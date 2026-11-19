from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from app.services.document_processing.image_processor import (
    ImageProcessingError,
    ImageProcessor,
)
from app.services.document_processing.ocr_engine import OCRResult


@pytest.fixture
def sample_png_path(tmp_path: Path) -> Path:
    path = tmp_path / "receipt.png"
    img = Image.new("RGB", (100, 50), color="white")
    img.save(str(path))
    return path


@pytest.fixture
def sample_jpg_path(tmp_path: Path) -> Path:
    path = tmp_path / "bill.jpg"
    img = Image.new("RGB", (80, 40), color="white")
    img.save(str(path))
    return path


@pytest.fixture
def sample_multiframe_tiff_path(tmp_path: Path) -> Path:
    path = tmp_path / "multi_invoice.tiff"
    frame1 = Image.new("RGB", (120, 120), color="white")
    frame2 = Image.new("RGB", (120, 120), color="lightgray")
    frame3 = Image.new("RGB", (120, 120), color="white")
    frame1.save(
        str(path),
        format="TIFF",
        save_all=True,
        append_images=[frame2, frame3],
    )
    return path


def test_png_processing(sample_png_path: Path) -> None:
    processor = ImageProcessor()
    gen = processor.extract_chunks(sample_png_path, "png")
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        total, warnings, errors = stop.value

    assert total == 1
    assert len(chunks) == 1
    assert chunks[0]["source_type"] == "IMAGE"
    assert chunks[0]["page_number"] == 1


def test_jpg_processing(sample_jpg_path: Path) -> None:
    processor = ImageProcessor()
    gen = processor.extract_chunks(sample_jpg_path, "jpg")
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        total, warnings, errors = stop.value

    assert total == 1
    assert len(chunks) == 1
    assert chunks[0]["source_type"] == "IMAGE"


def test_multiframe_tiff_processing(sample_multiframe_tiff_path: Path) -> None:
    processor = ImageProcessor()
    gen = processor.extract_chunks(sample_multiframe_tiff_path, "tiff")
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        total, warnings, errors = stop.value

    assert total == 3
    assert len(chunks) == 3
    for idx, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == idx
        assert chunk["source_type"] == "TIFF_PAGE"
        assert chunk["page_number"] == idx + 1


def test_corrupt_image_handling(tmp_path: Path) -> None:
    corrupted_path = tmp_path / "corrupted.jpg"
    corrupted_path.write_bytes(b"\xff\xd8\xffnotarealjpgdata")
    processor = ImageProcessor()
    gen = processor.extract_chunks(corrupted_path, "jpg")
    with pytest.raises(ImageProcessingError):
        next(gen)
