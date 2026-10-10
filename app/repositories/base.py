"""Abstract repository contract used by the upload service and API."""

from abc import ABC, abstractmethod
from typing import Any

from app.models import FeatureRecord


class FileRepository(ABC):
    """Persistence interface so processing logic is independent of specific storage engine."""

    @property
    def backend_name(self) -> str:
        """Name of the active storage engine (e.g. 'sqlite', 'memory', 'mongodb')."""
        return "base"

    async def health_check(self) -> bool:
        """Verify storage engine readiness."""
        return True

    @abstractmethod
    async def create_file(self, document: dict[str, Any]) -> None:
        """Insert the initial file document."""

    @abstractmethod
    async def update_file(self, file_id: str, fields: dict[str, Any]) -> None:
        """Update file metadata and processing status."""

    @abstractmethod
    async def insert_features(self, file_id: str, features: list[FeatureRecord]) -> None:
        """Insert one batch of feature documents."""

    @abstractmethod
    async def delete_features(self, file_id: str) -> None:
        """Remove all features for one upload."""

    @abstractmethod
    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        """Get one file document."""

    @abstractmethod
    async def list_files(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """Return a newest-first page and the total number of uploaded files."""

    @abstractmethod
    async def delete_file(self, file_id: str) -> bool:
        """Delete a file and its feature records; return whether it existed."""

    @abstractmethod
    async def get_features(
        self, file_id: str, limit: int, offset: int, geometry_type: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Return an ordered page of feature documents and its filtered total."""

    @abstractmethod
    async def summarize_features(self, file_id: str) -> dict[str, Any]:
        """Aggregate whole-file counts and measurement totals."""
