from datetime import datetime, timezone
import logging
import math
import os
import uuid
from typing import List, Optional

logger = logging.getLogger("doc_intel.api.documents")
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice
from app.models.processing_event import ProcessingEvent
from app.schemas.chunk import (
    DocumentChunkListResponse,
    DocumentChunkResponse,
    ProcessingSummaryResponse,
)
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    ProcessingEventResponse,
    RejectedDocumentResponse,
    UploadBatchResponse,
)
from app.services.document_processing.storage import storage_service
from app.services.extraction.context_models import (
    ExtractionContext,
    ExtractionContextListResponse,
    ExtractionContextSummary,
)
from app.services.extraction.context_service import context_service
from app.core.config import settings
from app.models.extraction_run import ExtractionRun, ExtractionRunStatus
from app.schemas.extraction_api import (
    DocumentInvoicesResponse,
    ExtractionHistoryResponse,
    ExtractionInitiationResponse,
    ExtractionRunResponse,
    InvoiceDetailResponse,
)
from app.services.extraction.service import extraction_service
from app.workers.celery_app import dispatch_document_processing, dispatch_invoice_extraction

router = APIRouter()


@router.post(
    "/upload",
    response_model=UploadBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload multiple financial documents",
    description="Upload multiple documents (PDF, JPG, PNG, TIFF, XLS, XLSX, CSV). Validates extensions, magic signatures, computes SHA-256, and handles partial batch success.",
)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    auto_process: bool = Query(True, description="Automatically schedule document processing upon upload"),
) -> UploadBatchResponse:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files were provided in the upload request.",
        )

    accepted_docs: List[DocumentResponse] = []
    rejected_files: List[RejectedDocumentResponse] = []
    current_batch_hashes = set()
    accepted_doc_ids: List[uuid.UUID] = []

    for file in files:
        # 1. Process and write file stream
        is_saved, doc_data, error_info = await storage_service.save_uploaded_file(file)

        if not is_saved or not doc_data:
            rejected_files.append(
                RejectedDocumentResponse(
                    filename=error_info.get("filename", file.filename or "unknown"),
                    error=error_info.get("error", "Validation failed"),
                    reason=error_info.get("reason", "File validation failed"),
                )
            )
            continue

        file_hash = doc_data["sha256_hash"]

        # 2. Check for duplicate within the current batch
        if file_hash in current_batch_hashes:
            storage_service.delete_file(doc_data["file_path"])
            rejected_files.append(
                RejectedDocumentResponse(
                    filename=doc_data["original_filename"],
                    error="Duplicate file detected",
                    reason="A file with identical content was already included in this upload batch.",
                )
            )
            continue

        # 3. Check for existing document with identical SHA-256 in database
        existing_doc = await db.scalar(
            select(Document).where(Document.sha256_hash == file_hash)
        )
        if existing_doc:
            storage_service.delete_file(doc_data["file_path"])
            rejected_files.append(
                RejectedDocumentResponse(
                    filename=doc_data["original_filename"],
                    error="Duplicate file detected",
                    reason=f"Document with identical SHA-256 hash was already uploaded (ID: {existing_doc.id}).",
                )
            )
            continue

        now = datetime.now(timezone.utc)
        # 4. Create Document record and ProcessingEvent
        document = Document(
            id=doc_data["id"],
            original_filename=doc_data["original_filename"],
            stored_filename=doc_data["stored_filename"],
            file_path=doc_data["file_path"],
            file_type=doc_data["file_type"],
            mime_type=doc_data["mime_type"],
            file_size=doc_data["file_size"],
            sha256_hash=file_hash,
            status=DocumentStatus.UPLOADED.value,
            total_chunks=0,
            extracted_characters=0,
            uploaded_at=now,
        )
        db.add(document)

        event = ProcessingEvent(
            document_id=document.id,
            event_type="upload_completed",
            message=f"Document '{document.original_filename}' uploaded successfully ({document.file_size} bytes).",
            created_at=now,
        )
        db.add(event)

        current_batch_hashes.add(file_hash)
        accepted_docs.append(DocumentResponse.model_validate(document))
        accepted_doc_ids.append(document.id)

    # Commit all accepted documents and events
    if accepted_docs:
        await db.commit()

        # Schedule background processing
        if auto_process:
            for doc_id in accepted_doc_ids:
                dispatch_document_processing(doc_id, background_tasks, is_reprocess=False)

    return UploadBatchResponse(
        accepted=accepted_docs,
        rejected=rejected_files,
        total_accepted=len(accepted_docs),
        total_rejected=len(rejected_files),
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List uploaded documents",
    description="Retrieve a paginated list of uploaded documents with optional filtering by status, file type, or search term.",
)
async def list_documents(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by document status"),
    file_type: Optional[str] = Query(None, description="Filter by file type"),
    search: Optional[str] = Query(None, description="Search by original filename"),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    query = select(Document)

    if status:
        query = query.where(Document.status == status.lower())
    if file_type:
        query = query.where(Document.file_type == file_type.lower())
    if search:
        query = query.where(Document.original_filename.ilike(f"%{search}%"))

    # Total count query
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.scalar(count_query)) or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Document.uploaded_at.desc()).offset(offset).limit(page_size)
    result = await db.scalars(query)
    items = result.all()

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document details",
    description="Retrieve full metadata, processing history, associated invoice, and validation issues for a document.",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetailResponse:
    query = (
        select(Document)
        .where(Document.id == document_id)
        .options(
            selectinload(Document.processing_events),
            selectinload(Document.invoices).selectinload(Invoice.line_items),
            selectinload(Document.invoices).selectinload(Invoice.validation_issues),
        )
    )
    document = await db.scalar(query)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    return DocumentDetailResponse.model_validate(document)


@router.post(
    "/{document_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process or reprocess document",
    description="Manually trigger or re-trigger document parsing, OCR, and chunk extraction.",
)
async def process_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    force_reprocess: bool = Query(True, description="Purge previous chunks and re-extract"),
    db: AsyncSession = Depends(get_db),
):
    document = await db.scalar(
        select(Document).where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # Dispatch to background task or Celery
    mode = dispatch_document_processing(
        document_id=document.id,
        background_tasks=background_tasks,
        is_reprocess=force_reprocess,
    )

    return {
        "status": "queued",
        "message": f"Processing scheduled for document '{document.original_filename}'.",
        "document_id": str(document_id),
        "mode": mode,
    }


@router.get(
    "/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
    summary="Get paginated document chunks",
    description="Retrieve extracted text chunks with optional filtering by source type, page number, or sheet name.",
)
async def get_document_chunks(
    document_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    source_type: Optional[str] = Query(None, description="Filter by source_type (e.g. PDF_PAGE, IMAGE, SPREADSHEET_SHEET, CSV)"),
    page_number: Optional[int] = Query(None, description="Filter by page number"),
    sheet_name: Optional[str] = Query(None, description="Filter by sheet name"),
    db: AsyncSession = Depends(get_db),
) -> DocumentChunkListResponse:
    # Verify document exists
    doc = await db.scalar(select(Document).where(Document.id == document_id))
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    query = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    if source_type:
        query = query.where(DocumentChunk.source_type == source_type.upper())
    if page_number is not None:
        query = query.where(DocumentChunk.page_number == page_number)
    if sheet_name:
        query = query.where(DocumentChunk.sheet_name == sheet_name)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.scalar(count_query)) or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(DocumentChunk.chunk_index.asc()).offset(offset).limit(page_size)
    result = await db.scalars(query)
    items = result.all()

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return DocumentChunkListResponse(
        items=[DocumentChunkResponse.model_validate(chunk) for chunk in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}/processing-summary",
    response_model=ProcessingSummaryResponse,
    summary="Get document processing summary",
    description="Retrieve extraction metrics, page/sheet counts, total chunks, character counts, and processing audit events.",
)
async def get_document_processing_summary(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProcessingSummaryResponse:
    query = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.processing_events))
    )
    document = await db.scalar(query)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    return ProcessingSummaryResponse(
        document_id=document.id,
        status=document.status,
        page_count=document.page_count,
        sheet_count=document.sheet_count,
        total_chunks=document.total_chunks,
        extracted_characters=document.extracted_characters,
        extraction_method_summary=document.extraction_method_summary,
        error_message=document.error_message,
        processed_at=document.processed_at,
        processing_events=[
            ProcessingEventResponse.model_validate(ev)
            for ev in document.processing_events
        ],
    )


@router.get(
    "/{document_id}/extraction-contexts",
    response_model=ExtractionContextListResponse,
    summary="Get prepared extraction contexts for a document",
    description="Prepares, groups, and budgets extraction contexts for a document without initiating AI extraction. Returns paginated context summaries.",
)
async def get_document_extraction_contexts(
    document_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> ExtractionContextListResponse:
    try:
        result = await context_service.prepare_document_contexts(document_id, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    total_contexts = len(result.contexts)
    total_pages = math.ceil(total_contexts / page_size) if total_contexts > 0 else 1
    offset = (page - 1) * page_size
    paged_contexts = result.contexts[offset : offset + page_size]

    items = [ExtractionContextSummary.from_context(ctx) for ctx in paged_contexts]

    return ExtractionContextListResponse(
        document_id=document_id,
        items=items,
        total=total_contexts,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_source_chunks=result.total_source_chunks,
        selected_source_chunks=result.selected_source_chunks,
        warnings=result.warnings,
    )


@router.get(
    "/{document_id}/extraction-contexts/{context_id}",
    response_model=ExtractionContext,
    summary="Get full extraction context details",
    description="Retrieve the complete prepared extraction context including full combined text, row ranges, and metadata for a specific context ID.",
)
async def get_extraction_context_detail(
    document_id: uuid.UUID,
    context_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionContext:
    try:
        result = await context_service.prepare_document_contexts(document_id, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    for ctx in result.contexts:
        if ctx.context_id == context_id:
            return ctx

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Extraction context '{context_id}' not found for document '{document_id}'.",
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document",
    description="Permanently delete a document, clean up its stored file on disk, and cascade-delete all associated database records.",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    document = await db.scalar(
        select(Document).where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # Clean up physical file from storage
    storage_service.delete_file(document.file_path)

    # Delete from database (cascades to chunks, invoice, line items, validation issues, processing events)
    await db.delete(document)
    await db.commit()

    return {
        "status": "success",
        "message": f"Document '{document.original_filename}' and associated records were deleted.",
        "id": str(document_id),
    }


@router.post(
    "/{document_id}/extract-invoices",
    response_model=ExtractionInitiationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start invoice extraction",
    description="Asynchronously initiate AI extraction of invoices from prepared document content. Queues an ExtractionRun and returns immediately with HTTP 202.",
)
async def extract_invoices(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ExtractionInitiationResponse:
    # 1. Verify document exists
    document = await db.scalar(
        select(Document).where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # 2. Verify document has usable content
    if document.status == DocumentStatus.FAILED.value and document.total_chunks == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document processing failed with no chunks available for invoice extraction.",
        )

    if document.total_chunks == 0 and document.status == DocumentStatus.UPLOADED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no extracted chunks. Run document processing first.",
        )

    # 3. Verify LLM configuration
    api_key = settings.GEMINI_API_KEY
    if not settings.LLM_ENABLED or not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM extraction is disabled or unconfigured. Verify LLM_ENABLED and GEMINI_API_KEY.",
        )

    # 4. Create ExtractionRun
    run = await extraction_service.create_extraction_run(db, document_id)

    # 5. Dispatch background processing
    try:
        mode = dispatch_invoice_extraction(document_id, run.id, background_tasks)
    except Exception as e:
        logger.error(
            "Failed to schedule extraction worker via Celery/Redis for run %s: %s",
            run.id,
            e,
            exc_info=True,
        )
        run.status = ExtractionRunStatus.FAILED.value
        run.error_message = f"Failed to dispatch extraction task: {e}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to dispatch extraction worker via Celery/Redis: {e}",
        )

    return ExtractionInitiationResponse(
        extraction_run_id=run.id,
        document_id=document_id,
        status=run.status,
        processing_mode=mode,
        message=f"Invoice extraction queued in {mode} mode.",
    )


@router.get(
    "/{document_id}/invoices",
    response_model=DocumentInvoicesResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve document invoices",
    description="Retrieve all extracted invoices belonging to the latest successful extraction run, or a specific historical run.",
)
async def get_document_invoices(
    document_id: uuid.UUID,
    extraction_run_id: Optional[uuid.UUID] = Query(
        None, description="Optional specific extraction run ID to inspect historical results"
    ),
    db: AsyncSession = Depends(get_db),
) -> DocumentInvoicesResponse:
    # 1. Verify document exists
    document = await db.scalar(
        select(Document).where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # 2. Resolve target extraction run
    target_run_id = extraction_run_id
    if target_run_id:
        run = await db.scalar(
            select(ExtractionRun).where(
                ExtractionRun.id == target_run_id,
                ExtractionRun.document_id == document_id,
            )
        )
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ExtractionRun with ID '{target_run_id}' not found for document '{document_id}'.",
            )
        query = (
            select(Invoice)
            .where(
                Invoice.document_id == document_id,
                Invoice.extraction_run_id == target_run_id,
            )
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.validation_issues),
            )
            .order_by(Invoice.created_at.asc())
        )
    else:
        # Resolve latest completed or partial run
        latest_run = await db.scalar(
            select(ExtractionRun)
            .where(
                ExtractionRun.document_id == document_id,
                ExtractionRun.status.in_(["completed", "partial"]),
            )
            .order_by(ExtractionRun.created_at.desc())
        )
        if latest_run:
            target_run_id = latest_run.id
            query = (
                select(Invoice)
                .where(
                    Invoice.document_id == document_id,
                    Invoice.extraction_run_id == target_run_id,
                )
                .options(
                    selectinload(Invoice.line_items),
                    selectinload(Invoice.validation_issues),
                )
                .order_by(Invoice.created_at.asc())
            )
        else:
            # Fallback to any invoices associated with this document
            query = (
                select(Invoice)
                .where(Invoice.document_id == document_id)
                .options(
                    selectinload(Invoice.line_items),
                    selectinload(Invoice.validation_issues),
                )
                .order_by(Invoice.created_at.asc())
            )

    invoices = (await db.execute(query)).scalars().all()
    return DocumentInvoicesResponse(
        document_id=document_id,
        extraction_run_id=target_run_id,
        total_invoices=len(invoices),
        invoices=[InvoiceDetailResponse.model_validate(inv) for inv in invoices],
    )


@router.get(
    "/{document_id}/extraction-history",
    response_model=ExtractionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document extraction history",
    description="Retrieve all extraction runs performed on this document, ordered newest first.",
)
async def get_document_extraction_history(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionHistoryResponse:
    # 1. Verify document exists
    document = await db.scalar(
        select(Document).where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # 2. Query all extraction runs ordered descending by created_at
    query = (
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
    )
    runs = (await db.execute(query)).scalars().all()

    return ExtractionHistoryResponse(
        document_id=document_id,
        total_runs=len(runs),
        runs=[ExtractionRunResponse.model_validate(r) for r in runs],
    )


@router.get(
    "/{document_id}/file",
    status_code=status.HTTP_200_OK,
    summary="Download or view raw document file",
    description="Streams the raw uploaded document file from disk.",
)
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    document = await db.scalar(
        select(Document).where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    if not document.file_path or not os.path.exists(document.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found on server disk.",
        )

    return FileResponse(
        path=document.file_path,
        media_type=document.mime_type or "application/octet-stream",
        filename=document.original_filename,
    )
