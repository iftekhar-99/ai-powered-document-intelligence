import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile
from app.core.config import settings
from app.services.document_processing.validator import (
    MIME_TYPE_MAPPING,
    sanitize_filename,
    validate_file_extension,
    validate_file_signature,
)


class FileStorageService:
    CHUNK_SIZE = 64 * 1024  # 64 KB streaming buffer

    def __init__(self, upload_dir: Optional[str] = None):
        self.upload_dir = Path(upload_dir or settings.UPLOAD_DIR)
        self.max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        self._ensure_upload_dir()

    @property
    def dir_path(self) -> Path:
        return Path(self.upload_dir)

    def _ensure_upload_dir(self) -> None:
        self.dir_path.mkdir(parents=True, exist_ok=True)

    async def save_uploaded_file(
        self, upload_file: UploadFile
    ) -> Tuple[bool, Optional[dict], Optional[dict]]:
        """
        Process, validate, and store an uploaded file using chunked streaming.
        Returns:
            (is_success, document_dict_if_success, error_dict_if_failed)
        """
        raw_name = upload_file.filename or "unnamed_document"
        clean_filename = sanitize_filename(raw_name)

        # 1. Validate file extension
        is_valid_ext, file_type, ext_error = validate_file_extension(clean_filename)
        if not is_valid_ext or not file_type:
            return (
                False,
                None,
                {
                    "filename": raw_name,
                    "error": "Unsupported file type",
                    "reason": ext_error or "Unsupported extension",
                },
            )

        # 2. Prepare storage destination
        self._ensure_upload_dir()
        doc_uuid = uuid.uuid4()
        ext = Path(clean_filename).suffix.lower()
        stored_filename = f"{doc_uuid}{ext}"
        destination_path = self.dir_path / stored_filename

        sha256 = hashlib.sha256()
        total_size = 0
        header_bytes = b""
        first_chunk = True

        try:
            with open(destination_path, "wb") as dest:
                while True:
                    chunk = await upload_file.read(self.CHUNK_SIZE)
                    if not chunk:
                        break

                    if first_chunk:
                        header_bytes = chunk[:512]
                        # 3. Validate file signature on first chunk
                        is_valid_sig, sig_error = validate_file_signature(
                            header_bytes, file_type
                        )
                        if not is_valid_sig:
                            dest.close()
                            self.delete_file(destination_path)
                            return (
                                False,
                                None,
                                {
                                    "filename": raw_name,
                                    "error": "Invalid file signature",
                                    "reason": sig_error or "File signature mismatch",
                                },
                            )
                        first_chunk = False

                    total_size += len(chunk)
                    if total_size > self.max_bytes:
                        dest.close()
                        self.delete_file(destination_path)
                        return (
                            False,
                            None,
                            {
                                "filename": raw_name,
                                "error": "File size limit exceeded",
                                "reason": (
                                    f"File size exceeds maximum allowed limit of "
                                    f"{settings.MAX_UPLOAD_SIZE_MB} MB."
                                ),
                            },
                        )

                    sha256.update(chunk)
                    dest.write(chunk)

            # 4. Handle empty file (0 bytes)
            if total_size == 0:
                self.delete_file(destination_path)
                return (
                    False,
                    None,
                    {
                        "filename": raw_name,
                        "error": "Empty file",
                        "reason": "Uploaded file contains 0 bytes.",
                    },
                )

            computed_hash = sha256.hexdigest()
            mime_type = upload_file.content_type or MIME_TYPE_MAPPING.get(
                file_type, "application/octet-stream"
            )

            document_data = {
                "id": doc_uuid,
                "original_filename": clean_filename,
                "stored_filename": stored_filename,
                "file_path": str(destination_path.resolve()),
                "file_type": file_type,
                "mime_type": mime_type,
                "file_size": total_size,
                "sha256_hash": computed_hash,
                "status": "uploaded",
            }
            return True, document_data, None

        except Exception as e:
            self.delete_file(destination_path)
            return (
                False,
                None,
                {
                    "filename": raw_name,
                    "error": "Processing error",
                    "reason": f"An error occurred while saving file: {str(e)}",
                },
            )

    def delete_file(self, file_path: Path | str) -> bool:
        """Safely delete file from storage if it exists."""
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                path.unlink(missing_ok=True)
                return True
            return False
        except Exception:
            return False


storage_service = FileStorageService()
