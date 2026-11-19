import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Tuple
from PIL import Image, ImageOps, ImageSequence
from app.core.config import settings
from app.services.document_processing.ocr_engine import ocr_engine

logger = logging.getLogger("doc_intel.image")

# Protect against decompression bomb attacks on maliciously oversized images
Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS


class ImageProcessingError(Exception):
    """Raised when an image file cannot be opened or is severely corrupted."""
    pass


class ImageProcessor:
    def extract_chunks(
        self, file_path: str | Path, file_type: str
    ) -> Generator[Dict[str, Any], None, Tuple[int, List[str], List[str]]]:
        """
        Process single image (JPG, PNG) or multi-frame TIFF image.
        Yields chunk dictionary per image or frame.
        Returns: (total_frames_or_pages, warnings, errors) upon completion.
        """
        path = Path(file_path)
        if not path.exists():
            raise ImageProcessingError(f"Image file does not exist at '{file_path}'.")

        warnings: List[str] = []
        errors: List[str] = []
        is_tiff = file_type.lower() in ["tiff", "tif"]

        try:
            with Image.open(str(path)) as img:
                if is_tiff:
                    # Multi-page / multi-frame TIFF handling
                    frames = []
                    for frame_idx, frame in enumerate(ImageSequence.Iterator(img)):
                        try:
                            # Copy frame data so PIL stream iterator doesn't drop it
                            frame_copy = frame.copy()
                            frame_transposed = ImageOps.exif_transpose(frame_copy)
                            if frame_transposed.mode != "RGB":
                                frame_transposed = frame_transposed.convert("RGB")
                            frames.append((frame_idx + 1, frame_transposed))
                        except Exception as fe:
                            err_msg = f"Failed to decode TIFF frame {frame_idx + 1}: {str(fe)}"
                            errors.append(err_msg)

                    total_frames = len(frames)
                    if total_frames == 0:
                        raise ImageProcessingError("TIFF image contains 0 readable frames.")

                    logger.info("Processing multi-frame TIFF (%d frames): %s", total_frames, path.name)

                    for chunk_idx, (frame_num, frame_img) in enumerate(frames):
                        ocr_res = ocr_engine.recognize(frame_img)
                        if not ocr_res.success:
                            warnings.append(
                                f"Frame {frame_num}: OCR was unavailable or failed. ({ocr_res.error_message})"
                            )

                        content = ocr_res.text if ocr_res.success and ocr_res.text else f"[TIFF Frame {frame_num}: {ocr_res.error_message or 'No text detected'}]"
                        method = "OCR" if ocr_res.success else "FALLBACK"

                        yield {
                            "chunk_index": chunk_idx,
                            "source_type": "TIFF_PAGE",
                            "page_number": frame_num,
                            "sheet_name": None,
                            "row_start": None,
                            "row_end": None,
                            "content": content,
                            "extraction_method": method,
                            "ocr_confidence": ocr_res.confidence,
                            "metadata": {
                                "frame_number": frame_num,
                                "dimensions": [frame_img.width, frame_img.height],
                                "ocr_words": ocr_res.word_count,
                                "deskew_angle": ocr_res.skew_angle_detected,
                                "char_count": len(content),
                            },
                        }

                    return total_frames, warnings, errors

                else:
                    # Standard single image (JPG, PNG)
                    img_transposed = ImageOps.exif_transpose(img)
                    if img_transposed.mode != "RGB":
                        img_transposed = img_transposed.convert("RGB")

                    ocr_res = ocr_engine.recognize(img_transposed)
                    if not ocr_res.success:
                        warnings.append(
                            f"Image OCR unavailable or failed: {ocr_res.error_message}"
                        )

                    content = ocr_res.text if ocr_res.success and ocr_res.text else f"[Image: {ocr_res.error_message or 'No text detected'}]"
                    method = "OCR" if ocr_res.success else "FALLBACK"

                    yield {
                        "chunk_index": 0,
                        "source_type": "IMAGE",
                        "page_number": 1,
                        "sheet_name": None,
                        "row_start": None,
                        "row_end": None,
                        "content": content,
                        "extraction_method": method,
                        "ocr_confidence": ocr_res.confidence,
                        "metadata": {
                            "page_number": 1,
                            "dimensions": [img_transposed.width, img_transposed.height],
                            "ocr_words": ocr_res.word_count,
                            "deskew_angle": ocr_res.skew_angle_detected,
                            "char_count": len(content),
                        },
                    }

                    return 1, warnings, errors

        except ImageProcessingError:
            raise
        except Exception as e:
            raise ImageProcessingError(f"Failed to process image '{path.name}': {str(e)}")


image_processor = ImageProcessor()
