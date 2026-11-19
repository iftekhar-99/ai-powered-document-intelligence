# Tesseract OCR Setup & Troubleshooting Guide

This document details the configuration, verification, and host installation procedures for Tesseract OCR in the AI-Powered Financial Document Intelligence System.

---

## 1. Role of OCR in the Processing Pipeline

The document engine uses a **hybrid digital + OCR** approach:
- **Digital PDFs**: PyMuPDF extracts font-encoded text directly. If a page has $\ge 50$ characters, digital text extraction is used (`DIGITAL_TEXT`).
- **Scanned PDFs & Images**: When a page has $< 50$ characters or is an image (JPG, PNG, TIFF), the engine rasterizes the page to a 300 DPI image and passes it to the OCR engine.
- **Image Preprocessing**: Before OCR recognition, OpenCV performs grayscale conversion, CLAHE contrast enhancement, deskew angle correction, and noise reduction.
- **Spreadsheets & CSVs**: Parsed directly via OpenPyXL, xlrd, and standard csv without requiring OCR.

---

## 2. Host Installation Instructions

### Debian / Ubuntu / Pop!_OS
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng libtesseract-dev
```

To install additional financial or multi-language training sets (e.g. French, German, Spanish):
```bash
sudo apt-get install -y tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-spa
```

### Fedora / Red Hat Enterprise Linux / CentOS Stream
```bash
sudo dnf install -y tesseract tesseract-langpack-eng
```

### macOS (via Homebrew)
```bash
brew install tesseract tesseract-lang
```

### Windows
1. Download the official installer from the [UB-Mannheim Tesseract OCR wiki](https://github.com/UB-Mannheim/tesseract/wiki).
2. During installation, select additional language packs if needed.
3. Add the installation directory (typically `C:\Program Files\Tesseract-OCR`) to your system `PATH`, or set `TESSERACT_CMD` in `.env`:
   ```ini
   TESSERACT_CMD="C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
   ```

---

## 3. Configuration in `.env`

The following environment variables control OCR behavior in `backend/app/core/config.py`:

```ini
# Path to executable or command name in PATH
TESSERACT_CMD=tesseract

# Default OCR language
OCR_LANGUAGE=eng

# Maximum execution timeout in seconds per page to prevent hanging
OCR_TIMEOUT_SECONDS=30

# Rasterization resolution for scanned PDF pages
PDF_OCR_DPI=300

# Minimum characters required to treat a PDF page as digital text
PDF_MIN_TEXT_CHARS_PER_PAGE=50
```

---

## 4. Verifying OCR Functionality

### Command Line Verification
```bash
tesseract --version
tesseract --list-langs
```

### API Capabilities Verification
Run the backend and inspect the `/api/v1/capabilities` endpoint:
```bash
curl http://localhost:8000/api/v1/capabilities
```
Expected response when installed:
```json
{
  "pdf_digital_extraction": true,
  "tesseract_available": true,
  "tesseract_executable": "/usr/bin/tesseract",
  "tesseract_version": "5.3.4",
  "ocr_languages": ["eng", "osd"],
  "xlsx_processing": true,
  "xls_processing": true,
  "csv_processing": true,
  "include_hidden_sheets": true,
  "background_processing_mode": "inline",
  "redis_connected": false,
  "redis_status": "offline (not required; using inline background tasks)"
}
```

### Automated Integration Test
A real integration test that generates a synthetic invoice image and tests Tesseract is provided at:
```bash
cd backend
source .venv/bin/activate
pytest tests/test_ocr_genuine_integration.py -v
```
- If Tesseract is installed: test will pass and verify that `"INV-2026-001"` and `"5000.00"` are recognized.
- If Tesseract is not installed: test will be cleanly marked as **SKIPPED** with installation instructions.
