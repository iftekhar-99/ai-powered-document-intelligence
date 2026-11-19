import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
from PIL import Image
import pymupdf
from app.core.config import settings
from app.services.document_processing.ocr_engine import ocr_engine

logger = logging.getLogger("doc_intel.pdf")


class PDFProcessingError(Exception):
    """Raised when PDF cannot be opened, is encrypted, or is fundamentally corrupted."""
    pass


class PDFProcessor:
    def __init__(
        self,
        min_text_chars: Optional[int] = None,
        ocr_dpi: Optional[int] = None,
    ):
        self.min_text_chars = (
            min_text_chars
            if min_text_chars is not None
            else settings.PDF_MIN_TEXT_CHARS_PER_PAGE
        )
        self.ocr_dpi = ocr_dpi if ocr_dpi is not None else settings.PDF_OCR_DPI

    def extract_chunks(
        self, file_path: str | Path
    ) -> Generator[Dict[str, Any], None, Tuple[int, List[str], List[str]]]:
        """
        Stream process a PDF document page-by-page.
        Yields chunk dictionary per page.
        Returns: (total_pages, warnings, errors) upon completion.
        """
        path = Path(file_path)
        if not path.exists():
            raise PDFProcessingError(f"PDF file does not exist at '{file_path}'.")

        warnings: List[str] = []
        errors: List[str] = []

        try:
            doc = pymupdf.open(str(path))
        except Exception as e:
            raise PDFProcessingError(f"Failed to open PDF document: {str(e)}")

        try:
            if doc.is_encrypted:
                raise PDFProcessingError(
                    "PDF is encrypted or password-protected and cannot be processed."
                )

            page_count = len(doc)
            if page_count == 0:
                raise PDFProcessingError("PDF contains 0 pages.")

            logger.info("Starting processing of PDF (%d pages): %s", page_count, path.name)

            for page_index in range(page_count):
                page_number = page_index + 1
                try:
                    page = doc[page_index]
                    text = page.get_text("text").strip()

                    # Decide whether digital text is sufficient or if OCR rasterization is needed
                    if len(text) >= self.min_text_chars:
                        yield {
                            "chunk_index": page_index,
                            "source_type": "PDF_PAGE",
                            "page_number": page_number,
                            "sheet_name": None,
                            "row_start": None,
                            "row_end": None,
                            "content": text,
                            "extraction_method": "DIGITAL_TEXT",
                            "ocr_confidence": None,
                            "metadata": {
                                "page_number": page_number,
                                "char_count": len(text),
                                "width": round(page.rect.width, 1),
                                "height": round(page.rect.height, 1),
                            },
                        }
                    else:
                        # Scanned page detected -> invoke OCR
                        logger.debug(
                            "Page %d has insufficient digital text (%d chars). Falling back to OCR.",
                            page_number,
                            len(text),
                        )

                        if ocr_engine.is_ocr_available():
                            pix = page.get_pixmap(dpi=self.ocr_dpi)
                            img = Image.frombytes(
                                "RGB", [pix.width, pix.height], pix.samples
                            )
                            ocr_res = ocr_engine.recognize(img)

                            if ocr_res.success and ocr_res.text:
                                yield {
                                    "chunk_index": page_index,
                                    "source_type": "PDF_PAGE",
                                    "page_number": page_number,
                                    "sheet_name": None,
                                    "row_start": None,
                                    "row_end": None,
                                    "content": ocr_res.text,
                                    "extraction_method": "OCR",
                                    "ocr_confidence": ocr_res.confidence,
                                    "metadata": {
                                        "page_number": page_number,
                                        "ocr_confidence": ocr_res.confidence,
                                        "ocr_words": ocr_res.word_count,
                                        "deskew_angle": ocr_res.skew_angle_detected,
                                        "char_count": len(ocr_res.text),
                                    },
                                }
                            else:
                                # OCR returned empty or error, retain whatever digital text exists
                                warn_msg = (
                                    f"Page {page_number}: OCR yielded no text. "
                                    f"({ocr_res.error_message or 'No text detected'})"
                                )
                                warnings.append(warn_msg)
                                yield {
                                    "chunk_index": page_index,
                                    "source_type": "PDF_PAGE",
                                    "page_number": page_number,
                                    "sheet_name": None,
                                    "row_start": None,
                                    "row_end": None,
                                    "content": text or "[Scanned page: No text detected]",
                                    "extraction_method": "OCR" if ocr_res.success else "DIGITAL_TEXT",
                                    "ocr_confidence": ocr_res.confidence,
                                    "metadata": {
                                        "page_number": page_number,
                                        "warning": warn_msg,
                                        "char_count": len(text),
                                    },
                                }
                        else:
                            # OCR not installed on host
                            warn_msg = (
                                f"Page {page_number} appears scanned, but OCR is unavailable on system."
                            )
                            warnings.append(warn_msg)
                            yield {
                                "chunk_index": page_index,
                                "source_type": "PDF_PAGE",
                                "page_number": page_number,
                                "sheet_name": None,
                                "row_start": None,
                                "row_end": None,
                                "content": text or "[Scanned page: OCR unavailable on server]",
                                "extraction_method": "DIGITAL_TEXT",
                                "ocr_confidence": None,
                                "metadata": {
                                    "page_number": page_number,
                                    "warning": warn_msg,
                                    "char_count": len(text),
                                },
                            }

                except Exception as page_err:
                    err_msg = f"Error processing PDF page {page_number}: {str(page_err)}"
                    logger.warning(err_msg, exc_info=True)
                    errors.append(err_msg)
                    yield {
                        "chunk_index": page_index,
                        "source_type": "PDF_PAGE",
                        "page_number": page_number,
                        "sheet_name": None,
                        "row_start": None,
                        "row_end": None,
                        "content": f"[Error on page {page_number}: {str(page_err)}]",
                        "extraction_method": "FALLBACK",
                        "ocr_confidence": None,
                        "metadata": {"page_number": page_number, "error": str(page_err)},
                    }

            return page_count, warnings, errors

        finally:
            doc.close()


pdf_processor = PDFProcessor()
