import os
from pathlib import Path
from typing import Optional, Tuple


SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".csv": "csv",
}

MIME_TYPE_MAPPING = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "tiff": "image/tiff",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
}

# Magic byte signatures for supported file types
SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "tiff": [b"II*\x00", b"MM\x00*"],
    "xlsx": [b"PK\x03\x04"],  # Standard ZIP signature for Office Open XML
    "xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # Compound File Binary Format
}


def sanitize_filename(filename: str) -> str:
    """
    Sanitize user-provided filenames to prevent directory traversal and path injection.
    Strips directory components and dangerous characters.
    """
    if not filename:
        return "unnamed_document"

    # Replace backslashes with forward slashes and extract base name
    clean_name = os.path.basename(filename.replace("\\", "/"))
    # Remove null bytes and non-printable characters
    clean_name = "".join(c for c in clean_name if c.isprintable() and c != "\x00")
    # Strip leading/trailing dots and spaces
    clean_name = clean_name.strip(". ")
    return clean_name or "unnamed_document"


def validate_file_extension(filename: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate filename extension.
    Returns: (is_valid, file_type, error_message)
    """
    ext = Path(filename).suffix.lower()
    if not ext:
        return False, None, "File has no extension. A valid file extension is required."

    file_type = SUPPORTED_EXTENSIONS.get(ext)
    if not file_type:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
        return (
            False,
            None,
            f"Unsupported file extension '{ext}'. Supported extensions are: {supported}",
        )

    return True, file_type, None


def validate_file_signature(
    header_bytes: bytes, file_type: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate binary magic bytes signature against expected file type.
    Returns: (is_valid, error_message)
    """
    if not header_bytes:
        return False, "File is empty (0 bytes)."

    if file_type == "csv":
        # CSV should be valid text without null bytes
        if b"\x00" in header_bytes[:512]:
            return False, "Invalid CSV format: file contains binary null bytes."
        try:
            # Check if header can be decoded as text
            header_bytes[:512].decode("utf-8")
        except UnicodeDecodeError:
            try:
                header_bytes[:512].decode("latin-1")
            except Exception:
                return False, "Invalid CSV format: content cannot be parsed as text."
        return True, None

    expected_signatures = SIGNATURES.get(file_type)
    if expected_signatures:
        for sig in expected_signatures:
            if header_bytes.startswith(sig):
                return True, None
        return (
            False,
            f"Invalid file signature for {file_type.upper()}. Header bytes do not match the expected magic sequence.",
        )

    return True, None
