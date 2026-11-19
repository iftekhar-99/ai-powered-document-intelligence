from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CapabilitiesResponse(BaseModel):
    pdf_digital_extraction: bool = Field(..., description="PDF text extraction via PyMuPDF")
    tesseract_available: bool = Field(..., description="Tesseract OCR binary installed on host")
    tesseract_executable: str = Field(..., description="Path to Tesseract executable or 'not found'")
    tesseract_version: str = Field(..., description="Tesseract version or 'unavailable'")
    ocr_languages: List[str] = Field(default_factory=list, description="Available OCR language packs")
    xlsx_processing: bool = Field(..., description="XLSX workbook parsing via OpenPyXL")
    xls_processing: bool = Field(..., description="XLS legacy spreadsheet parsing via xlrd")
    csv_processing: bool = Field(..., description="CSV delimited text parsing")
    include_hidden_sheets: bool = Field(..., description="Whether hidden worksheets are processed")
    background_processing_mode: str = Field(..., description="Active background processing mode ('inline' or 'celery')")
    redis_connected: bool = Field(..., description="Actual Redis socket connection status")
    redis_status: str = Field(..., description="Human-readable Redis connectivity status")


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["healthy"])
    app_name: str = Field(..., examples=["Financial Document Intelligence System"])
    version: str = Field(..., examples=["0.1.0"])
    environment: str = Field(..., examples=["development"])
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    services: Dict[str, str] = Field(
        default_factory=lambda: {
            "api": "online",
            "database": "configured",
            "redis": "configured",
        }
    )
    capabilities: Optional[CapabilitiesResponse] = None
