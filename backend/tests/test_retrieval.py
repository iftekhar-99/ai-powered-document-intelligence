import io
import os
import uuid
from fastapi.testclient import TestClient


def test_document_listing_and_pagination(
    client: TestClient, pdf_bytes: bytes, png_bytes: bytes
) -> None:
    # Upload two documents
    files = [
        ("files", ("invoice_alpha.pdf", io.BytesIO(pdf_bytes), "application/pdf")),
        ("files", ("receipt_beta.png", io.BytesIO(png_bytes), "image/png")),
    ]
    client.post("/api/v1/documents/upload", files=files)

    # List all documents
    res = client.get("/api/v1/documents")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1

    # Filter by file_type=pdf
    res_pdf = client.get("/api/v1/documents?file_type=pdf")
    assert res_pdf.status_code == 200
    assert res_pdf.json()["total"] == 1
    assert res_pdf.json()["items"][0]["file_type"] == "pdf"

    # Filter by search=alpha
    res_search = client.get("/api/v1/documents?search=alpha")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1
    assert res_search.json()["items"][0]["original_filename"] == "invoice_alpha.pdf"

    # Pagination: page_size=1
    res_p1 = client.get("/api/v1/documents?page=1&page_size=1")
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert len(p1_data["items"]) == 1
    assert p1_data["total_pages"] == 2


def test_document_details_retrieval(client: TestClient, pdf_bytes: bytes) -> None:
    files = [("files", ("detailed_invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_res = client.post("/api/v1/documents/upload", files=files)
    doc_id = upload_res.json()["accepted"][0]["id"]

    res = client.get(f"/api/v1/documents/{doc_id}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == doc_id
    assert detail["original_filename"] == "detailed_invoice.pdf"
    assert detail["status"] == "uploaded"
    assert len(detail["processing_events"]) >= 1
    assert detail["processing_events"][0]["event_type"] == "upload_completed"


def test_nonexistent_document_handling(client: TestClient) -> None:
    random_id = uuid.uuid4()
    res = client.get(f"/api/v1/documents/{random_id}")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    del_res = client.delete(f"/api/v1/documents/{random_id}")
    assert del_res.status_code == 404


def test_document_deletion_and_file_cleanup(client: TestClient, pdf_bytes: bytes) -> None:
    files = [("files", ("to_delete.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_res = client.post("/api/v1/documents/upload", files=files)
    doc = upload_res.json()["accepted"][0]
    doc_id = doc["id"]

    # Retrieve details to check physical file path
    get_res = client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 200

    # Delete the document
    del_res = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Confirm it no longer exists in DB
    verify_get = client.get(f"/api/v1/documents/{doc_id}")
    assert verify_get.status_code == 404
