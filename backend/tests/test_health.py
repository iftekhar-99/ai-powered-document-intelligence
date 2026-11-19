from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "docs" in data
    assert "health" in data


def test_root_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "services" in data
    assert data["services"]["api"] == "online"


def test_api_v1_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert data["app_name"] == "Financial Document Intelligence System"
    assert "capabilities" in data
    caps = data["capabilities"]
    assert caps["pdf_digital_extraction"] is True
    assert caps["xlsx_processing"] is True
    assert caps["xls_processing"] is True
    assert caps["csv_processing"] is True
    assert "background_processing_mode" in caps
    assert "redis_status" in caps


def test_api_v1_capabilities_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["pdf_digital_extraction"] is True
    assert "tesseract_available" in data
    assert "ocr_languages" in data
    assert data["xlsx_processing"] is True
    assert data["xls_processing"] is True
    assert data["csv_processing"] is True
    assert data["include_hidden_sheets"] is True
    assert data["background_processing_mode"] == "inline"
    assert "redis_connected" in data
