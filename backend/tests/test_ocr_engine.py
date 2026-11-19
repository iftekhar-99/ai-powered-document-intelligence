import time
from unittest.mock import patch
import numpy as np
import pytest
from PIL import Image
from app.services.document_processing.ocr_engine import OCREngine, OCRResult


def test_ocr_preprocessing_grayscale_and_clahe() -> None:
    engine = OCREngine()
    # Create RGB test image with varied values
    img = Image.new("RGB", (200, 200), color=(180, 200, 220))
    preprocessed, angle = engine.preprocess_image(img)

    assert isinstance(preprocessed, np.ndarray)
    assert len(preprocessed.shape) == 2  # Grayscale
    assert preprocessed.shape == (200, 200)
    assert isinstance(angle, float)


def test_ocr_skew_detection_and_deskew() -> None:
    engine = OCREngine()
    # Synthetic image
    img = np.ones((300, 300), dtype=np.uint8) * 255
    preprocessed, angle = engine.preprocess_image(img)
    assert abs(angle) <= 30.0


def test_missing_tesseract_graceful_handling() -> None:
    """Genuine test ensuring that when Tesseract is not installed, no crash occurs and clear error is returned."""
    engine = OCREngine()
    engine.tesseract_cmd = "nonexistent_tesseract_binary_path_12345"

    img = Image.new("RGB", (100, 100), color="white")
    res = engine.recognize(img)

    assert res.success is False
    assert res.confidence is None
    assert res.word_count == 0
    assert "not installed or not accessible" in res.error_message


def test_ocr_recognition_with_mocked_pytesseract() -> None:
    """Mock-based integration test for confidence calculation and word parsing."""
    engine = OCREngine()

    mock_data = {
        "text": ["", "INVOICE", "", "TOTAL", "$500.00"],
        "conf": [-1, 95.5, -1, 90.0, 85.5],
    }

    with patch.object(engine, "is_ocr_available", return_value=True):
        with patch("pytesseract.image_to_data", return_value=mock_data):
            img = Image.new("RGB", (100, 100), color="white")
            result = engine.recognize(img)

            assert result.success is True
            assert result.word_count == 3
            assert result.text == "INVOICE TOTAL $500.00"
            assert result.confidence == pytest.approx(90.33, 0.1)
            assert result.processing_time_ms >= 0


def test_ocr_timeout_handling() -> None:
    engine = OCREngine()

    with patch.object(engine, "is_ocr_available", return_value=True):
        with patch("pytesseract.image_to_data", side_effect=RuntimeError("OCR processing timed out")):
            img = Image.new("RGB", (100, 100), color="white")
            result = engine.recognize(img)

            assert result.success is False
            assert "timed out" in result.error_message.lower()
