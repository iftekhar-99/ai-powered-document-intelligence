"""
Invoice extraction orchestrator for the AI-Powered Document Intelligence System.

Coordinates:
- Context preparation retrieval.
- Eligible context selection and non-invoice skipping.
- JSON Schema normalization for Gemini structured outputs.
- Retry-wrapped LLM invocations with exponential backoff.
- Source chunk allowlist validation and rejection of fabricated evidence.
- Multi-page and multi-batch invoice merging without content loss.
- Completeness scoring and confidence threshold enforcement.
- Strict Pydantic response validation and audit tracking.
"""

import asyncio
import copy
import logging
import math
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.extraction import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    ExtractionStatus,
    InvoiceExtraction,
    InvoiceLineItemExtraction,
    SourceEvidence,
)
from app.services.extraction.context_models import ExtractionContext
from app.services.extraction.context_service import context_service
from app.services.extraction.prompt_builder import (
    PROMPT_VERSION,
    ExtractionPromptBuilder,
)
from app.services.extraction.providers import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMMalformedResponseError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
    get_llm_provider,
)

logger = logging.getLogger(__name__)

CORE_INVOICE_FIELDS = [
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "total",
    "currency",
    "line_items",
]


def inline_schema_defs(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inlines all $defs and $ref in a JSON Schema and normalizes anyOf constructs
    into OpenAPI 3.0 nullable types to ensure maximum compatibility with Google
    Gemini's structured output engine, while preserving full schema semantics.
    """
    defs = schema.get("$defs", {})

    def resolve_node(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                if ref_key in defs:
                    resolved = copy.deepcopy(defs[ref_key])
                    return resolve_node(resolved)
            new_dict = {}
            for k, v in node.items():
                if k in ("$defs", "title"):
                    continue
                new_dict[k] = resolve_node(v)

            # Convert anyOf with null to OpenAPI 3.0 type + nullable: true
            if "anyOf" in new_dict:
                any_of = new_dict.pop("anyOf")
                is_nullable = any(
                    isinstance(item, dict) and item.get("type") == "null"
                    for item in any_of
                )
                non_null_types = [
                    item.get("type")
                    for item in any_of
                    if isinstance(item, dict) and item.get("type") not in ("null", None)
                ]
                if non_null_types:
                    # Prefer number over string for Decimal financial fields
                    chosen_type = "number" if "number" in non_null_types else non_null_types[0]
                    new_dict["type"] = chosen_type
                    if is_nullable:
                        new_dict["nullable"] = True
                else:
                    non_null_items = [
                        item for item in any_of
                        if isinstance(item, dict) and item.get("type") != "null"
                    ]
                    if non_null_items:
                        for k2, v2 in non_null_items[0].items():
                            if k2 not in new_dict:
                                new_dict[k2] = v2
                    if is_nullable:
                        new_dict["nullable"] = True

            return new_dict
        elif isinstance(node, list):
            return [resolve_node(item) for item in node]
        return node

    inlined = resolve_node(schema)
    if isinstance(inlined, dict):
        inlined.pop("$defs", None)
    return inlined


@dataclass
class OrchestrationMetadata:
    """Execution telemetry recorded during extraction orchestration."""
    provider: str
    model: str
    prompt_version: str
    processing_time_ms: float = 0.0
    contexts_total: int = 0
    contexts_processed: int = 0
    contexts_skipped: int = 0
    total_batches: int = 0
    retry_count: int = 0
    token_usage: Dict[str, Optional[int]] = field(
        default_factory=lambda: {
            "prompt_tokens": None,
            "candidates_tokens": None,
            "total_tokens": None,
        }
    )


class EvidenceValidator:
    """
    Validates that returned SourceEvidence entries strictly link to real,
    existing DocumentChunks in the current context's allowlist.
    """

    @classmethod
    def validate_invoice_evidence(
        cls,
        invoice: InvoiceExtraction,
        allowed_chunk_ids: Set[UUID],
    ) -> List[str]:
        """
        Validates all evidence fields on an invoice. Rejects invalid chunk IDs,
        modifies invoice in-place to remove invalid evidence, and returns warning messages.
        """
        warnings: List[str] = []

        # Validate header scalar fields
        for field_name in [
            "invoice_number",
            "invoice_date",
            "supplier_name",
            "customer_name",
            "subtotal",
            "tax",
            "total",
            "currency",
        ]:
            field_obj = getattr(invoice, field_name, None)
            if isinstance(field_obj, ExtractedField):
                retained, rejected = cls._filter_evidence(field_obj.evidence, allowed_chunk_ids)
                field_obj.evidence = retained
                if rejected:
                    for rej_id in rejected:
                        msg = f"Rejected invalid/unknown source_chunk_id '{rej_id}' on field '{field_name}'"
                        warnings.append(msg)
                        invoice.needs_manual_review = True
                        if msg not in invoice.review_reasons:
                            invoice.review_reasons.append(msg)

                # Check missing evidence for populated core fields
                if field_name in ("invoice_number", "total", "supplier_name") and field_obj.value is not None:
                    if not field_obj.evidence and allowed_chunk_ids:
                        warn_msg = f"Core field '{field_name}' was extracted without supporting source evidence"
                        warnings.append(warn_msg)
                        invoice.needs_manual_review = True
                        if warn_msg not in invoice.review_reasons:
                            invoice.review_reasons.append(warn_msg)

        # Validate line item fields
        for idx, item in enumerate(invoice.line_items):
            for li_field in ["description", "quantity", "unit_price", "tax", "line_total"]:
                field_obj = getattr(item, li_field, None)
                if isinstance(field_obj, ExtractedField):
                    retained, rejected = cls._filter_evidence(field_obj.evidence, allowed_chunk_ids)
                    field_obj.evidence = retained
                    if rejected:
                        for rej_id in rejected:
                            msg = f"Rejected invalid source_chunk_id '{rej_id}' on line item {idx+1} field '{li_field}'"
                            warnings.append(msg)
                            invoice.needs_manual_review = True
                            if msg not in invoice.review_reasons:
                                invoice.review_reasons.append(msg)

        return warnings

    @staticmethod
    def _filter_evidence(
        evidence_list: List[SourceEvidence],
        allowed_chunk_ids: Set[UUID],
    ) -> Tuple[List[SourceEvidence], List[UUID]]:
        retained: List[SourceEvidence] = []
        rejected: List[UUID] = []
        for ev in evidence_list:
            if ev.source_chunk_id in allowed_chunk_ids:
                retained.append(ev)
            else:
                rejected.append(ev.source_chunk_id)
        return retained, rejected


class MultiBatchMerger:
    """
    Merges partial extraction results from sequential context batches
    belonging to the same parent invoice candidate.
    """

    @classmethod
    def merge_invoices(
        cls,
        base_inv: InvoiceExtraction,
        incoming_inv: InvoiceExtraction,
    ) -> InvoiceExtraction:
        """
        Merges incoming_inv into base_inv according to the strict merge rules:
        - Non-null fields fill missing fields.
        - Conflicting non-null fields flag manual review without silent overwriting.
        - Line items are preserved from every batch.
        - Overlapping line items are deduplicated only when identical evidence proves overlap.
        - Legitimate repeated line items are preserved.
        """
        merged = base_inv.model_copy(deep=True)

        # 1. Merge scalar fields
        scalar_fields = [
            "invoice_number",
            "invoice_date",
            "supplier_name",
            "customer_name",
            "subtotal",
            "tax",
            "total",
            "currency",
        ]
        for field_name in scalar_fields:
            base_field: ExtractedField = getattr(merged, field_name)
            inc_field: ExtractedField = getattr(incoming_inv, field_name)

            if base_field.value is None and inc_field.value is not None:
                setattr(merged, field_name, inc_field.model_copy(deep=True))
            elif base_field.value is not None and inc_field.value is not None:
                # Compare values
                if str(base_field.value).strip() == str(inc_field.value).strip():
                    # Matching: merge evidence without duplication
                    cls._merge_field_evidence(base_field, inc_field)
                else:
                    # Conflicting values: record conflict, flag manual review, do not silently overwrite
                    conflict_msg = (
                        f"Conflicting values for '{field_name}' across batches: "
                        f"'{base_field.value}' vs '{inc_field.value}'"
                    )
                    merged.needs_manual_review = True
                    if conflict_msg not in merged.review_reasons:
                        merged.review_reasons.append(conflict_msg)
                    cls._merge_field_evidence(base_field, inc_field)

        # 2. Merge line items with strict overlap deduplication
        merged.line_items = cls._merge_line_items(merged.line_items, incoming_inv.line_items)

        # 3. Merge page boundaries
        pages_start = [p for p in (merged.document_page_start, incoming_inv.document_page_start) if p is not None]
        pages_end = [p for p in (merged.document_page_end, incoming_inv.document_page_end) if p is not None]
        if pages_start:
            merged.document_page_start = min(pages_start)
        if pages_end:
            merged.document_page_end = max(pages_end)

        # 4. Merge review flags and reasons
        if incoming_inv.needs_manual_review:
            merged.needs_manual_review = True
        for reason in incoming_inv.review_reasons:
            if reason not in merged.review_reasons:
                merged.review_reasons.append(reason)

        # 5. Overall confidence aggregation
        confs = [c for c in (merged.overall_confidence, incoming_inv.overall_confidence) if c is not None]
        if confs:
            merged.overall_confidence = round(sum(confs) / len(confs), 3)

        return merged

    @staticmethod
    def _merge_field_evidence(target: ExtractedField, source: ExtractedField) -> None:
        existing_signatures = {
            (ev.source_chunk_id, ev.relevant_text.strip())
            for ev in target.evidence
        }
        for ev in source.evidence:
            sig = (ev.source_chunk_id, ev.relevant_text.strip())
            if sig not in existing_signatures:
                target.evidence.append(ev)
                existing_signatures.add(sig)

    @classmethod
    def _merge_line_items(
        cls,
        base_items: List[InvoiceLineItemExtraction],
        incoming_items: List[InvoiceLineItemExtraction],
    ) -> List[InvoiceLineItemExtraction]:
        merged_items = list(base_items)

        for item_b in incoming_items:
            evidence_b = cls._extract_line_item_evidence_signatures(item_b)

            is_duplicate_overlap = False
            if evidence_b:
                for item_a in base_items:
                    evidence_a = cls._extract_line_item_evidence_signatures(item_a)
                    # Deduplicate ONLY if evidence proves identical source chunk overlap
                    if evidence_a and evidence_a == evidence_b:
                        is_duplicate_overlap = True
                        break

            if not is_duplicate_overlap:
                merged_items.append(item_b)

        return merged_items

    @staticmethod
    def _extract_line_item_evidence_signatures(item: InvoiceLineItemExtraction) -> Set[Tuple[UUID, str]]:
        sigs = set()
        for f_name in ["description", "quantity", "unit_price", "tax", "line_total"]:
            f: ExtractedField = getattr(item, f_name)
            for ev in f.evidence:
                if ev.source_chunk_id and ev.relevant_text:
                    sigs.add((ev.source_chunk_id, ev.relevant_text.strip()))
        return sigs


class InvoiceExtractionOrchestrator:
    """
    Coordinates context-to-Gemini invoice extraction, validation, and merging.
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        prompt_builder: Optional[ExtractionPromptBuilder] = None,
        max_retries: Optional[int] = None,
        base_retry_delay: float = 0.5,
        confidence_threshold: Optional[float] = None,
    ):
        self._provider = provider
        self._prompt_builder = prompt_builder or ExtractionPromptBuilder()
        self._max_retries = (
            max_retries
            if max_retries is not None
            else getattr(settings, "LLM_MAX_RETRIES", 2)
        )
        self._base_retry_delay = base_retry_delay
        self._confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else getattr(settings, "EXTRACTION_CONFIDENCE_THRESHOLD", 0.75)
        )

    def _get_provider(self) -> LLMProvider:
        if self._provider is not None:
            return self._provider
        return get_llm_provider()

    async def extract_document_invoices(
        self,
        document_id: UUID,
        db: Optional[AsyncSession] = None,
        db_session: Optional[AsyncSession] = None,
    ) -> DocumentExtractionResponse:
        """
        Executes the full end-to-end extraction pipeline for a document.
        Does not persist invoice records to the database.
        """
        session = db or db_session
        start_time = time.perf_counter()
        provider = self._get_provider()

        metadata = OrchestrationMetadata(
            provider=provider.provider_name,
            model=provider.model_name,
            prompt_version=self._prompt_builder.version,
        )

        # 1. Retrieve prepared extraction contexts
        prep_result = await context_service.prepare_document_contexts(document_id, session)
        contexts = prep_result.contexts
        metadata.contexts_total = len(contexts)

        warnings: List[str] = list(prep_result.warnings)

        if not contexts:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            metadata.processing_time_ms = elapsed_ms
            return DocumentExtractionResponse(
                document_id=document_id,
                document_type=DocumentType.OTHER,
                invoices=[],
                warnings=warnings + ["No contexts available for extraction."],
                extraction_status=ExtractionStatus.COMPLETED,
                metadata=metadata.__dict__,
            )

        # 2. Filter eligible contexts vs skipped contexts
        eligible_contexts: List[ExtractionContext] = []
        for ctx in contexts:
            # Skip non-invoice contexts that have 0 detected invoice numbers
            if ctx.document_type_hint == "other" and not ctx.metadata.get("detected_invoice_numbers"):
                metadata.contexts_skipped += 1
                warnings.append(
                    f"Context {ctx.context_index} skipped as non-invoice content "
                    f"({ctx.character_count} chars)."
                )
            else:
                eligible_contexts.append(ctx)

        metadata.contexts_processed = len(eligible_contexts)

        # Group split batches by parent_context_id
        # Single-batch or unsplit contexts use their own context_id as key
        batch_groups: Dict[str, List[ExtractionContext]] = {}
        for ctx in eligible_contexts:
            parent_key = ctx.metadata.get("parent_context_id") or str(ctx.context_id)
            batch_groups.setdefault(parent_key, []).append(ctx)

        metadata.total_batches = len(eligible_contexts)

        extracted_invoices: List[InvoiceExtraction] = []
        total_attempts = 0
        all_failed = True
        any_success = False

        # 3. Process each batch group
        for parent_key, group_contexts in batch_groups.items():
            # Sort batches by batch_index or context_index
            sorted_batches = sorted(
                group_contexts,
                key=lambda c: c.metadata.get("batch_index", c.context_index),
            )

            group_invoices: List[InvoiceExtraction] = []

            for batch_ctx in sorted_batches:
                prompt_obj = self._prompt_builder.build_prompt(batch_ctx)
                normalized_schema = inline_schema_defs(prompt_obj.json_schema)

                # Execute LLM generation with bounded retry
                llm_response, retries_used = await self._execute_with_retry(
                    provider=provider,
                    prompt=prompt_obj.user_prompt,
                    json_schema=normalized_schema,
                )
                total_attempts += retries_used

                if llm_response is None:
                    warnings.append(
                        f"Failed to extract context {batch_ctx.context_index} "
                        f"after {retries_used} attempt(s)."
                    )
                    continue

                any_success = True
                all_failed = False

                # Track token usage if available
                if llm_response.usage:
                    if llm_response.usage.prompt_tokens:
                        metadata.token_usage["prompt_tokens"] = (
                            (metadata.token_usage["prompt_tokens"] or 0)
                            + llm_response.usage.prompt_tokens
                        )
                    if llm_response.usage.candidates_tokens:
                        metadata.token_usage["candidates_tokens"] = (
                            (metadata.token_usage["candidates_tokens"] or 0)
                            + llm_response.usage.candidates_tokens
                        )
                    if llm_response.usage.total_tokens:
                        metadata.token_usage["total_tokens"] = (
                            (metadata.token_usage["total_tokens"] or 0)
                            + llm_response.usage.total_tokens
                        )

                # Parse and validate response with Pydantic
                invoices_from_batch = self._parse_and_validate_response(
                    parsed_json=llm_response.parsed_json,
                    document_id=document_id,
                    context=batch_ctx,
                    warnings=warnings,
                )

                # Validate source evidence references against allowlist
                allowed_ids = set(batch_ctx.source_chunk_ids)
                for inv in invoices_from_batch:
                    evidence_warnings = EvidenceValidator.validate_invoice_evidence(
                        invoice=inv,
                        allowed_chunk_ids=allowed_ids,
                    )
                    warnings.extend(evidence_warnings)

                    # Assess completeness and confidence
                    self._assess_invoice_quality(inv, warnings)

                group_invoices.extend(invoices_from_batch)

            # 4. Multi-batch merging for split contexts
            if len(sorted_batches) > 1 and group_invoices:
                merged_inv = group_invoices[0]
                for next_inv in group_invoices[1:]:
                    merged_inv = MultiBatchMerger.merge_invoices(merged_inv, next_inv)
                extracted_invoices.append(merged_inv)
            else:
                extracted_invoices.extend(group_invoices)

        metadata.retry_count = total_attempts
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        metadata.processing_time_ms = elapsed_ms

        # 5. Determine overall extraction status
        if not eligible_contexts:
            status = ExtractionStatus.COMPLETED
            doc_type = DocumentType.OTHER
        elif all_failed:
            status = ExtractionStatus.FAILED
            doc_type = DocumentType.UNKNOWN
        elif len(extracted_invoices) < len(batch_groups):
            status = ExtractionStatus.PARTIAL
            doc_type = DocumentType.INVOICE
        else:
            status = ExtractionStatus.COMPLETED
            doc_type = DocumentType.INVOICE if extracted_invoices else DocumentType.OTHER

        return DocumentExtractionResponse(
            document_id=document_id,
            document_type=doc_type,
            invoices=extracted_invoices,
            warnings=warnings,
            extraction_status=status,
            metadata=metadata.__dict__,
        )

    async def _execute_with_retry(
        self,
        provider: LLMProvider,
        prompt: str,
        json_schema: Dict[str, Any],
    ) -> Tuple[Optional[Any], int]:
        """
        Executes generate_structured with exponential backoff on retryable errors.
        Never retries authentication or configuration errors.
        """
        attempts = 0
        last_exception: Optional[Exception] = None

        while attempts <= self._max_retries:
            attempts += 1
            try:
                response = await provider.generate_structured(
                    prompt=prompt,
                    json_schema=json_schema,
                )
                return response, attempts - 1
            except (LLMAuthenticationError, LLMConfigurationError) as exc:
                # Fatal: do NOT retry
                logger.error("Non-retryable LLM provider error: %s", exc)
                return None, attempts - 1
            except (LLMRateLimitError, LLMServiceUnavailableError, LLMTimeoutError) as exc:
                last_exception = exc
                if attempts > self._max_retries:
                    logger.error("Max retries exceeded for retryable error: %s", exc)
                    break
                delay = self._base_retry_delay * (2 ** (attempts - 1))
                logger.warning(
                    "Retryable LLM error (attempt %d/%d): %s. Backing off for %.2fs",
                    attempts,
                    self._max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            except LLMMalformedResponseError as exc:
                last_exception = exc
                logger.error("Malformed response from model: %s", exc)
                # Malformed JSON typically indicates bad prompt/model failure, retry once if permitted
                if attempts > self._max_retries:
                    break
                await asyncio.sleep(self._base_retry_delay)
            except Exception as exc:
                last_exception = exc
                logger.error("Unexpected LLM error: %s", exc)
                break

        return None, attempts - 1

    def _parse_and_validate_response(
        self,
        parsed_json: Any,
        document_id: UUID,
        context: ExtractionContext,
        warnings: List[str],
    ) -> List[InvoiceExtraction]:
        """
        Safely maps parsed JSON into validated InvoiceExtraction models,
        supporting both DocumentExtractionResponse formats and single InvoiceExtraction payloads.
        """
        invoices: List[InvoiceExtraction] = []

        if isinstance(parsed_json, dict):
            # Format 1: Response has 'invoices' array
            if "invoices" in parsed_json and isinstance(parsed_json["invoices"], list):
                for item in parsed_json["invoices"]:
                    try:
                        inv = InvoiceExtraction.model_validate(item)
                        # Ensure page boundaries from context if missing
                        if inv.document_page_start is None:
                            inv.document_page_start = context.page_start
                        if inv.document_page_end is None:
                            inv.document_page_end = context.page_end
                        if inv.source_context_id is None:
                            inv.source_context_id = context.context_id
                        invoices.append(inv)
                    except Exception as ve:
                        warnings.append(f"Validation error in extracted invoice item: {ve}")

            # Format 2: Direct InvoiceExtraction dictionary
            elif "invoice_number" in parsed_json or "total" in parsed_json:
                try:
                    inv = InvoiceExtraction.model_validate(parsed_json)
                    if inv.document_page_start is None:
                        inv.document_page_start = context.page_start
                    if inv.document_page_end is None:
                        inv.document_page_end = context.page_end
                    if inv.source_context_id is None:
                        inv.source_context_id = context.context_id
                    invoices.append(inv)
                except Exception as ve:
                    warnings.append(f"Validation error in extracted invoice: {ve}")
            else:
                warnings.append(
                    f"Model output in context {context.context_index} had unrecognized keys: {list(parsed_json.keys())[:5]}"
                )

        elif isinstance(parsed_json, list):
            # Format 3: Bare list of invoice items
            for item in parsed_json:
                if isinstance(item, dict):
                    try:
                        inv = InvoiceExtraction.model_validate(item)
                        invoices.append(inv)
                    except Exception as ve:
                        warnings.append(f"Validation error in list item invoice: {ve}")

        return invoices

    def _assess_invoice_quality(
        self,
        invoice: InvoiceExtraction,
        warnings: List[str],
    ) -> None:
        """
        Computes completeness ratio and applies confidence thresholds.
        """
        # Completeness ratio
        present_count = 0
        for fname in CORE_INVOICE_FIELDS:
            if fname == "line_items":
                if invoice.line_items:
                    present_count += 1
            else:
                field_val = getattr(invoice, fname, None)
                if isinstance(field_val, ExtractedField) and field_val.value is not None:
                    present_count += 1

        completeness = round(present_count / len(CORE_INVOICE_FIELDS), 2)
        if completeness < 0.4:
            warn_msg = f"Low invoice completeness ({int(completeness * 100)}% of core fields populated)"
            warnings.append(warn_msg)
            invoice.needs_manual_review = True
            if warn_msg not in invoice.review_reasons:
                invoice.review_reasons.append(warn_msg)

        # Confidence threshold check
        if invoice.overall_confidence is not None:
            if invoice.overall_confidence < self._confidence_threshold:
                conf_msg = (
                    f"Overall confidence ({invoice.overall_confidence:.2f}) "
                    f"below threshold ({self._confidence_threshold:.2f})"
                )
                warnings.append(conf_msg)
                invoice.needs_manual_review = True
                if conf_msg not in invoice.review_reasons:
                    invoice.review_reasons.append(conf_msg)


# Global default orchestrator instance
extraction_orchestrator = InvoiceExtractionOrchestrator()


async def extract_document_invoices(
    document_id: UUID,
    db: Optional[AsyncSession] = None,
    db_session: Optional[AsyncSession] = None,
    provider: Optional[LLMProvider] = None,
) -> DocumentExtractionResponse:
    """
    Public entry point for extracting invoices from a document.
    """
    session = db or db_session
    orch = InvoiceExtractionOrchestrator(provider=provider) if provider else extraction_orchestrator
    return await orch.extract_document_invoices(document_id, db=session)
