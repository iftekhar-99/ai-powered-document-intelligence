"""
Extraction run status and inspection endpoints.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.extraction_run import ExtractionRun
from app.schemas.extraction_api import ExtractionRunResponse

router = APIRouter()


@router.get(
    "/{run_id}",
    response_model=ExtractionRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get extraction run status",
    description="Retrieve the current status, metrics, context counts, and execution details of a specific extraction run.",
)
async def get_extraction_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ExtractionRunResponse:
    query = select(ExtractionRun).where(ExtractionRun.id == run_id)
    run = (await db.execute(query)).scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ExtractionRun with ID '{run_id}' not found.",
        )

    return ExtractionRunResponse.model_validate(run)
