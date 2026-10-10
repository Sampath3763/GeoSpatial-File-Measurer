"""Liveness and backend readiness health checks."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_repository
from app.core.errors import DatabaseUnavailable
from app.repositories.base import FileRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/healthz")
@router.get("/api/health")
@router.get("/api/healthz", include_in_schema=True)
async def health(repository: FileRepository = Depends(get_repository)) -> dict[str, str]:
    """Check API and storage backend readiness."""
    try:
        is_healthy = await repository.health_check()
        if not is_healthy:
            raise DatabaseUnavailable("Database health check returned unhealthy.")
        return {"status": "ok", "backend": repository.backend_name}
    except Exception as error:
        logger.warning("Health check failed: %s", error)
        raise DatabaseUnavailable("Database backend is unavailable.") from error
