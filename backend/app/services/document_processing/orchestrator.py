import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.models.processing_event import ProcessingEvent
from app.services.document_processing.image_processor import image_processor
from app.services.document_processing.pdf_processor import pdf_processor
from app.services.document_processing.spreadsheet_processor import (
    spreadsheet_processor,
)

logger = logging.getLogger("doc_intel.processor")


class DocumentProcessor:
    CHUNK_COMMIT_BATCH_SIZE = 50

    async def process_document(
        self,
        document_id: uuid.UUID | str,
        db: AsyncSession,
        is_reprocess: bool = False,
    ) -> Document:
        """
        Orchestrate end-to-end document text and tabular extraction.
        Extracts chunks, saves them incrementally to DB, and updates status transitions.
        """
        if isinstance(document_id, str):
            document_id = uuid.UUID(document_id)

        # 1. Fetch document record
        document = await db.scalar(
            select(Document).where(Document.id == document_id)
        )
        if not document:
            raise ValueError(f"Document with ID '{document_id}' not found.")

        # 2. Verify stored file exists
        file_path = Path(document.file_path)
        if not file_path.exists() or not file_path.is_file():
            document.status = DocumentStatus.FAILED.value
            document.error_message = f"Physical file missing at '{document.file_path}'."
            event = ProcessingEvent(
                document_id=document.id,
                event_type="error",
                message=document.error_message,
            )
            db.add(event)
            await db.commit()
            raise FileNotFoundError(document.error_message)

        # 3. Handle reprocessing cleanup
        if is_reprocess:
            logger.info("Reprocessing document %s: purging existing chunks.", document.id)
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
            db.add(
                ProcessingEvent(
                    document_id=document.id,
                    event_type="reprocessing_started",
                    message="Manual reprocessing initiated. Existing chunks removed.",
                )
            )
        else:
            db.add(
                ProcessingEvent(
                    document_id=document.id,
                    event_type="processing_started",
                    message=f"Processing started for {document.file_type.upper()} document.",
                )
            )

        # 4. Transition status to processing
        document.status = DocumentStatus.PROCESSING.value
        document.error_message = None
        await db.commit()

        # 5. Dispatch to appropriate extraction service
        file_type = document.file_type.lower()
        chunk_dicts: List[Dict[str, Any]] = []
        warnings: List[str] = []
        errors: List[str] = []
        page_count: Optional[int] = None
        sheet_count: Optional[int] = None
        extraction_methods = set()

        try:
            if file_type == "pdf":
                generator = pdf_processor.extract_chunks(file_path)
                try:
                    while True:
                        chunk_dicts.append(next(generator))
                except StopIteration as stop:
                    page_count, warnings, errors = stop.value

            elif file_type in ["jpg", "jpeg", "png", "tiff", "tif"]:
                generator = image_processor.extract_chunks(file_path, file_type)
                try:
                    while True:
                        chunk_dicts.append(next(generator))
                except StopIteration as stop:
                    page_count, warnings, errors = stop.value

            elif file_type == "xlsx":
                generator = spreadsheet_processor.extract_xlsx_chunks(file_path)
                try:
                    while True:
                        chunk_dicts.append(next(generator))
                except StopIteration as stop:
                    sheet_count, warnings, errors = stop.value

            elif file_type == "xls":
                generator = spreadsheet_processor.extract_xls_chunks(file_path)
                try:
                    while True:
                        chunk_dicts.append(next(generator))
                except StopIteration as stop:
                    sheet_count, warnings, errors = stop.value

            elif file_type == "csv":
                generator = spreadsheet_processor.extract_csv_chunks(file_path)
                try:
                    while True:
                        chunk_dicts.append(next(generator))
                except StopIteration as stop:
                    sheet_count, warnings, errors = stop.value

            else:
                raise ValueError(f"Unsupported file type for processing: {file_type}")

            # 6. Save chunks in batches
            total_chars = 0
            for i, chunk_data in enumerate(chunk_dicts):
                total_chars += len(chunk_data["content"])
                extraction_methods.add(chunk_data["extraction_method"])

                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_data["chunk_index"],
                    source_type=chunk_data["source_type"],
                    page_number=chunk_data.get("page_number"),
                    sheet_name=chunk_data.get("sheet_name"),
                    row_start=chunk_data.get("row_start"),
                    row_end=chunk_data.get("row_end"),
                    content=chunk_data["content"],
                    extraction_method=chunk_data["extraction_method"],
                    ocr_confidence=chunk_data.get("ocr_confidence"),
                    chunk_metadata=chunk_data.get("metadata", {}),
                )
                db.add(chunk)

                if (i + 1) % self.CHUNK_COMMIT_BATCH_SIZE == 0:
                    await db.flush()

            # 7. Update extraction metrics on Document
            document.page_count = page_count
            document.sheet_count = sheet_count
            document.total_chunks = len(chunk_dicts)
            document.extracted_characters = total_chars
            document.extraction_method_summary = ", ".join(sorted(extraction_methods))
            document.processed_at = datetime.now(timezone.utc)

            # 8. Determine final processing status
            if len(chunk_dicts) == 0 or (errors and len(chunk_dicts) == len(errors)):
                document.status = DocumentStatus.FAILED.value
                document.error_message = (
                    "; ".join(errors) if errors else "No content could be extracted from document."
                )
                db.add(
                    ProcessingEvent(
                        document_id=document.id,
                        event_type="processing_failed",
                        message=f"Processing failed: {document.error_message}",
                    )
                )
            elif warnings or errors:
                # Extracted some content, but had warnings (e.g. OCR unavailable for some pages)
                document.status = DocumentStatus.NEEDS_REVIEW.value
                combined_notes = "; ".join(warnings + errors)
                document.error_message = combined_notes
                db.add(
                    ProcessingEvent(
                        document_id=document.id,
                        event_type="processing_needs_review",
                        message=f"Processing completed with warnings ({len(chunk_dicts)} chunks): {combined_notes}",
                    )
                )
            else:
                document.status = DocumentStatus.COMPLETED.value
                db.add(
                    ProcessingEvent(
                        document_id=document.id,
                        event_type="processing_completed",
                        message=(
                            f"Extraction completed successfully. Extracted {len(chunk_dicts)} chunks "
                            f"({total_chars} characters) via {document.extraction_method_summary}."
                        ),
                    )
                )

            await db.commit()
            await db.refresh(document)

            # Non-blocking chunk embedding generation for search
            # Executes within session to avoid SQLite cross-thread write lock contention.
            if document.status in (DocumentStatus.COMPLETED.value, DocumentStatus.NEEDS_REVIEW.value):
                try:
                    from app.services.search.embedding_service import embedding_service
                    await embedding_service.embed_document_chunks(db, document.id)
                except Exception as emb_err:
                    logger.warning(
                        "Background embedding generation skipped for document %s: %s",
                        document.id,
                        str(emb_err),
                    )

            return document


        except Exception as e:
            logger.error("Processing failed for document %s: %s", document.id, str(e), exc_info=True)
            document.status = DocumentStatus.FAILED.value
            document.error_message = str(e)
            document.processed_at = datetime.now(timezone.utc)
            db.add(
                ProcessingEvent(
                    document_id=document.id,
                    event_type="processing_failed",
                    message=f"Fatal processing error: {str(e)}",
                )
            )
            await db.commit()
            await db.refresh(document)
            return document



document_processor = DocumentProcessor()
