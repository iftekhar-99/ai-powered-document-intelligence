import asyncio
import logging
import uuid
from typing import Optional
from celery import Celery
from fastapi import BackgroundTasks
from app.core.config import settings
from app.db.session import async_session_maker
from app.services.document_processing.orchestrator import document_processor

logger = logging.getLogger("doc_intel.workers")

celery_app = Celery(
    "document_intelligence_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


async def _execute_processing(document_id: uuid.UUID, is_reprocess: bool = False):
    """Execute document extraction within an isolated async database session."""
    async with async_session_maker() as session:
        try:
            await document_processor.process_document(
                document_id=document_id,
                db=session,
                is_reprocess=is_reprocess,
            )
        except Exception as e:
            logger.error(
                "Background extraction task failed for document %s: %s",
                document_id,
                e,
                exc_info=True,
            )


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_document_task(self, document_id: str, is_reprocess: bool = False):
    """Celery task entry point for processing a document."""
    logger.info("Executing Celery process_document_task for doc ID: %s", document_id)
    try:
        doc_uuid = uuid.UUID(document_id)
        asyncio.run(_execute_processing(doc_uuid, is_reprocess=is_reprocess))
        return {"status": "success", "document_id": document_id}
    except Exception as exc:
        logger.error("Celery task exception: %s. Retrying...", exc)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def retry_document_task(self, document_id: str):
    """Celery task entry point for explicitly retrying or reprocessing a document."""
    return process_document_task(self, document_id, is_reprocess=True)


def dispatch_document_processing(
    document_id: uuid.UUID,
    background_tasks: Optional[BackgroundTasks] = None,
    is_reprocess: bool = False,
) -> str:
    """
    Route processing to Celery/Redis if configured, or FastAPI BackgroundTasks for local inline dev.
    Returns: "celery" or "inline"
    """
    mode = settings.PROCESSING_MODE.lower()

    if mode == "celery":
        try:
            process_document_task.delay(str(document_id), is_reprocess=is_reprocess)
            logger.info("Dispatched document %s to Celery queue via Redis.", document_id)
            return "celery"
        except Exception as e:
            logger.warning(
                "Celery dispatch failed (%s). Falling back to inline execution.", e
            )

    # Inline mode (development or fallback)
    if background_tasks is not None:
        background_tasks.add_task(_execute_processing, document_id, is_reprocess)
        logger.info("Scheduled inline BackgroundTask for document %s.", document_id)
    else:
        asyncio.create_task(_execute_processing(document_id, is_reprocess))
        logger.info("Spawned async task for document %s.", document_id)

    return "inline"


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def extract_invoices_task(self, document_id: str, extraction_run_id: str):
    """Celery task entry point for extracting invoices from a document."""
    logger.info("Executing Celery extract_invoices_task for doc ID: %s, run ID: %s", document_id, extraction_run_id)
    try:
        from app.services.extraction.service import extraction_service
        doc_uuid = uuid.UUID(document_id)
        run_uuid = uuid.UUID(extraction_run_id)
        asyncio.run(extraction_service.execute_extraction_run(doc_uuid, run_uuid))
        return {"status": "success", "document_id": document_id, "extraction_run_id": extraction_run_id}
    except Exception as exc:
        logger.error("Celery extraction task exception: %s. Retrying...", exc)
        raise self.retry(exc=exc)


def dispatch_invoice_extraction(
    document_id: uuid.UUID,
    extraction_run_id: uuid.UUID,
    background_tasks: Optional[BackgroundTasks] = None,
) -> str:
    """
    Route extraction to Celery if configured, or FastAPI BackgroundTasks for local inline dev.
    Returns: "celery" or "inline"
    """
    mode = settings.PROCESSING_MODE.lower()

    if mode == "celery":
        try:
            extract_invoices_task.delay(str(document_id), str(extraction_run_id))
            logger.info("Dispatched extraction run %s to Celery queue via Redis.", extraction_run_id)
            return "celery"
        except Exception as e:
            logger.error(
                "Celery extraction dispatch failed: %s. Not falling back to inline because PROCESSING_MODE=celery.",
                e,
                exc_info=True,
            )
            raise RuntimeError(f"Celery extraction dispatch failed: {e}") from e

    from app.services.extraction.service import extraction_service

    if background_tasks is not None:
        background_tasks.add_task(
            extraction_service.execute_extraction_run,
            document_id,
            extraction_run_id,
        )
        logger.info("Scheduled inline BackgroundTask for extraction run %s.", extraction_run_id)
    else:
        asyncio.create_task(
            extraction_service.execute_extraction_run(document_id, extraction_run_id)
        )
        logger.info("Spawned async task for extraction run %s.", extraction_run_id)

    return "inline"


async def _execute_embedding_generation(document_id: uuid.UUID):
    """Generate chunk embeddings within an isolated async database session."""
    async with async_session_maker() as session:
        try:
            from app.services.search.embedding_service import embedding_service
            await embedding_service.embed_document_chunks(session, document_id)
        except Exception as e:
            logger.warning(
                "Background embedding generation failed for document %s: %s",
                document_id,
                e,
                exc_info=True,
            )


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def generate_document_embeddings_task(self, document_id: str):
    """Celery task entry point for generating document chunk embeddings."""
    logger.info("Executing Celery generate_document_embeddings_task for doc ID: %s", document_id)
    try:
        doc_uuid = uuid.UUID(document_id)
        asyncio.run(_execute_embedding_generation(doc_uuid))
        return {"status": "success", "document_id": document_id}
    except Exception as exc:
        logger.warning("Celery embedding task exception: %s. Retrying...", exc)
        raise self.retry(exc=exc)


def dispatch_embedding_generation(
    document_id: uuid.UUID,
    background_tasks: Optional[BackgroundTasks] = None,
) -> str:
    """
    Route embedding generation to Celery if configured, or FastAPI BackgroundTasks/asyncio.
    Returns: "celery" or "inline"
    """
    mode = settings.PROCESSING_MODE.lower()

    if mode == "celery":
        try:
            generate_document_embeddings_task.delay(str(document_id))
            logger.info("Dispatched embedding task for document %s to Celery queue via Redis.", document_id)
            return "celery"
        except Exception as e:
            logger.warning(
                "Celery embedding dispatch failed: %s. Falling back to inline execution.", e
            )

    if background_tasks is not None:
        background_tasks.add_task(_execute_embedding_generation, document_id)
        logger.info("Scheduled inline BackgroundTask for embedding document %s.", document_id)
    else:
        asyncio.create_task(_execute_embedding_generation(document_id))
        logger.info("Spawned async task for embedding document %s.", document_id)

    return "inline"
