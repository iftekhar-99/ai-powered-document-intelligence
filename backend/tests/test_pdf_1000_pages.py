import time
from pathlib import Path
import pymupdf
import pytest
from app.services.document_processing.pdf_processor import PDFProcessor


def test_1000_page_synthetic_pdf_stress_and_streaming(tmp_path: Path) -> None:
    """
    Performance test: verify that a 1,000-page PDF can be generated, opened,
    and streamed page-by-page without loading all text into a single memory string.
    Records actual wall-clock processing measurements.
    """
    pdf_path = tmp_path / "synthetic_1000_pages.pdf"

    # 1. Generate lightweight 1,000-page synthetic document
    gen_start = time.perf_counter()
    doc = pymupdf.open()
    for i in range(1000):
        page = doc.new_page(width=595, height=842)  # Standard A4
        page.insert_text(
            (50, 100),
            f"Financial Ledger Record Page {i + 1}\nTransaction ID: TX-{10000 + i}\nAmount: ${float(i + 1) * 12.50}",
            fontsize=10,
        )
    doc.save(str(pdf_path))
    doc.close()
    gen_time_s = time.perf_counter() - gen_start

    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
    print(f"\n[PERF MEASUREMENT] 1,000-page synthetic PDF generated in {gen_time_s:.2f}s ({file_size_mb:.2f} MB)")

    # 2. Process and extract chunks page-by-page using streaming generator
    processor = PDFProcessor(min_text_chars=10)
    proc_start = time.perf_counter()
    gen = processor.extract_chunks(pdf_path)

    extracted_count = 0
    total_characters = 0

    try:
        while True:
            chunk = next(gen)
            extracted_count += 1
            total_characters += len(chunk["content"])
            assert chunk["page_number"] == extracted_count
            assert chunk["source_type"] == "PDF_PAGE"
            assert chunk["extraction_method"] == "DIGITAL_TEXT"
    except StopIteration as stop:
        page_count, warnings, errors = stop.value

    proc_time_s = time.perf_counter() - proc_start
    throughput_pages_per_sec = extracted_count / proc_time_s if proc_time_s > 0 else 0

    print(
        f"[PERF MEASUREMENT] Streamed and processed {extracted_count} pages in {proc_time_s:.2f}s "
        f"({throughput_pages_per_sec:.1f} pages/sec, {total_characters} chars total)"
    )

    # 3. Assertions
    assert page_count == 1000
    assert extracted_count == 1000
    assert len(errors) == 0
    assert proc_time_s < 15.0, f"Expected 1,000 pages to process within 15 seconds, took {proc_time_s:.2f}s"
