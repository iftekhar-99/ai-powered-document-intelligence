"""
Extraction Application Service for the AI-Powered Document Intelligence System.

Coordinates:
- ExtractionRun lifecycle (queued -> processing -> completed/partial/failed).
- Independent database session allocation for background processing.
- Invocation of InvoiceExtractionOrchestrator.
- Invocation of InvoicePersistenceService.
- Metric and token tracking.
- Idempotent execution and audit event logging.
"""

import datetime
import logging
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_maker
from app.models.document import Document, DocumentStatus
from app.models.extraction_run import ExtractionRun, ExtractionRunStatus
from app.models.processing_event import ProcessingEvent
from app.schemas.extraction import ExtractionStatus
from app.services.extraction.orchestrator import InvoiceExtractionOrchestrator
from app.services.extraction.persistence import invoice_persistence_service
from app.services.extraction.prompt_builder import PROMPT_VERSION
from app.services.extraction.providers import get_llm_provider
from app.services.validation import validation_service

logger = logging.getLogger(__name__)


class ExtractionService:
    """
    Application service managing the invoice extraction lifecycle.
    """

    async def create_extraction_run(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> ExtractionRun:
        """
        Creates and persists a new ExtractionRun in QUEUED status.
        """
        provider_name = getattr(settings, "LLM_PROVIDER", "gemini")
        model_name = getattr(settings, "GEMINI_MODEL", "gemini-flash-lite-latest")

        run = ExtractionRun(
            id=uuid4(),
            document_id=document_id,
            provider=provider_name,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            status=ExtractionRunStatus.QUEUED.value,
            total_contexts=0,
            successful_contexts=0,
            skipped_contexts=0,
            failed_contexts=0,
        )
        db.add(run)

        # Audit event
        event = ProcessingEvent(
            id=uuid4(),
            document_id=document_id,
            event_type="extraction_run_queued",
            message=f"Queued extraction run {run.id} with provider '{provider_name}' and model '{model_name}'.",
        )
        db.add(event)
        await db.commit()
        await db.refresh(run)

        logger.info("Created ExtractionRun %s for document %s in QUEUED state.", run.id, document_id)
        return run

    async def execute_extraction_run(
        self,
        document_id: UUID,
        extraction_run_id: UUID,
        orchestrator: Optional[InvoiceExtractionOrchestrator] = None,
        session_maker: Optional[Any] = None,
    ) -> ExtractionRun:
        """
        Executes an extraction run inside an independent database session.
        Handles status updates, metrics tracking, invoice persistence, and error handling.
        """
        start_time = datetime.datetime.now(datetime.timezone.utc)
        active_session_maker = session_maker or async_session_maker

        async with active_session_maker() as db:
            # 1. Fetch the extraction run
            run_query = select(ExtractionRun).where(ExtractionRun.id == extraction_run_id)
            run = (await db.execute(run_query)).scalar_one_or_none()

            if not run:
                logger.error("ExtractionRun %s not found for document %s", extraction_run_id, document_id)
                raise ValueError(f"ExtractionRun {extraction_run_id} not found.")

            # 2. Update status to PROCESSING
            run.status = ExtractionRunStatus.PROCESSING.value
            run.started_at = start_time
            await db.commit()

            orch = orchestrator or InvoiceExtractionOrchestrator()

            try:
                # 3. Execute extraction pipeline
                extraction_response = await orch.extract_document_invoices(
                    document_id=document_id,
                    db=db,
                )

                # 4. Persist extraction results into database
                persisted_invoices = await invoice_persistence_service.persist_extraction_results(
                    db=db,
                    document_id=document_id,
                    extraction_run_id=extraction_run_id,
                    extraction_response=extraction_response,
                )

                # 4b. Execute deterministic financial validation & duplicate detection
                for p_inv in persisted_invoices:
                    try:
                        await validation_service.validate_invoice(db, p_inv.id)
                    except Exception as v_err:
                        logger.warning(
                            "Post-extraction validation failed for invoice %s: %s",
                            p_inv.id,
                            v_err,
                        )

                # 5. Extract metadata metrics
                meta = extraction_response.metadata or {}
                token_usage = meta.get("token_usage", {})
                contexts_total = meta.get("contexts_total", len(extraction_response.invoices))
                contexts_processed = meta.get("contexts_processed", len(persisted_invoices))
                contexts_skipped = meta.get("contexts_skipped", 0)

                completed_time = datetime.datetime.now(datetime.timezone.utc)
                latency_ms = int((completed_time - start_time).total_seconds() * 1000)

                # 6. Map status
                if extraction_response.extraction_status == ExtractionStatus.COMPLETED:
                    run.status = ExtractionRunStatus.COMPLETED.value
                elif extraction_response.extraction_status == ExtractionStatus.PARTIAL:
                    run.status = ExtractionRunStatus.PARTIAL.value
                else:
                    run.status = ExtractionRunStatus.FAILED.value

                run.completed_at = completed_time
                run.processing_time_ms = latency_ms
                run.input_token_count = token_usage.get("prompt_tokens")
                run.output_token_count = token_usage.get("candidates_tokens")
                run.total_contexts = contexts_total
                run.successful_contexts = len(persisted_invoices)
                run.skipped_contexts = contexts_skipped
                run.failed_contexts = max(0, contexts_processed - len(persisted_invoices))

                if extraction_response.warnings:
                    run.error_message = "\n".join(extraction_response.warnings)

                # Audit event for completion
                event = ProcessingEvent(
                    id=uuid4(),
                    document_id=document_id,
                    event_type="extraction_run_completed",
                    message=(
                        f"Extraction run {run.id} finished with status '{run.status}'. "
                        f"Extracted {len(persisted_invoices)} invoice(s) in {latency_ms} ms."
                    ),
                )
                db.add(event)
                await db.commit()
                await db.refresh(run)

                logger.info(
                    "ExtractionRun %s completed with status '%s' (%d invoices persisted).",
                    run.id,
                    run.status,
                    len(persisted_invoices),
                )
                return run

            except Exception as exc:
                logger.error(
                    "Unhandled exception in ExtractionRun %s: %s",
                    extraction_run_id,
                    exc,
                    exc_info=True,
                )
                completed_time = datetime.datetime.now(datetime.timezone.utc)
                latency_ms = int((completed_time - start_time).total_seconds() * 1000)

                run.status = ExtractionRunStatus.FAILED.value
                run.completed_at = completed_time
                run.processing_time_ms = latency_ms
                run.error_message = str(exc)

                fail_event = ProcessingEvent(
                    id=uuid4(),
                    document_id=document_id,
                    event_type="extraction_run_failed",
                    message=f"Extraction run {run.id} failed: {exc}",
                )
                db.add(fail_event)
                await db.commit()
                await db.refresh(run)
                return run


extraction_service = ExtractionService()
