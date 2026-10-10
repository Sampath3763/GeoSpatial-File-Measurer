"""Upload and inspect geospatial files."""

import re
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from app.api.dependencies import get_repository, get_runtime_settings
from app.core.config import Settings
from app.core.errors import AppError
from app.repositories.base import FileRepository
from app.schemas.files import FeaturePage, FileInfo, FileList, MeasurementsPage
from app.services.file_service import FileService

router = APIRouter(prefix="/api/files", tags=["files"])
FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@router.get("", response_model=FileList, include_in_schema=False)
@router.get("/", response_model=FileList)
async def list_files(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repository: FileRepository = Depends(get_repository),
) -> dict[str, Any]:
    """List recently uploaded files."""
    files, total = await repository.list_files(limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "files": files}


@router.post("", response_model=FileInfo, status_code=201, include_in_schema=False)
@router.post("/", response_model=FileInfo, status_code=201)
async def upload_file(
    file: UploadFile | None = File(default=None),
    repository: FileRepository = Depends(get_repository),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    """Accept a file (.kml or .zip Shapefile) and synchronously process its geospatial features."""
    return await FileService(repository, settings).upload(file)


@router.get("/{file_id}", response_model=FileInfo, include_in_schema=False)
@router.get("/{file_id}/", response_model=FileInfo)
async def get_file(
    file_id: str,
    repository: FileRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return metadata about one uploaded file."""
    document = await _get_file_or_404(file_id, repository)
    return document


@router.delete("/{file_id}", status_code=204, include_in_schema=False)
@router.delete("/{file_id}/", status_code=204)
async def delete_file(
    file_id: str,
    repository: FileRepository = Depends(get_repository),
) -> Response:
    """Delete file metadata and every stored feature."""
    _validate_file_id(file_id)
    deleted = await repository.delete_file(file_id)
    if not deleted:
        raise _not_found()
    return Response(status_code=204)


@router.get("/{file_id}/measurements", response_model=MeasurementsPage, include_in_schema=False)
@router.get("/{file_id}/measurements/", response_model=MeasurementsPage)
async def get_file_measurements(
    file_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    geometry_type: str | None = Query(default=None),
    repository: FileRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return a measurement page and a whole-file aggregate summary."""
    document = await _get_file_or_404(file_id, repository)
    if document["status"] != "COMPLETED":
        raise AppError(
            "FILE_NOT_READY",
            "Measurements are available only after file processing is completed.",
            409,
            {"status": document["status"]},
        )
    features, filtered_total = await repository.get_features(
        file_id,
        limit,
        offset,
        geometry_type,
    )
    summary = await repository.summarize_features(file_id)
    return {
        "file_id": file_id,
        "status": document["status"],
        "crs": document.get("crs"),
        "feature_count": document["feature_count"],
        "summary": summary,
        "pagination": {"limit": limit, "offset": offset, "returned": len(features)},
        "features": [_measurement_view(feature) for feature in features],
        "filtered_total": filtered_total,
    }


@router.get("/{file_id}/features", response_model=FeaturePage, include_in_schema=False)
@router.get("/{file_id}/features/", response_model=FeaturePage)
async def get_file_features(
    file_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_geometry: bool = Query(
        default=True,
        description="Whether to include full coordinate arrays (set to false for fast preview of large geometries in browser UI)",
    ),
    repository: FileRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return paginated source geometries and attributes."""
    await _get_file_or_404(file_id, repository)
    features, total = await repository.get_features(file_id, limit, offset)
    return {
        "file_id": file_id,
        "limit": limit,
        "offset": offset,
        "total": total,
        "features": [
            {
                "feature_index": feature["feature_index"],
                "geometry_type": feature["geometry_type"],
                "geometry": feature.get("geometry") if include_geometry else None,
                "crs": feature.get("crs"),
                "properties": feature.get("properties", {}),
            }
            for feature in features
        ],
    }


async def _get_file_or_404(file_id: str, repository: FileRepository) -> dict[str, Any]:
    """Validate the public id format and return the file document."""
    _validate_file_id(file_id)
    document = await repository.get_file(file_id)
    if document is None:
        raise _not_found()
    return document


def _validate_file_id(file_id: str) -> None:
    """Reject malformed ids using the same not-found response as unknown ids."""
    if not FILE_ID_PATTERN.fullmatch(file_id):
        raise _not_found()


def _not_found() -> AppError:
    """Return a consistent file-not-found error."""
    return AppError("FILE_NOT_FOUND", "The requested file was not found.", 404)


def _measurement_view(feature: dict[str, Any]) -> dict[str, Any]:
    """Convert stored metre values into the requested response units."""
    geometry_type = feature["geometry_type"]
    measurements: dict[str, float | None] | None = None
    if feature["measurement_status"] == "CALCULATED":
        if geometry_type in {"Polygon", "MultiPolygon"}:
            area = feature.get("area_sq_m")
            measurements = {
                "area_sq_m": area,
                "area_hectares": round(area / 10_000, 4) if area is not None else None,
                "area_sq_km": round(area / 1_000_000, 4) if area is not None else None,
            }
        elif geometry_type in {"LineString", "MultiLineString"}:
            length = feature.get("length_m")
            measurements = {
                "length_m": length,
                "length_km": round(length / 1_000, 4) if length is not None else None,
            }
    return {
        "feature_index": feature["feature_index"],
        "layer": feature.get("layer"),
        "geometry_type": geometry_type,
        "measurement_status": feature["measurement_status"],
        "measurements": measurements,
        "projected_crs": feature.get("projected_crs"),
        "method": feature.get("measurement_method"),
        "note": feature.get("note"),
    }
