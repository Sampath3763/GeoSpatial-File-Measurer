"""In-memory repository for isolated unit and API tests."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.models import FeatureRecord
from app.repositories.base import FileRepository


class MemoryRepository(FileRepository):
    """Lightweight in-memory repository with same behavior as persistent backends."""

    def __init__(self) -> None:
        self.files: dict[str, dict[str, Any]] = {}
        self.features: dict[str, list[dict[str, Any]]] = {}
        self.lock = asyncio.Lock()

    @property
    def backend_name(self) -> str:
        return "memory"

    async def health_check(self) -> bool:
        return True

    async def create_file(self, document: dict[str, Any]) -> None:
        """Store a copy of a new file document."""
        async with self.lock:
            self.files[document["id"]] = dict(document)
            self.features.setdefault(document["id"], [])

    async def update_file(self, file_id: str, fields: dict[str, Any]) -> None:
        """Apply fields to an existing file."""
        async with self.lock:
            if file_id in self.files:
                self.files[file_id].update(fields)

    async def insert_features(self, file_id: str, features: list[FeatureRecord]) -> None:
        """Append a batch of serializable feature documents."""
        async with self.lock:
            destination = self.features.setdefault(file_id, [])
            destination.extend(
                {
                    "file_id": file_id,
                    "feature_index": feature.feature_index,
                    "layer": feature.layer,
                    "geometry_type": feature.geometry_type,
                    "geometry": feature.geometry,
                    "crs": feature.crs,
                    "properties": dict(feature.properties)
                    if feature.properties is not None
                    else {},
                    "measurement_status": feature.measurement_status,
                    "area_sq_m": feature.area_sq_m,
                    "length_m": feature.length_m,
                    "projected_crs": feature.projected_crs,
                    "measurement_method": feature.measurement_method,
                    "note": feature.note,
                }
                for feature in features
            )

    async def delete_features(self, file_id: str) -> None:
        """Remove features for one upload."""
        async with self.lock:
            self.features.pop(file_id, None)

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        """Return a defensive copy of a file."""
        async with self.lock:
            document = self.files.get(file_id)
            return dict(document) if document else None

    async def list_files(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """Return newest-first paginated files."""
        async with self.lock:
            ordered = sorted(
                self.files.values(),
                key=lambda item: item.get("created_at", datetime.min.replace(tzinfo=UTC)),
                reverse=True,
            )
            return [dict(item) for item in ordered[offset : offset + limit]], len(ordered)

    async def delete_file(self, file_id: str) -> bool:
        """Delete a file and its in-memory feature records."""
        async with self.lock:
            exists = self.files.pop(file_id, None) is not None
            self.features.pop(file_id, None)
            return exists

    async def get_features(
        self, file_id: str, limit: int, offset: int, geometry_type: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a feature page sorted by index."""
        async with self.lock:
            items = sorted(self.features.get(file_id, []), key=lambda item: item["feature_index"])
            if geometry_type:
                items = [item for item in items if item["geometry_type"] == geometry_type]
            return [dict(item) for item in items[offset : offset + limit]], len(items)

    async def summarize_features(self, file_id: str) -> dict[str, Any]:
        """Calculate summary totals across all in-memory features."""
        async with self.lock:
            geometry_counts: dict[str, int] = {}
            status_counts: dict[str, int] = {}
            total_area = 0.0
            total_length = 0.0
            for feature in self.features.get(file_id, []):
                geometry = feature["geometry_type"]
                status = feature["measurement_status"]
                geometry_counts[geometry] = geometry_counts.get(geometry, 0) + 1
                status_counts[status] = status_counts.get(status, 0) + 1
                if status == "CALCULATED":
                    total_area += feature.get("area_sq_m") or 0.0
                    total_length += feature.get("length_m") or 0.0
            return {
                "total_area_sq_m": round(total_area, 4),
                "total_length_m": round(total_length, 4),
                "counts_by_geometry_type": geometry_counts,
                "counts_by_measurement_status": status_counts,
            }
