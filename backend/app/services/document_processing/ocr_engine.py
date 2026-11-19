import logging
import os
import shutil
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Union
import cv2
import numpy as np
from PIL import Image
import pytesseract
from pytesseract import Output
from app.core.config import settings

logger = logging.getLogger("doc_intel.ocr")


@dataclass
class OCRResult:
    text: str
    confidence: Optional[float]
    word_count: int
    processing_time_ms: float
    success: bool
    error_message: Optional[str] = None
    skew_angle_detected: Optional[float] = None


class OCREngine:
    def __init__(self):
        self.tesseract_cmd = settings.TESSERACT_CMD
        self.language = settings.OCR_LANGUAGE
        self.timeout = settings.OCR_TIMEOUT_SECONDS

    def is_ocr_available(self) -> bool:
        """Check whether the configured Tesseract binary is available and executable."""
        cmd = self.tesseract_cmd
        if os.path.isabs(cmd):
            if os.path.isfile(cmd) and os.access(cmd, os.X_OK):
                return True
        return shutil.which(cmd) is not None

    def preprocess_image(
        self, image: Union[Image.Image, np.ndarray]
    ) -> Tuple[np.ndarray, float]:
        """
        Preprocess image for optimal OCR:
        1. Convert PIL to OpenCV ndarray if needed.
        2. Convert to grayscale.
        3. Correct skew if detectable.
        4. Enhance contrast via CLAHE.
        5. Denoise and threshold.
        Returns: (preprocessed_image_ndarray, detected_skew_angle)
        """
        # Convert PIL Image to RGB ndarray
        if isinstance(image, Image.Image):
            if image.mode != "RGB":
                image = image.convert("RGB")
            np_img = np.array(image)
        else:
            np_img = image.copy()

        # Convert to grayscale
        if len(np_img.shape) == 3:
            gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
        else:
            gray = np_img.copy()

        # Deskew calculation
        angle = self._detect_skew_angle(gray)
        deskewed = self._rotate_image(gray, angle)

        # Contrast enhancement (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(deskewed)

        # Gentle median blur to eliminate salt-and-pepper noise
        denoised = cv2.medianBlur(contrast_enhanced, 3)

        return denoised, angle

    def _detect_skew_angle(self, gray: np.ndarray) -> float:
        """Detect text orientation skew angle using minAreaRect on thresholded points."""
        try:
            thresh = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )[1]
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 100:
                return 0.0

            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            # Only accept realistic document skew (within -30 to 30 degrees)
            if -30.0 <= angle <= 30.0:
                return round(float(angle), 2)
            return 0.0
        except Exception:
            return 0.0

    def _rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        """Rotate image by angle in degrees with background padding."""
        if abs(angle) < 0.2:
            return image
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            image,
            M,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def recognize(
        self,
        image: Union[Image.Image, np.ndarray],
        lang: Optional[str] = None,
    ) -> OCRResult:
        """
        Execute OCR recognition on a single image.
        Returns structured OCRResult with text, confidence estimate, word count, and timing.
        """
        start_time = time.perf_counter()

        if not self.is_ocr_available():
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_msg = (
                f"Tesseract OCR executable '{self.tesseract_cmd}' is not installed "
                "or not accessible on system PATH. OCR is unavailable."
            )
            logger.warning(err_msg)
            return OCRResult(
                text="",
                confidence=None,
                word_count=0,
                processing_time_ms=round(duration_ms, 2),
                success=False,
                error_message=err_msg,
                skew_angle_detected=None,
            )

        try:
            # Set pytesseract tesseract_cmd
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            preprocessed, skew_angle = self.preprocess_image(image)

            active_lang = lang or self.language
            ocr_data = pytesseract.image_to_data(
                preprocessed,
                lang=active_lang,
                output_type=Output.DICT,
                timeout=self.timeout,
            )

            # Filter valid recognized words and confidences
            recognized_words = []
            confidences = []
            for i, text in enumerate(ocr_data.get("text", [])):
                word = text.strip()
                if word:
                    recognized_words.append(word)
                    try:
                        conf = float(ocr_data["conf"][i])
                        if conf >= 0:
                            confidences.append(conf)
                    except (ValueError, KeyError):
                        pass

            # Calculate mean word confidence as page-level statistic
            mean_conf = (
                round(float(np.mean(confidences)), 2) if confidences else None
            )
            extracted_text = " ".join(recognized_words).strip()
            duration_ms = (time.perf_counter() - start_time) * 1000

            return OCRResult(
                text=extracted_text,
                confidence=mean_conf,
                word_count=len(recognized_words),
                processing_time_ms=round(duration_ms, 2),
                success=True,
                error_message=None,
                skew_angle_detected=skew_angle,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if "timeout" in str(e).lower() or "timed out" in str(e).lower() or type(e).__name__ in ["TimeoutException", "TesseractTimeoutError", "TimeoutExpired"]:
                return OCRResult(
                    text="",
                    confidence=None,
                    word_count=0,
                    processing_time_ms=round(duration_ms, 2),
                    success=False,
                    error_message=f"OCR processing timed out after {self.timeout} seconds.",
                )
            logger.error("OCR execution failed: %s", str(e), exc_info=True)
            return OCRResult(
                text="",
                confidence=None,
                word_count=0,
                processing_time_ms=round(duration_ms, 2),
                success=False,
                error_message=f"OCR execution error: {str(e)}",
            )


ocr_engine = OCREngine()
