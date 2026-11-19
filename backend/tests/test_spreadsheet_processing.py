import csv
from pathlib import Path
import openpyxl
import pytest
from app.services.document_processing.spreadsheet_processor import (
    SpreadsheetProcessingError,
    SpreadsheetProcessor,
)


@pytest.fixture
def multi_sheet_xlsx(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    # Sheet 1: Orders (visible)
    ws1 = wb.active
    ws1.title = "Orders"
    ws1.append(["Order ID", "Customer", "Amount"])
    for i in range(1, 10):
        ws1.append([f"ORD-{i}", f"Client {i}", i * 150.0])

    # Sheet 2: Expenses (hidden)
    ws2 = wb.create_sheet(title="Expenses")
    ws2.sheet_state = "hidden"
    ws2.append(["Expense ID", "Category", "Amount"])
    ws2.append(["EXP-01", "Hosting", 450.0])

    # Sheet 3: Audit (veryHidden)
    ws3 = wb.create_sheet(title="Audit")
    ws3.sheet_state = "veryHidden"
    ws3.append(["Audit ID", "Internal Notes"])
    ws3.append(["AUD-99", "Sensitive compliance data"])

    # Sheet 4: EmptySheet
    wb.create_sheet(title="EmptySheet")

    path = tmp_path / "multi_sheet.xlsx"
    wb.save(str(path))
    wb.close()
    return path


@pytest.fixture
def large_xlsx(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(["ID", "Description", "Value"])
    for i in range(1, 125):  # 124 data rows
        ws.append([f"TX-{i}", f"Transaction {i}", i * 10])
    path = tmp_path / "large.xlsx"
    wb.save(str(path))
    wb.close()
    return path


def test_xlsx_multiple_sheets_and_hidden_sheets_included_by_default(
    multi_sheet_xlsx: Path,
) -> None:
    # Default configuration: include_hidden_sheets=True
    processor = SpreadsheetProcessor(chunk_row_size=50, include_hidden_sheets=True)
    gen = processor.extract_xlsx_chunks(multi_sheet_xlsx)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        sheet_count, warnings, errors = stop.value

    assert sheet_count == 4
    # Check all sheet names are extracted into chunks
    sheet_names = [c["sheet_name"] for c in chunks]
    assert "Orders" in sheet_names
    assert "Expenses" in sheet_names
    assert "Audit" in sheet_names
    assert "EmptySheet" in sheet_names

    # Check warnings indicate they were included
    assert any("expenses" in w.lower() for w in warnings)
    assert any("audit" in w.lower() for w in warnings)


def test_xlsx_hidden_and_very_hidden_sheets_skipped_when_configured_false(
    multi_sheet_xlsx: Path,
) -> None:
    # When include_hidden_sheets=False, hidden and veryHidden worksheets must be skipped
    processor = SpreadsheetProcessor(chunk_row_size=50, include_hidden_sheets=False)
    gen = processor.extract_xlsx_chunks(multi_sheet_xlsx)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        sheet_count, warnings, errors = stop.value

    assert sheet_count == 4
    sheet_names = [c["sheet_name"] for c in chunks]
    assert "Orders" in sheet_names
    assert "EmptySheet" in sheet_names
    assert "Expenses" not in sheet_names
    assert "Audit" not in sheet_names

    # Check warnings state they were skipped
    assert any("skipped" in w.lower() and "expenses" in w.lower() for w in warnings)
    assert any("skipped" in w.lower() and "audit" in w.lower() for w in warnings)


def test_xlsx_row_chunking(large_xlsx: Path) -> None:
    # 124 rows with chunk size 50 -> 3 chunks (50, 50, 24)
    processor = SpreadsheetProcessor(chunk_row_size=50)
    gen = processor.extract_xlsx_chunks(large_xlsx)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        sheet_count, warnings, errors = stop.value

    assert sheet_count == 1
    assert len(chunks) == 3
    assert chunks[0]["row_start"] == 2
    assert chunks[0]["row_end"] == 51
    assert chunks[1]["row_start"] == 52
    assert chunks[1]["row_end"] == 101
    assert chunks[2]["row_start"] == 102
    assert chunks[2]["row_end"] == 125


def test_csv_utf8_and_quoted_commas(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Invoice", "Description", "Total"])
        writer.writerow(["INV-001", "Consulting, engineering and cloud design", "5000.00"])
        writer.writerow(["INV-002", "Hardware, server maintenance", "3500.00"])

    processor = SpreadsheetProcessor(chunk_row_size=50)
    gen = processor.extract_csv_chunks(path)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        sheet_count, warnings, errors = stop.value

    assert sheet_count == 1
    assert len(chunks) == 1
    content = chunks[0]["content"]
    assert "INV-001" in content
    assert "Consulting, engineering and cloud design" in content


def test_csv_utf8_bom_and_semicolon_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "bom_data.csv"
    content = "\ufeffOrder;Product;Price\nORD-1;Laptop;1200\nORD-2;Monitor;400\n"
    path.write_text(content, encoding="utf-8-sig")

    processor = SpreadsheetProcessor()
    gen = processor.extract_csv_chunks(path)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        sheet_count, warnings, errors = stop.value

    assert sheet_count == 1
    assert len(chunks) == 1
    assert "ORD-1" in chunks[0]["content"]
    assert "Laptop" in chunks[0]["content"]


def test_csv_windows_cp1252_encoding(tmp_path: Path) -> None:
    path = tmp_path / "cp1252.csv"
    # Write euro symbol in cp1252 (0x80)
    data = b"Item,Price\nCoffee,2.50 \x80\nTea,1.80 \x80\n"
    path.write_bytes(data)

    processor = SpreadsheetProcessor()
    gen = processor.extract_csv_chunks(path)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        sheet_count, warnings, errors = stop.value

    assert sheet_count == 1
    assert len(chunks) == 1
    assert "Coffee" in chunks[0]["content"]


def test_empty_csv_handling(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    processor = SpreadsheetProcessor()
    gen = processor.extract_csv_chunks(path)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        sheet_count, warnings, errors = stop.value

    assert sheet_count == 1
    assert len(chunks) == 1
    assert "Empty CSV file" in chunks[0]["content"]


def test_corrupted_xlsx_handling(tmp_path: Path) -> None:
    corrupted_path = tmp_path / "corrupt.xlsx"
    corrupted_path.write_bytes(b"PK\x03\x04corrupted binary not real zip xlsx")

    processor = SpreadsheetProcessor()
    gen = processor.extract_xlsx_chunks(corrupted_path)
    with pytest.raises(SpreadsheetProcessingError):
        next(gen)
