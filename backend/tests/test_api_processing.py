import io
import uuid
from fastapi.testclient import TestClient


def test_api_process_and_retrieve_chunks_and_summary(
    client: TestClient, pdf_bytes: bytes
) -> None:
    # 1. Upload document with auto_process=False to inspect manual process endpoint
    files = [("files", ("invoice_endpoint_test.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_res = client.post("/api/v1/documents/upload?auto_process=false", files=files)
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["accepted"][0]["id"]

    # 2. Trigger manual processing endpoint
    proc_res = client.post(f"/api/v1/documents/{doc_id}/process?force_reprocess=true")
    assert proc_res.status_code == 202
    proc_data = proc_res.json()
    assert proc_data["status"] == "queued"
    assert proc_data["document_id"] == doc_id

    # 3. Get processing summary
    summary_res = client.get(f"/api/v1/documents/{doc_id}/processing-summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["document_id"] == doc_id
    assert "status" in summary
    assert "processing_events" in summary

    # 4. Get chunks endpoint
    chunks_res = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks_res.status_code == 200
    chunks_data = chunks_res.json()
    assert "items" in chunks_data
    assert "total" in chunks_data


def test_api_endpoints_nonexistent_document(client: TestClient) -> None:
    random_id = uuid.uuid4()
    assert client.post(f"/api/v1/documents/{random_id}/process").status_code == 404
    assert client.get(f"/api/v1/documents/{random_id}/chunks").status_code == 404
    assert client.get(f"/api/v1/documents/{random_id}/processing-summary").status_code == 404
