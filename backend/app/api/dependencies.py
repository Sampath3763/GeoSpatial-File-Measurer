"""FastAPI dependencies for request-scoped access to the repository and settings."""

from fastapi import Request

from app.core.config import Settings
from app.core.errors import DatabaseUnavailable
from app.repositories.base import FileRepository


def get_repository(request: Request) -> FileRepository:
    """Return the active repository or raise a service-unavailable error."""
    repository = getattr(request.app.state, "repository", None)
    if repository is None:
        raise DatabaseUnavailable("Database repository is not initialized.")
    return repository


def get_runtime_settings(request: Request) -> Settings:
    """Return the settings instance chosen by the application factory."""
    return request.app.state.settings
