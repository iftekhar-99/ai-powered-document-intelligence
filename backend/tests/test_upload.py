import io
from fastapi.testclient import TestClient
from app.core.config import settings
from app.services.document_processing.storage import storage_service


def test_successful_single_pdf_upload(client: TestClient, pdf_bytes: bytes) -> None:
    files = [("files", ("invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 1
    assert data["total_rejected"] == 0
    doc = data["accepted"][0]
    assert doc["original_filename"] == "invoice.pdf"
    assert doc["file_type"] == "pdf"
    assert doc["status"] == "uploaded"
    assert "sha256_hash" in doc
    assert "id" in doc


def test_successful_multiple_file_upload(
    client: TestClient, pdf_bytes: bytes, png_bytes: bytes, csv_bytes: bytes
) -> None:
    files = [
        ("files", ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")),
        ("files", ("scan.png", io.BytesIO(png_bytes), "image/png")),
        ("files", ("data.csv", io.BytesIO(csv_bytes), "text/csv")),
    ]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 3
    assert data["total_rejected"] == 0
    types = [d["file_type"] for d in data["accepted"]]
    assert "pdf" in types
    assert "png" in types
    assert "csv" in types


def test_png_and_jpg_upload(client: TestClient, png_bytes: bytes, jpg_bytes: bytes) -> None:
    files = [
        ("files", ("receipt.png", io.BytesIO(png_bytes), "image/png")),
        ("files", ("bill.jpg", io.BytesIO(jpg_bytes), "image/jpeg")),
    ]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 2
    assert data["total_rejected"] == 0


def test_xlsx_xls_and_csv_upload(
    client: TestClient, xlsx_bytes: bytes, xls_bytes: bytes, csv_bytes: bytes
) -> None:
    files = [
        ("files", ("statement.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ("files", ("ledger.xls", io.BytesIO(xls_bytes), "application/vnd.ms-excel")),
        ("files", ("transactions.csv", io.BytesIO(csv_bytes), "text/csv")),
    ]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 3
    assert data["total_rejected"] == 0


def test_unsupported_extension_rejection(client: TestClient) -> None:
    files = [("files", ("executable.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream"))]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 0
    assert data["total_rejected"] == 1
    assert data["rejected"][0]["error"] == "Unsupported file type"


def test_invalid_file_signature_rejection(client: TestClient) -> None:
    # A text file renamed to .pdf
    fake_pdf = b"This is just plain text, not a valid PDF header!"
    files = [("files", ("fake.pdf", io.BytesIO(fake_pdf), "application/pdf"))]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 0
    assert data["total_rejected"] == 1
    assert data["rejected"][0]["error"] == "Invalid file signature"


def test_duplicate_file_detection_using_sha256(client: TestClient, pdf_bytes: bytes) -> None:
    # Upload first time
    files = [("files", ("invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    res1 = client.post("/api/v1/documents/upload", files=files)
    assert res1.status_code == 200
    assert res1.json()["total_accepted"] == 1

    # Upload exact same file again (even with different filename)
    files2 = [("files", ("duplicate_invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    res2 = client.post("/api/v1/documents/upload", files=files2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total_accepted"] == 0
    assert data2["total_rejected"] == 1
    assert data2["rejected"][0]["error"] == "Duplicate file detected"


def test_empty_file_handling(client: TestClient) -> None:
    files = [("files", ("empty.pdf", io.BytesIO(b""), "application/pdf"))]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 0
    assert data["total_rejected"] == 1
    assert data["rejected"][0]["error"] in ["Empty file", "Invalid file signature"]


def test_file_size_limit_enforcement(client: TestClient, pdf_bytes: bytes, monkeypatch) -> None:
    # Temporarily reduce max size to 10 bytes for test
    monkeypatch.setattr(storage_service, "max_bytes", 10)
    files = [("files", ("large_invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 0
    assert data["total_rejected"] == 1
    assert data["rejected"][0]["error"] == "File size limit exceeded"


def test_partial_batch_failure_handling(
    client: TestClient, pdf_bytes: bytes, png_bytes: bytes
) -> None:
    # 1 valid PDF, 1 invalid fake PDF, 1 valid PNG, 1 unsupported EXE
    files = [
        ("files", ("valid.pdf", io.BytesIO(pdf_bytes), "application/pdf")),
        ("files", ("fake.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")),
        ("files", ("valid.png", io.BytesIO(png_bytes), "image/png")),
        ("files", ("malware.exe", io.BytesIO(b"MZ123"), "application/octet-stream")),
    ]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_accepted"] == 2
    assert data["total_rejected"] == 2
    accepted_names = [d["original_filename"] for d in data["accepted"]]
    assert "valid.pdf" in accepted_names
    assert "valid.png" in accepted_names
    rejected_errors = [r["error"] for r in data["rejected"]]
    assert "Invalid file signature" in rejected_errors
    assert "Unsupported file type" in rejected_errors
