import shutil
from PIL import Image, ImageDraw, ImageFont
import pytest
import pytesseract
from app.core.config import settings
from app.services.document_processing.ocr_engine import ocr_engine


@pytest.fixture
def genuine_test_invoice_image() -> Image.Image:
    """Create a high-contrast synthetic image containing known financial text."""
    width, height = 800, 200
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    sentence = "INVOICE NUMBER INV-2026-001 TOTAL AMOUNT 5000.00 USD"

    # Use default bitmap font or load standard truetype font if available
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    draw.text((30, 80), sentence, fill=(0, 0, 0), font=font)
    return image


def test_genuine_tesseract_ocr_integration(
    genuine_test_invoice_image: Image.Image,
) -> None:
    """
    Genuine integration test that invokes the real Tesseract executable on the host.
    Must NOT mock pytesseract.
    If Tesseract binary is not installed on this host, marks test as skipped (not passed).
    """
    tesseract_binary = shutil.which(settings.TESSERACT_CMD)
    if not tesseract_binary:
        pytest.skip(
            f"Genuine Tesseract executable '{settings.TESSERACT_CMD}' is not installed on this system. "
            f"To enable this integration test, install: sudo apt-get install -y tesseract-ocr tesseract-ocr-eng"
        )

    # 1. Run actual Tesseract OCR directly via pytesseract
    raw_text = pytesseract.image_to_string(
        genuine_test_invoice_image, config="--psm 6"
    )

    # 2. Run through our OCREngine preprocessing pipeline
    engine_result = ocr_engine.recognize(genuine_test_invoice_image)

    # 3. Verify recognition contains expected invoice number and amount
    combined_output = f"{raw_text} {engine_result.text}".upper()

    assert "INV-2026-001" in combined_output, (
        f"Expected 'INV-2026-001' in OCR output, got: '{combined_output}'"
    )
    assert "5000.00" in combined_output, (
        f"Expected '5000.00' in OCR output, got: '{combined_output}'"
    )
    assert engine_result.success is True
    assert engine_result.confidence is not None and engine_result.confidence > 0
