from fastapi import APIRouter
from app.api.v1.endpoints import (
    dashboard,
    documents,
    extraction_runs,
    health,
    invoices,
    search,
    validation,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
api_router.include_router(extraction_runs.router, prefix="/extraction-runs", tags=["Extraction Runs"])
api_router.include_router(validation.router, tags=["Validation"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
