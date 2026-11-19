"""
Document context segmentation and grouping engine for PDF, Images, and Spreadsheets.

Handles:
- PDF page grouping (start pages, continuation pages, distinct invoices).
- Spreadsheet grouping (per-sheet, financial rows, multi-invoice tables).
- Context budget and token management (overlapping batches for oversized inputs).
"""

import math
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from app.core.config import settings
from app.models.chunk import DocumentChunk
from app.services.extraction.context_models import (
    ExtractionContext,
    RowRange,
)
from app.services.extraction.context_selector import (
    CandidateScoreResult,
    InvoiceCandidateDetector,
)


class DocumentSegmenter:
    """
    Orchestrates intelligent grouping of DocumentChunks into traceable ExtractionContexts.
    """

    def __init__(
        self,
        max_input_chars: Optional[int] = None,
        candidate_threshold: float = 0.35,
    ):
        self.max_input_chars = int(
            max_input_chars or getattr(settings, "LLM_MAX_INPUT_CHARS", 30000)
        )
        self.detector = InvoiceCandidateDetector(candidate_threshold=candidate_threshold)

    def segment_pdf_chunks(
        self,
        document_id: UUID,
        chunks: List[DocumentChunk],
    ) -> List[ExtractionContext]:
        """
        Groups PDF/image page chunks into invoice candidates and distinct contexts.
        Sorts chunks by page_number and preserves original chunk IDs.
        """
        if not chunks:
            return []

        # Sort strictly by page_number (or chunk_index if page_number is None)
        sorted_chunks = sorted(
            chunks,
            key=lambda c: (c.page_number if c.page_number is not None else c.chunk_index),
        )

        groups: List[List[Tuple[DocumentChunk, CandidateScoreResult]]] = []
        current_group: List[Tuple[DocumentChunk, CandidateScoreResult]] = []
        current_invoice_numbers: Set[str] = set()

        for chunk in sorted_chunks:
            eval_res = self.detector.evaluate_text(chunk.content)
            chunk_numbers = set(eval_res.detected_invoice_numbers)

            if not current_group:
                # First chunk begins first group
                current_group.append((chunk, eval_res))
                current_invoice_numbers = set(chunk_numbers)
                continue

            prev_chunk, prev_eval = current_group[-1]

            # 1. Check for shared invoice number vs conflicting invoice numbers
            has_shared_invoice = bool(
                current_invoice_numbers
                and chunk_numbers
                and current_invoice_numbers.intersection(chunk_numbers)
            )
            has_conflicting_invoice = bool(
                current_invoice_numbers
                and chunk_numbers
                and not current_invoice_numbers.intersection(chunk_numbers)
            )

            # 2. Check if current chunk is explicit continuation
            is_explicit_continuation = (
                has_shared_invoice
                or eval_res.has_continuation_indicators
            )

            # 3. Check for new invoice start
            is_new_invoice_start = (
                not is_explicit_continuation
                and (
                    has_conflicting_invoice
                    or (eval_res.has_invoice_start_indicators and not has_shared_invoice)
                )
            )

            # 4. Check non-invoice pages mixed with invoices
            is_non_invoice_transition = (
                not is_explicit_continuation
                and prev_eval.is_invoice_candidate
                and not eval_res.is_invoice_candidate
            )
            is_invoice_after_non_invoice = (
                not is_explicit_continuation
                and not prev_eval.is_invoice_candidate
                and eval_res.is_invoice_candidate
            )

            if has_conflicting_invoice or is_new_invoice_start or is_non_invoice_transition or is_invoice_after_non_invoice:
                # Close current group and start a new one
                groups.append(current_group)
                current_group = [(chunk, eval_res)]
                current_invoice_numbers = set(chunk_numbers)
            else:
                # Continue current group
                current_group.append((chunk, eval_res))
                if chunk_numbers:
                    current_invoice_numbers.update(chunk_numbers)

        if current_group:
            groups.append(current_group)

        # Convert chunk groups into preliminary ExtractionContext objects
        contexts: List[ExtractionContext] = []
        for idx, group in enumerate(groups):
            ctx = self._create_pdf_context(document_id, idx, group)
            contexts.append(ctx)

        # Apply budget and size management (splitting oversized contexts into overlapping batches)
        return self._apply_context_budget(contexts)

    def segment_spreadsheet_chunks(
        self,
        document_id: UUID,
        chunks: List[DocumentChunk],
    ) -> List[ExtractionContext]:
        """
        Groups spreadsheet or CSV chunks into structured contexts.
        Preserves worksheet names, row positions, and column structures.
        """
        if not chunks:
            return []

        # Group chunks by sheet_name
        sheets_dict: Dict[str, List[DocumentChunk]] = {}
        for chunk in chunks:
            sheet_name = chunk.sheet_name or "Sheet1"
            sheets_dict.setdefault(sheet_name, []).append(chunk)

        contexts: List[ExtractionContext] = []
        context_idx = 0

        for sheet_name, sheet_chunks in sheets_dict.items():
            # Sort chunks by row_start or chunk_index
            sorted_chunks = sorted(
                sheet_chunks,
                key=lambda c: (c.row_start if c.row_start is not None else c.chunk_index),
            )

            # Evaluate content of the sheet
            sheet_evals = [self.detector.evaluate_text(c.content) for c in sorted_chunks]
            all_invoice_numbers: Set[str] = set()
            for ev in sheet_evals:
                all_invoice_numbers.update(ev.detected_invoice_numbers)

            # Check if chunks have distinct, non-overlapping invoice numbers that can be separated reliably
            chunk_inv_sets = [set(ev.detected_invoice_numbers) for ev in sheet_evals]
            can_separate_reliably = (
                len(sorted_chunks) > 1
                and all(len(invs) == 1 for invs in chunk_inv_sets)
                and len(all_invoice_numbers) == len(sorted_chunks)
            )

            if can_separate_reliably:
                for c, ev in zip(sorted_chunks, sheet_evals):
                    ctx = self._create_spreadsheet_context(
                        document_id=document_id,
                        context_index=context_idx,
                        sheet_name=sheet_name,
                        chunks=[c],
                        evals=[ev],
                        all_invoice_numbers=set(ev.detected_invoice_numbers),
                    )
                    contexts.append(ctx)
                    context_idx += 1
            else:
                ctx = self._create_spreadsheet_context(
                    document_id=document_id,
                    context_index=context_idx,
                    sheet_name=sheet_name,
                    chunks=sorted_chunks,
                    evals=sheet_evals,
                    all_invoice_numbers=all_invoice_numbers,
                )
                contexts.append(ctx)
                context_idx += 1

        # Apply budget splitting for oversized worksheets
        return self._apply_context_budget(contexts)

    def _create_spreadsheet_context(
        self,
        document_id: UUID,
        context_index: int,
        sheet_name: str,
        chunks: List[DocumentChunk],
        evals: List[CandidateScoreResult],
        all_invoice_numbers: Set[str],
    ) -> ExtractionContext:
        """Constructs an ExtractionContext from spreadsheet/CSV chunks."""
        has_financial = any(
            ev.is_invoice_candidate or "financial_total_found" in ev.matching_indicators
            for ev in evals
        )
        doc_type_hint = "invoice" if has_financial else "other"
        needs_review = False
        review_reasons: List[str] = []

        if len(all_invoice_numbers) > 1:
            needs_review = True
            review_reasons.append(
                f"Worksheet '{sheet_name}' contains multiple distinct invoice numbers: {sorted(all_invoice_numbers)}"
            )

        row_ranges: List[RowRange] = []
        chunk_ids: List[UUID] = []
        text_parts: List[str] = []

        for c in chunks:
            chunk_ids.append(c.id)
            row_ranges.append(
                RowRange(
                    sheet_name=sheet_name,
                    row_start=c.row_start,
                    row_end=c.row_end,
                )
            )
            header_prefix = f"--- Worksheet: {sheet_name}"
            if c.row_start is not None and c.row_end is not None:
                header_prefix += f" (Rows {c.row_start}-{c.row_end})"
            header_prefix += f" [Chunk ID: {c.id}] ---\n"
            text_parts.append(header_prefix + c.content.strip())

        combined_text = "\n\n".join(text_parts)
        char_count = len(combined_text)
        est_tokens = ExtractionContext.estimate_tokens(combined_text)

        return ExtractionContext(
            context_id=uuid4(),
            document_id=document_id,
            context_index=context_index,
            document_type_hint=doc_type_hint,
            source_chunk_ids=chunk_ids,
            page_start=None,
            page_end=None,
            sheet_names=[sheet_name],
            row_ranges=row_ranges,
            combined_text=combined_text,
            character_count=char_count,
            estimated_input_tokens=est_tokens,
            segmentation_confidence=0.9 if has_financial else 0.7,
            needs_manual_review=needs_review,
            review_reasons=review_reasons,
            metadata={
                "sheet_name": sheet_name,
                "total_chunks_in_sheet": len(chunks),
                "detected_invoice_numbers": sorted(all_invoice_numbers),
            },
        )

    def _create_pdf_context(
        self,
        document_id: UUID,
        context_index: int,
        group: List[Tuple[DocumentChunk, CandidateScoreResult]],
    ) -> ExtractionContext:
        """Constructs an ExtractionContext from a group of PDF/Image chunks."""
        chunks = [c for c, _ in group]
        evals = [ev for _, ev in group]

        chunk_ids = [c.id for c in chunks]
        pages = [c.page_number for c in chunks if c.page_number is not None]
        page_start = min(pages) if pages else None
        page_end = max(pages) if pages else None

        # Build formatted combined text with explicit chunk tags
        text_blocks: List[str] = []
        for c in chunks:
            page_info = f"Page {c.page_number}" if c.page_number is not None else f"Chunk {c.chunk_index}"
            header = f"--- [Document Chunk ID: {c.id} | {page_info}] ---"
            text_blocks.append(f"{header}\n{c.content.strip()}")

        combined_text = "\n\n".join(text_blocks)
        char_count = len(combined_text)
        est_tokens = ExtractionContext.estimate_tokens(combined_text)

        # Aggregate candidate evaluation
        all_numbers: Set[str] = set()
        for ev in evals:
            all_numbers.update(ev.detected_invoice_numbers)

        is_invoice_group = any(ev.is_invoice_candidate for ev in evals)
        doc_type_hint = "invoice" if is_invoice_group else "other"

        # Check for review flags
        needs_review = False
        review_reasons: List[str] = []

        if len(all_numbers) > 1:
            needs_review = True
            review_reasons.append(
                f"Multiple distinct invoice numbers grouped together: {sorted(all_numbers)}"
            )

        if is_invoice_group and not all_numbers:
            needs_review = True
            review_reasons.append(
                "Invoice candidate has no detectable invoice number"
            )

        for ev in evals:
            if ev.suggested_review_status:
                needs_review = True
                review_reasons.extend(ev.review_reasons)

        # Calculate heuristic segmentation confidence
        confidence = 0.95
        if needs_review:
            confidence = 0.65
        elif not is_invoice_group:
            confidence = 0.80

        # Deduplicate review reasons
        unique_review_reasons = list(dict.fromkeys(review_reasons))

        return ExtractionContext(
            context_id=uuid4(),
            document_id=document_id,
            context_index=context_index,
            document_type_hint=doc_type_hint,
            source_chunk_ids=chunk_ids,
            page_start=page_start,
            page_end=page_end,
            sheet_names=[],
            row_ranges=[],
            combined_text=combined_text,
            character_count=char_count,
            estimated_input_tokens=est_tokens,
            segmentation_confidence=confidence,
            needs_manual_review=needs_review,
            review_reasons=unique_review_reasons,
            metadata={
                "detected_invoice_numbers": sorted(all_numbers),
                "num_pages": len(pages),
                "is_candidate": is_invoice_group,
            },
        )

    def _apply_context_budget(
        self,
        contexts: List[ExtractionContext],
    ) -> List[ExtractionContext]:
        """
        Enforces LLM_MAX_INPUT_CHARS budget.
        Splits oversized contexts into sequential overlapping batches.
        Preserves all source chunk IDs and never silently truncates.
        """
        budgeted_contexts: List[ExtractionContext] = []
        new_index = 0

        for ctx in contexts:
            if ctx.character_count <= self.max_input_chars:
                ctx.context_index = new_index
                budgeted_contexts.append(ctx)
                new_index += 1
                continue

            # Context exceeds budget: split into overlapping batches
            batches = self._split_oversized_context(ctx, new_index)
            for batch_ctx in batches:
                budgeted_contexts.append(batch_ctx)
                new_index += 1

        return budgeted_contexts

    def _split_oversized_context(
        self,
        ctx: ExtractionContext,
        start_index: int,
    ) -> List[ExtractionContext]:
        """
        Splits an oversized ExtractionContext into sequential batches with overlap,
        ensuring every chunk is preserved and metadata accurately traces parentage.
        """
        # Split by chunk sections if formatted with chunk markers
        chunk_sections = ctx.combined_text.split("\n\n--- ")
        if len(chunk_sections) > 1:
            reconstructed_sections = [
                chunk_sections[0] if i == 0 else f"--- {chunk_sections[i]}"
                for i in range(len(chunk_sections))
            ]
        else:
            # Fallback to paragraph splitting if single chunk is huge
            reconstructed_sections = ctx.combined_text.split("\n\n")

        batches: List[List[str]] = []
        current_batch: List[str] = []
        current_chars = 0

        target_batch_size = int(self.max_input_chars * 0.85)

        for section in reconstructed_sections:
            sec_len = len(section)
            if current_batch and (current_chars + sec_len > self.max_input_chars):
                batches.append(current_batch)
                # Overlap: keep the last section for continuity if possible
                overlap_section = current_batch[-1] if len(current_batch) > 1 else None
                if overlap_section and len(overlap_section) < self.max_input_chars * 0.3:
                    current_batch = [overlap_section, section]
                    current_chars = len(overlap_section) + sec_len
                else:
                    current_batch = [section]
                    current_chars = sec_len
            else:
                current_batch.append(section)
                current_chars += sec_len

        if current_batch:
            batches.append(current_batch)

        total_batches = len(batches)
        parent_id = ctx.context_id
        split_contexts: List[ExtractionContext] = []

        for b_idx, batch_parts in enumerate(batches):
            batch_text = "\n\n".join(batch_parts)
            b_char_count = len(batch_text)
            b_tokens = ExtractionContext.estimate_tokens(batch_text)

            # Map which chunk IDs appear in this batch text
            batch_chunk_ids = [
                cid for cid in ctx.source_chunk_ids
                if str(cid) in batch_text
            ]
            if not batch_chunk_ids:
                batch_chunk_ids = list(ctx.source_chunk_ids)

            batch_ctx = ExtractionContext(
                context_id=uuid4(),
                document_id=ctx.document_id,
                context_index=start_index + b_idx,
                document_type_hint=ctx.document_type_hint,
                source_chunk_ids=batch_chunk_ids,
                page_start=ctx.page_start,
                page_end=ctx.page_end,
                sheet_names=ctx.sheet_names,
                row_ranges=ctx.row_ranges,
                combined_text=batch_text,
                character_count=b_char_count,
                estimated_input_tokens=b_tokens,
                segmentation_confidence=ctx.segmentation_confidence,
                needs_manual_review=ctx.needs_manual_review or (total_batches > 1),
                review_reasons=list(ctx.review_reasons) + (
                    [f"Oversized context split into batch {b_idx + 1} of {total_batches}"]
                    if total_batches > 1 else []
                ),
                metadata={
                    **ctx.metadata,
                    "is_split": True,
                    "batch_index": b_idx,
                    "total_batches": total_batches,
                    "parent_context_id": str(parent_id),
                },
            )
            split_contexts.append(batch_ctx)

        return split_contexts
