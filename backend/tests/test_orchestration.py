import uuid
from pathlib import Path
import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.services.document_processing.orchestrator import document_processor


@pytest.mark.asyncio
async def test_successful_pdf_document_orchestration(
    tmp_path: Path, client
) -> None:
    # 1. Create PDF file with realistic invoice text (> 50 chars per page)
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text(
        (50, 72),
        "Page 1: Acme Corp Invoice #INV-2026-AAA. Billed to Global Logistics Inc. Subtotal: $1,000.00, Tax: $200.00, Total: $1,200.00",
        fontsize=12,
    )
    page2 = doc.new_page()
    page2.insert_text(
        (50, 72),
        "Page 2: Standard terms and conditions for wire transfer payment within 30 business days. Thank you for your business.",
        fontsize=12,
    )
    pdf_path = tmp_path / "test_invoice.pdf"
    doc.save(str(pdf_path))
    doc.close()

    # 2. Get DB session
    from app.db.session import async_session_maker
    async with async_session_maker() as session:
        doc_uuid = uuid.uuid4()
        document = Document(
            id=doc_uuid,
            original_filename="test_invoice.pdf",
            stored_filename=f"{doc_uuid}.pdf",
            file_path=str(pdf_path),
            file_type="pdf",
            mime_type="application/pdf",
            file_size=pdf_path.stat().st_size,
            sha256_hash=f"dummyhash_orchestration_{doc_uuid}",
            status=DocumentStatus.UPLOADED.value,
            total_chunks=0,
            extracted_characters=0,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        doc_id = document.id

        # 3. Process document
        processed = await document_processor.process_document(doc_id, session)

        assert processed.status == DocumentStatus.COMPLETED.value
        assert processed.page_count == 2
        assert processed.total_chunks == 2
        assert processed.extracted_characters > 0
        assert "DIGITAL_TEXT" in processed.extraction_method_summary

        # Verify chunks in DB
        chunks = (
            await session.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
            )
        ).all()
        assert len(chunks) == 2
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert "Page 1" in chunks[0].content
        assert "Page 2" in chunks[1].content


@pytest.mark.asyncio
async def test_reprocessing_purges_previous_chunks(tmp_path: Path, client) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Single page initial extraction", fontsize=12)
    pdf_path = tmp_path / "reprocess_test.pdf"
    doc.save(str(pdf_path))
    doc.close()

    from app.db.session import async_session_maker
    async with async_session_maker() as session:
        doc_uuid = uuid.uuid4()
        document = Document(
            id=doc_uuid,
            original_filename="reprocess_test.pdf",
            stored_filename=f"{doc_uuid}.pdf",
            file_path=str(pdf_path),
            file_type="pdf",
            mime_type="application/pdf",
            file_size=pdf_path.stat().st_size,
            sha256_hash=f"dummyhash_reprocess_{doc_uuid}",
            status=DocumentStatus.UPLOADED.value,
            total_chunks=0,
            extracted_characters=0,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        doc_id = document.id

        # First processing
        await document_processor.process_document(doc_id, session)
        chunks_1 = (
            await session.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
            )
        ).all()
        assert len(chunks_1) == 1

        # Second processing (reprocessing)
        await document_processor.process_document(doc_id, session, is_reprocess=True)
        chunks_2 = (
            await session.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
            )
        ).all()
        # Ensure no duplicate chunks were created
        assert len(chunks_2) == 1


@pytest.mark.asyncio
async def test_missing_file_sets_failed_status(tmp_path: Path, client) -> None:
    from app.db.session import async_session_maker
    async with async_session_maker() as session:
        doc_uuid = uuid.uuid4()
        document = Document(
            id=doc_uuid,
            original_filename="ghost.pdf",
            stored_filename=f"{doc_uuid}.pdf",
            file_path=str(tmp_path / "nonexistent_ghost_file.pdf"),
            file_type="pdf",
            mime_type="application/pdf",
            file_size=100,
            sha256_hash=f"dummyhash_ghost_{doc_uuid}",
            status=DocumentStatus.UPLOADED.value,
            total_chunks=0,
            extracted_characters=0,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)

        with pytest.raises(FileNotFoundError):
            await document_processor.process_document(document.id, session)

        await session.refresh(document)
        assert document.status == DocumentStatus.FAILED.value
        assert "missing" in document.error_message.lower()
