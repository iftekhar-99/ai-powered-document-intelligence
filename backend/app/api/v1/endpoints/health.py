from fastapi import APIRouter, status
from app.core.capabilities import get_system_capabilities
from app.core.config import settings
from app.db.session import DB_PROVIDER
from app.schemas.health import CapabilitiesResponse, HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Check the operational status of the API, database, redis and document capabilities.",
)
async def check_health() -> HealthResponse:
    capabilities_dict = get_system_capabilities()
    capabilities = CapabilitiesResponse(**capabilities_dict)

    redis_service_status = capabilities_dict["redis_status"]

    return HealthResponse(
        status="healthy",
        app_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.APP_ENV,
        services={
            "api": "online",
            "database": f"{DB_PROVIDER} (active)",
            "redis": redis_service_status,
        },
        capabilities=capabilities,
    )


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    status_code=status.HTTP_200_OK,
    summary="System Processing Capabilities",
    description="Query detailed document extraction and OCR capabilities of the host environment.",
)
async def get_capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(**get_system_capabilities())
