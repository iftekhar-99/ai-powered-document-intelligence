import io
from pathlib import Path
import pytest
import pymupdf
from app.services.document_processing.pdf_processor import (
    PDFProcessingError,
    PDFProcessor,
)


@pytest.fixture
def digital_pdf_path(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Financial Report Q3\nInvoice: INV-2026-001\nTotal: $12,500.00", fontsize=12)
    path = tmp_path / "digital.pdf"
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def multipage_pdf_path(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    for i in range(1, 4):
        page = doc.new_page()
        page.insert_text(
            (50, 72),
            f"Page {i} Header\nLine item description for transaction {i * 100}.\nSubtotal: ${i * 500}.00",
            fontsize=12,
        )
    path = tmp_path / "multipage.pdf"
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def empty_pdf_path(tmp_path: Path) -> Path:
    empty_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
        b"trailer << /Size 3 /Root 1 0 R >>\nstartxref\n115\n%%EOF"
    )
    path = tmp_path / "empty.pdf"
    path.write_bytes(empty_pdf)
    return path


@pytest.fixture
def encrypted_pdf_path(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Secret Financial Data", fontsize=12)
    path = tmp_path / "encrypted.pdf"
    doc.save(
        str(path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="password123",
        owner_pw="owner123",
    )
    doc.close()
    return path


def test_digital_pdf_extraction(digital_pdf_path: Path) -> None:
    processor = PDFProcessor(min_text_chars=10)
    gen = processor.extract_chunks(digital_pdf_path)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        page_count, warnings, errors = stop.value

    assert page_count == 1
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["page_number"] == 1
    assert chunk["source_type"] == "PDF_PAGE"
    assert chunk["extraction_method"] == "DIGITAL_TEXT"
    assert "INV-2026-001" in chunk["content"]
    assert len(errors) == 0


def test_multipage_pdf_extraction_and_page_numbering(multipage_pdf_path: Path) -> None:
    processor = PDFProcessor(min_text_chars=10)
    gen = processor.extract_chunks(multipage_pdf_path)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        page_count, warnings, errors = stop.value

    assert page_count == 3
    assert len(chunks) == 3
    for idx, chunk in enumerate(chunks):
        expected_page = idx + 1
        assert chunk["page_number"] == expected_page
        assert chunk["chunk_index"] == idx
        assert f"Page {expected_page} Header" in chunk["content"]


def test_empty_pdf_detection(empty_pdf_path: Path) -> None:
    processor = PDFProcessor()
    gen = processor.extract_chunks(empty_pdf_path)
    with pytest.raises(PDFProcessingError, match="0 pages"):
        next(gen)


def test_encrypted_pdf_detection(encrypted_pdf_path: Path) -> None:
    processor = PDFProcessor()
    gen = processor.extract_chunks(encrypted_pdf_path)
    with pytest.raises(PDFProcessingError, match="encrypted or password-protected"):
        next(gen)


def test_corrupted_pdf_handling(tmp_path: Path) -> None:
    corrupted_path = tmp_path / "corrupted.pdf"
    corrupted_path.write_bytes(b"%PDF-1.4\nCorrupted binary rubbish that cannot be parsed by poppler or mupdf")
    processor = PDFProcessor()
    gen = processor.extract_chunks(corrupted_path)
    with pytest.raises(PDFProcessingError):
        next(gen)


def test_scanned_pdf_page_handling(tmp_path: Path) -> None:
    # A PDF page with no text (only blank/image)
    doc = pymupdf.open()
    doc.new_page()  # Blank page
    path = tmp_path / "scanned_blank.pdf"
    doc.save(str(path))
    doc.close()

    processor = PDFProcessor(min_text_chars=50)
    gen = processor.extract_chunks(path)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        page_count, warnings, errors = stop.value

    assert page_count == 1
    assert len(chunks) == 1
    # When OCR is unavailable or blank, chunk should still be produced with warning
    assert chunks[0]["page_number"] == 1
