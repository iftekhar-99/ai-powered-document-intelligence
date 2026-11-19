import csv
import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
import openpyxl
import xlrd
from app.core.config import settings

logger = logging.getLogger("doc_intel.spreadsheet")


class SpreadsheetProcessingError(Exception):
    """Raised when a spreadsheet cannot be parsed or is corrupted."""
    pass


class SpreadsheetProcessor:
    def __init__(
        self,
        chunk_row_size: Optional[int] = None,
        include_hidden_sheets: Optional[bool] = None,
    ):
        self.chunk_row_size = (
            chunk_row_size or settings.SPREADSHEET_CHUNK_ROW_SIZE
        )
        self.include_hidden_sheets = (
            include_hidden_sheets
            if include_hidden_sheets is not None
            else settings.INCLUDE_HIDDEN_SHEETS
        )

    def format_table_chunk(
        self,
        sheet_name: str,
        row_start: int,
        row_end: int,
        headers: List[str],
        rows: List[List[Any]],
    ) -> str:
        """
        Format a slice of tabular rows into clear, structured text optimized for downstream LLM reasoning.
        """
        lines = [
            f"Sheet: {sheet_name}",
            f"Rows: {row_start}-{row_end}",
            "",
            f"Columns: {' | '.join(str(h) for h in headers)}",
            "",
        ]
        for idx, row in enumerate(rows):
            row_num = row_start + idx
            formatted_cells = [
                str(c) if c is not None and str(c).strip() != "" else "-"
                for c in row
            ]
            lines.append(f"Row {row_num}: {' | '.join(formatted_cells)}")

        return "\n".join(lines)

    def extract_xlsx_chunks(
        self, file_path: str | Path
    ) -> Generator[Dict[str, Any], None, Tuple[int, List[str], List[str]]]:
        """
        Stream process XLSX workbooks using OpenPyXL with read_only=True and data_only=True.
        Yields chunk dictionary per row batch per sheet.
        """
        path = Path(file_path)
        if not path.exists():
            raise SpreadsheetProcessingError(f"File not found: '{file_path}'")

        warnings: List[str] = []
        errors: List[str] = []
        global_chunk_idx = 0
        sheets_processed = 0

        try:
            wb = openpyxl.load_workbook(
                str(path), read_only=True, data_only=True
            )
        except Exception as e:
            raise SpreadsheetProcessingError(
                f"Failed to open Excel workbook '{path.name}': {str(e)}"
            )

        try:
            sheet_names = wb.sheetnames
            sheets_processed = len(sheet_names)
            if sheets_processed == 0:
                raise SpreadsheetProcessingError("Workbook contains no worksheets.")

            for sheet_name in sheet_names:
                try:
                    ws = wb[sheet_name]
                    sheet_state = getattr(ws, "sheet_state", "visible")
                    is_hidden = str(sheet_state).lower() in ["hidden", "veryhidden"]
                    if is_hidden:
                        if not self.include_hidden_sheets:
                            warnings.append(
                                f"Worksheet '{sheet_name}' is {sheet_state} and was skipped (INCLUDE_HIDDEN_SHEETS=False)."
                            )
                            continue
                        else:
                            warnings.append(
                                f"Worksheet '{sheet_name}' is marked as {sheet_state} (included)."
                            )

                    rows_iter = ws.iter_rows(values_only=True)
                    # Extract header row
                    header_row = None
                    for r in rows_iter:
                        if any(cell is not None and str(cell).strip() != "" for cell in r):
                            header_row = [
                                str(c).strip() if c is not None else f"Column_{i+1}"
                                for i, c in enumerate(r)
                            ]
                            break

                    if header_row is None:
                        # Empty worksheet
                        yield {
                            "chunk_index": global_chunk_idx,
                            "source_type": "SPREADSHEET_SHEET",
                            "page_number": None,
                            "sheet_name": sheet_name,
                            "row_start": 0,
                            "row_end": 0,
                            "content": f"Sheet: {sheet_name}\n[Empty Worksheet: 0 rows]",
                            "extraction_method": "TABULAR_PARSER",
                            "ocr_confidence": None,
                            "metadata": {
                                "sheet_name": sheet_name,
                                "is_hidden": is_hidden,
                                "total_rows": 0,
                                "char_count": len(f"Sheet: {sheet_name}\n[Empty Worksheet: 0 rows]"),
                            },
                        }
                        global_chunk_idx += 1
                        continue

                    # Stream data rows in batches of chunk_row_size
                    current_batch: List[List[Any]] = []
                    current_row_num = 2  # 1 was header
                    batch_start_row = 2

                    for r in rows_iter:
                        # Skip completely empty rows
                        if not any(cell is not None and str(cell).strip() != "" for cell in r):
                            current_row_num += 1
                            continue

                        current_batch.append(list(r))
                        if len(current_batch) >= self.chunk_row_size:
                            row_end = current_row_num
                            content = self.format_table_chunk(
                                sheet_name,
                                batch_start_row,
                                row_end,
                                header_row,
                                current_batch,
                            )
                            yield {
                                "chunk_index": global_chunk_idx,
                                "source_type": "SPREADSHEET_SHEET",
                                "page_number": None,
                                "sheet_name": sheet_name,
                                "row_start": batch_start_row,
                                "row_end": row_end,
                                "content": content,
                                "extraction_method": "TABULAR_PARSER",
                                "ocr_confidence": None,
                                "metadata": {
                                    "sheet_name": sheet_name,
                                    "is_hidden": is_hidden,
                                    "row_count": len(current_batch),
                                    "char_count": len(content),
                                    "columns": header_row,
                                },
                            }
                            global_chunk_idx += 1
                            current_batch = []
                            batch_start_row = current_row_num + 1

                        current_row_num += 1

                    # Yield final remaining rows if any
                    if current_batch:
                        row_end = current_row_num - 1
                        content = self.format_table_chunk(
                            sheet_name,
                            batch_start_row,
                            row_end,
                            header_row,
                            current_batch,
                        )
                        yield {
                            "chunk_index": global_chunk_idx,
                            "source_type": "SPREADSHEET_SHEET",
                            "page_number": None,
                            "sheet_name": sheet_name,
                            "row_start": batch_start_row,
                            "row_end": row_end,
                            "content": content,
                            "extraction_method": "TABULAR_PARSER",
                            "ocr_confidence": None,
                            "metadata": {
                                "sheet_name": sheet_name,
                                "is_hidden": is_hidden,
                                "row_count": len(current_batch),
                                "char_count": len(content),
                                "columns": header_row,
                            },
                        }
                        global_chunk_idx += 1

                except Exception as sheet_err:
                    err_msg = f"Error processing sheet '{sheet_name}': {str(sheet_err)}"
                    logger.error(err_msg, exc_info=True)
                    errors.append(err_msg)

            return sheets_processed, warnings, errors

        finally:
            wb.close()

    def extract_xls_chunks(
        self, file_path: str | Path
    ) -> Generator[Dict[str, Any], None, Tuple[int, List[str], List[str]]]:
        """
        Process legacy XLS spreadsheets using xlrd.
        """
        path = Path(file_path)
        if not path.exists():
            raise SpreadsheetProcessingError(f"File not found: '{file_path}'")

        warnings: List[str] = []
        errors: List[str] = []
        global_chunk_idx = 0

        try:
            wb = xlrd.open_workbook(str(path))
        except Exception as e:
            raise SpreadsheetProcessingError(
                f"Failed to open legacy XLS workbook '{path.name}': {str(e)}"
            )

        sheet_names = wb.sheet_names()
        sheets_processed = len(sheet_names)
        if sheets_processed == 0:
            raise SpreadsheetProcessingError("XLS workbook contains no sheets.")

        for sheet_name in sheet_names:
            try:
                ws = wb.sheet_by_name(sheet_name)
                visibility = getattr(ws, "visibility", 0)
                is_hidden = visibility != 0
                sheet_state = "hidden" if visibility == 1 else ("veryHidden" if visibility == 2 else "visible")
                if is_hidden:
                    if not self.include_hidden_sheets:
                        warnings.append(
                            f"Worksheet '{sheet_name}' is {sheet_state} and was skipped (INCLUDE_HIDDEN_SHEETS=False)."
                        )
                        continue
                    else:
                        warnings.append(
                            f"Worksheet '{sheet_name}' is marked as {sheet_state} (included)."
                        )
                total_rows = ws.nrows
                total_cols = ws.ncols

                if total_rows == 0:
                    yield {
                        "chunk_index": global_chunk_idx,
                        "source_type": "SPREADSHEET_SHEET",
                        "page_number": None,
                        "sheet_name": sheet_name,
                        "row_start": 0,
                        "row_end": 0,
                        "content": f"Sheet: {sheet_name}\n[Empty Worksheet: 0 rows]",
                        "extraction_method": "TABULAR_PARSER",
                        "ocr_confidence": None,
                        "metadata": {
                            "sheet_name": sheet_name,
                            "total_rows": 0,
                            "char_count": len(f"Sheet: {sheet_name}\n[Empty Worksheet: 0 rows]"),
                        },
                    }
                    global_chunk_idx += 1
                    continue

                # Header row
                header_row = [
                    str(ws.cell_value(0, c)).strip() or f"Column_{c+1}"
                    for c in range(total_cols)
                ]

                # Process data rows in slices
                data_row_start = 1
                while data_row_start < total_rows:
                    data_row_end = min(
                        data_row_start + self.chunk_row_size, total_rows
                    )
                    batch_rows = []
                    for r_idx in range(data_row_start, data_row_end):
                        row_vals = [
                            ws.cell_value(r_idx, c) for c in range(total_cols)
                        ]
                        if any(
                            v is not None and str(v).strip() != "" for v in row_vals
                        ):
                            batch_rows.append(row_vals)

                    if batch_rows:
                        content = self.format_table_chunk(
                            sheet_name,
                            data_row_start + 1,
                            data_row_end,
                            header_row,
                            batch_rows,
                        )
                        yield {
                            "chunk_index": global_chunk_idx,
                            "source_type": "SPREADSHEET_SHEET",
                            "page_number": None,
                            "sheet_name": sheet_name,
                            "row_start": data_row_start + 1,
                            "row_end": data_row_end,
                            "content": content,
                            "extraction_method": "TABULAR_PARSER",
                            "ocr_confidence": None,
                            "metadata": {
                                "sheet_name": sheet_name,
                                "row_count": len(batch_rows),
                                "char_count": len(content),
                                "columns": header_row,
                            },
                        }
                        global_chunk_idx += 1

                    data_row_start = data_row_end

            except Exception as se:
                err_msg = f"Error reading XLS sheet '{sheet_name}': {str(se)}"
                errors.append(err_msg)

        return sheets_processed, warnings, errors

    def extract_csv_chunks(
        self, file_path: str | Path
    ) -> Generator[Dict[str, Any], None, Tuple[int, List[str], List[str]]]:
        """
        Process CSV files supporting encodings (UTF-8, UTF-8 BOM, Windows-1252, Latin-1)
        and delimiters (, ; \t |).
        """
        path = Path(file_path)
        if not path.exists():
            raise SpreadsheetProcessingError(f"File not found: '{file_path}'")

        warnings: List[str] = []
        errors: List[str] = []
        global_chunk_idx = 0

        # 1. Detect encoding and delimiter
        encoding, delimiter = self._detect_csv_format(path)

        try:
            with open(path, "r", encoding=encoding, errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)

                # Find header
                header_row = None
                for row in reader:
                    if any(cell.strip() for cell in row):
                        header_row = [
                            c.strip() if c.strip() else f"Column_{i+1}"
                            for i, c in enumerate(row)
                        ]
                        break

                if header_row is None:
                    # Empty CSV file
                    yield {
                        "chunk_index": 0,
                        "source_type": "CSV",
                        "page_number": None,
                        "sheet_name": "CSV",
                        "row_start": 0,
                        "row_end": 0,
                        "content": "Sheet: CSV\n[Empty CSV file: 0 rows]",
                        "extraction_method": "TABULAR_PARSER",
                        "ocr_confidence": None,
                        "metadata": {
                            "encoding": encoding,
                            "delimiter": delimiter,
                            "row_count": 0,
                            "char_count": len("Sheet: CSV\n[Empty CSV file: 0 rows]"),
                        },
                    }
                    return 1, warnings, errors

                current_batch: List[List[Any]] = []
                current_row_num = 2
                batch_start_row = 2

                for row in reader:
                    if not any(cell.strip() for cell in row):
                        current_row_num += 1
                        continue

                    current_batch.append(row)
                    if len(current_batch) >= self.chunk_row_size:
                        row_end = current_row_num
                        content = self.format_table_chunk(
                            "CSV",
                            batch_start_row,
                            row_end,
                            header_row,
                            current_batch,
                        )
                        yield {
                            "chunk_index": global_chunk_idx,
                            "source_type": "CSV",
                            "page_number": None,
                            "sheet_name": "CSV",
                            "row_start": batch_start_row,
                            "row_end": row_end,
                            "content": content,
                            "extraction_method": "TABULAR_PARSER",
                            "ocr_confidence": None,
                            "metadata": {
                                "encoding": encoding,
                                "delimiter": delimiter,
                                "row_count": len(current_batch),
                                "char_count": len(content),
                                "columns": header_row,
                            },
                        }
                        global_chunk_idx += 1
                        current_batch = []
                        batch_start_row = current_row_num + 1

                    current_row_num += 1

                if current_batch:
                    row_end = current_row_num - 1
                    content = self.format_table_chunk(
                        "CSV",
                        batch_start_row,
                        row_end,
                        header_row,
                        current_batch,
                    )
                    yield {
                        "chunk_index": global_chunk_idx,
                        "source_type": "CSV",
                        "page_number": None,
                        "sheet_name": "CSV",
                        "row_start": batch_start_row,
                        "row_end": row_end,
                        "content": content,
                        "extraction_method": "TABULAR_PARSER",
                        "ocr_confidence": None,
                        "metadata": {
                            "encoding": encoding,
                            "delimiter": delimiter,
                            "row_count": len(current_batch),
                            "char_count": len(content),
                            "columns": header_row,
                        },
                    }

            return 1, warnings, errors

        except Exception as e:
            raise SpreadsheetProcessingError(
                f"Failed to process CSV file '{path.name}': {str(e)}"
            )

    def _detect_csv_format(self, path: Path) -> Tuple[str, str]:
        """Detect file encoding and delimiter with sensible fallbacks."""
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc, errors="strict") as f:
                    sample = f.read(4096)
                    if not sample:
                        return enc, ","
                    try:
                        dialect = csv.Sniffer().sniff(
                            sample, delimiters=[",", ";", "\t", "|"]
                        )
                        return enc, dialect.delimiter
                    except Exception:
                        if ";" in sample and sample.count(";") > sample.count(","):
                            return enc, ";"
                        elif "\t" in sample and sample.count("\t") > sample.count(","):
                            return enc, "\t"
                        elif "|" in sample and sample.count("|") > sample.count(","):
                            return enc, "|"
                        return enc, ","
            except UnicodeDecodeError:
                continue
        return "latin-1", ","


spreadsheet_processor = SpreadsheetProcessor()
