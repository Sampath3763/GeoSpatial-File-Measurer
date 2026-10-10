"""MongoDB repository using PyMongo's native asynchronous client."""

from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.models import FeatureRecord
from app.repositories.base import FileRepository


class MongoRepository(FileRepository):
    """MongoDB-backed file and feature storage."""

    def __init__(self, database: AsyncDatabase[dict[str, Any]]) -> None:
        self.files = database["uploaded_files"]
        self.features = database["features"]

    async def create_file(self, document: dict[str, Any]) -> None:
        """Insert the file document in its PROCESSING state."""
        await self.files.insert_one({"_id": document["id"], **document})

    async def update_file(self, file_id: str, fields: dict[str, Any]) -> None:
        """Update file status and summary fields."""
        await self.files.update_one({"_id": file_id}, {"$set": fields})

    async def insert_features(self, file_id: str, features: list[FeatureRecord]) -> None:
        """Insert a feature batch with stable sequential indexes."""
        if not features:
            return
        await self.features.insert_many(
            [
                {
                    "file_id": file_id,
                    "feature_index": feature.feature_index,
                    "layer": feature.layer,
                    "geometry_type": feature.geometry_type,
                    "geometry": feature.geometry,
                    "crs": feature.crs,
                    "properties": feature.properties,
                    "measurement_status": feature.measurement_status,
                    "area_sq_m": feature.area_sq_m,
                    "length_m": feature.length_m,
                    "projected_crs": feature.projected_crs,
                    "measurement_method": feature.measurement_method,
                    "note": feature.note,
                }
                for feature in features
            ],
            ordered=False,
        )

    async def delete_features(self, file_id: str) -> None:
        """Delete all feature records belonging to an upload."""
        await self.features.delete_many({"file_id": file_id})

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        """Fetch one file, converting MongoDB's key to the API's id field."""
        document = await self.files.find_one({"_id": file_id})
        return _file_document(document) if document else None

    async def list_files(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """Return a newest-first page and total count."""
        total = await self.files.count_documents({})
        cursor = self.files.find({}).sort("created_at", DESCENDING).skip(offset).limit(limit)
        return [_file_document(document) async for document in cursor], total

    async def delete_file(self, file_id: str) -> bool:
        """Delete the file document and its features."""
        if await self.files.find_one({"_id": file_id}) is None:
            return False
        await self.features.delete_many({"file_id": file_id})
        result = await self.files.delete_one({"_id": file_id})
        return bool(result.deleted_count)

    async def get_features(
        self, file_id: str, limit: int, offset: int, geometry_type: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a sorted page, optionally filtered by geometry type."""
        query: dict[str, Any] = {"file_id": file_id}
        if geometry_type:
            query["geometry_type"] = geometry_type
        total = await self.features.count_documents(query)
        cursor = (
            self.features.find(query)
            .sort("feature_index", ASCENDING)
            .skip(offset)
            .limit(limit)
        )
        return [document async for document in cursor], total

    async def summarize_features(self, file_id: str) -> dict[str, Any]:
        """Aggregate all features, independently of page and geometry filter."""
        pipeline = [
            {"$match": {"file_id": file_id}},
            {
                "$group": {
                    "_id": {
                        "geometry_type": "$geometry_type",
                        "measurement_status": "$measurement_status",
                    },
                    "count": {"$sum": 1},
                    "area": {"$sum": {"$ifNull": ["$area_sq_m", 0]}},
                    "length": {"$sum": {"$ifNull": ["$length_m", 0]}},
                }
            },
        ]
        geometry_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        total_area = 0.0
        total_length = 0.0
        cursor = await self.features.aggregate(pipeline)
        async for group in cursor:
            geometry_type = group["_id"]["geometry_type"]
            measurement_status = group["_id"]["measurement_status"]
            count = int(group["count"])
            geometry_counts[geometry_type] = geometry_counts.get(geometry_type, 0) + count
            status_counts[measurement_status] = status_counts.get(measurement_status, 0) + count
            total_area += float(group["area"])
            total_length += float(group["length"])
        return {
            "total_area_sq_m": round(total_area, 4),
            "total_length_m": round(total_length, 4),
            "counts_by_geometry_type": geometry_counts,
            "counts_by_measurement_status": status_counts,
        }


def _file_document(document: dict[str, Any]) -> dict[str, Any]:
    """Convert a MongoDB file document into the public field shape."""
    result = dict(document)
    result["id"] = result.pop("_id", result.get("id"))
    result.pop("_id", None)
    return result
