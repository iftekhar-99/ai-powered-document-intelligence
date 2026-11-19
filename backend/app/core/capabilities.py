import logging
import shutil
import socket
from typing import Any, Dict, List
import pytesseract
from app.core.config import settings

logger = logging.getLogger("doc_intel.capabilities")


def is_redis_connected(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check whether Redis server is reachable and accepting socket connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def get_system_capabilities() -> Dict[str, Any]:
    """
    Probe the actual host environment and dependencies to report accurate processing capabilities.
    Does not assume or confuse configured services with actually available or connected services.
    """
    # 1. PDF Digital Extraction Availability
    try:
        import pymupdf  # noqa: F401
        pdf_digital_available = True
    except ImportError:
        pdf_digital_available = False

    # 2. Tesseract Binary Availability
    tesseract_path = shutil.which(settings.TESSERACT_CMD)
    tesseract_available = tesseract_path is not None

    # 3. OCR Language Availability
    ocr_languages: List[str] = []
    tesseract_version: str = "unavailable"
    if tesseract_available:
        try:
            ocr_languages = pytesseract.get_languages(config="")
            tesseract_version = str(pytesseract.get_tesseract_version())
        except Exception as e:
            logger.debug("Failed to query Tesseract languages or version: %s", str(e))
            ocr_languages = []

    # 4. XLSX Processing Availability
    try:
        import openpyxl  # noqa: F401
        xlsx_available = True
    except ImportError:
        xlsx_available = False

    # 5. XLS Processing Availability
    try:
        import xlrd  # noqa: F401
        xls_available = True
    except ImportError:
        xls_available = False

    # 6. CSV Processing Availability
    try:
        import csv  # noqa: F401
        csv_available = True
    except ImportError:
        csv_available = False

    # 7. Background Processing Mode
    bg_mode = settings.PROCESSING_MODE.lower()

    # 8. Redis Connectivity (Actual Connection Probe)
    redis_connected = is_redis_connected(settings.REDIS_HOST, settings.REDIS_PORT)
    if redis_connected:
        redis_status = "connected"
    elif bg_mode == "celery":
        redis_status = "unreachable (required for celery workers)"
    else:
        redis_status = "offline (not required; using inline background tasks)"

    return {
        "pdf_digital_extraction": pdf_digital_available,
        "tesseract_available": tesseract_available,
        "tesseract_executable": tesseract_path or "not found",
        "tesseract_version": tesseract_version,
        "ocr_languages": ocr_languages,
        "xlsx_processing": xlsx_available,
        "xls_processing": xls_available,
        "csv_processing": csv_available,
        "include_hidden_sheets": settings.INCLUDE_HIDDEN_SHEETS,
        "background_processing_mode": bg_mode,
        "redis_connected": redis_connected,
        "redis_status": redis_status,
    }
