"""Upload orchestration: validate, read, measure, persist, and finalize."""

import asyncio
import logging
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import (
    AppError,
    FileProcessingError,
    ReaderValidationError,
    TooManyFeatures,
)
from app.models import FeatureRecord
from app.repositories.base import FileRepository
from app.services.geo_reader import read_and_measure
from app.services.upload_validation import (
    sanitize_filename,
    save_upload_stream,
    validate_shapefile_archive,
)

logger = logging.getLogger(__name__)
PERSIST_BATCH_SIZE = 1_000


class FileService:
    """Coordinate upload processing without coupling to a storage engine."""

    def __init__(self, repository: FileRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def upload(self, upload: UploadFile | None) -> dict[str, Any]:
        """Validate and process one KML or zipped Shapefile upload."""
        if upload is None:
            raise AppError("FILE_REQUIRED", "A file is required in the 'file' field.", 400)
        filename = sanitize_filename(upload.filename)
        extension = Path(filename).suffix.lower()
        if extension not in {".zip", ".kml"}:
            await upload.close()
            raise AppError(
                "UNSUPPORTED_FILE_TYPE",
                "Only .zip Shapefiles and .kml files are supported.",
                415,
            )

        file_type = "shapefile" if extension == ".zip" else "kml"
        file_id = uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix="geo-measurement-") as temp_dir:
            path = Path(temp_dir) / ("upload.zip" if extension == ".zip" else "upload.kml")
            size_bytes = await save_upload_stream(upload, str(path), self.settings)
            if file_type == "shapefile":
                validate_shapefile_archive(str(path), self.settings)

            created_at = datetime.now(UTC)
            file_document: dict[str, Any] = {
                "id": file_id,
                "filename": filename,
                "file_type": file_type,
                "size_bytes": size_bytes,
                "crs": None,
                "feature_count": 0,
                "status": "PROCESSING",
                "error_message": None,
                "warnings": [],
                "geometry_type_counts": {},
                "created_at": created_at,
                "completed_at": None,
            }
            await self.repository.create_file(file_document)
            try:
                features, crs, warnings = await asyncio.to_thread(
                    read_and_measure,
                    path,
                    file_type,
                    self.settings.max_features_per_file,
                )
                if not features:
                    warnings.append("The file contains no features.")
                for start in range(0, len(features), PERSIST_BATCH_SIZE):
                    await self.repository.insert_features(
                        file_id,
                        features[start : start + PERSIST_BATCH_SIZE],
                    )
                geometry_counts = _count_geometry_types(features)
                completed_at = datetime.now(UTC)
                await self.repository.update_file(
                    file_id,
                    {
                        "crs": crs,
                        "feature_count": len(features),
                        "geometry_type_counts": geometry_counts,
                        "warnings": list(dict.fromkeys(warnings)),
                        "status": "COMPLETED",
                        "completed_at": completed_at,
                    },
                )
                result = dict(file_document)
                result.update(
                    {
                        "crs": crs,
                        "feature_count": len(features),
                        "geometry_type_counts": geometry_counts,
                        "warnings": list(dict.fromkeys(warnings)),
                        "status": "COMPLETED",
                        "completed_at": completed_at,
                    }
                )
                return result
            except TooManyFeatures as error:
                await self._mark_failed(file_id, str(error))
                raise TooManyFeatures(self.settings.max_features_per_file, file_id) from error
            except Exception as error:
                logger.exception("File processing failed for upload %s", file_id)
                message = (
                    str(error)
                    if isinstance(error, ReaderValidationError)
                    else "The file could not be read or measured."
                )
                await self._mark_failed(file_id, message)
                if isinstance(error, AppError):
                    raise
                raise FileProcessingError(
                    message,
                    file_id,
                ) from error

    async def _mark_failed(self, file_id: str, message: str) -> None:
        """Best-effort rollback for feature batches and mark the upload failed."""
        await self.repository.delete_features(file_id)
        await self.repository.update_file(
            file_id,
            {
                "status": "FAILED",
                "error_message": message,
                "completed_at": datetime.now(UTC),
            },
        )


def _count_geometry_types(features: list[FeatureRecord]) -> dict[str, int]:
    """Count features by their reported geometry type."""
    counts: dict[str, int] = {}
    for feature in features:
        counts[feature.geometry_type] = counts.get(feature.geometry_type, 0) + 1
    return counts
