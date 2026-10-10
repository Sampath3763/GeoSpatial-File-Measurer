"""Analytics endpoints: multi-unit measurements, topology audit, PDF report, simplification.

All heavy computation is delegated to pure service modules; this router only:
  - validates the file_id and existence
  - calls the appropriate service
  - serialises the result

This satisfies the Dependency Inversion Principle: the router depends on the
FileRepository abstraction, not on any concrete storage engine.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.dependencies import get_repository
from app.core.errors import AppError
from app.repositories.base import FileRepository
from app.schemas.analytics import (
    MultiUnitMeasurementsPage,
    SimplificationResponse,
    TopologyAuditResponse,
)

router = APIRouter(prefix="/api/files", tags=["analytics"])

_FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


async def _get_completed_file(
    file_id: str,
    repository: FileRepository,
) -> dict[str, Any]:
    """Validate format, existence, and COMPLETED status."""
    if not _FILE_ID_PATTERN.fullmatch(file_id):
        raise _not_found()
    document = await repository.get_file(file_id)
    if document is None:
        raise _not_found()
    if document["status"] != "COMPLETED":
        raise AppError(
            "FILE_NOT_READY",
            "This endpoint is available only after file processing is completed.",
            409,
            {"status": document["status"]},
        )
    return document


def _not_found() -> AppError:
    return AppError("FILE_NOT_FOUND", "The requested file was not found.", 404)


@router.get(
    "/{file_id}/measurements/units",
    response_model=MultiUnitMeasurementsPage,
    include_in_schema=False,
)
@router.get("/{file_id}/measurements/units/", response_model=MultiUnitMeasurementsPage)
async def get_measurements_multi_unit(
    file_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    geometry_type: str | None = Query(default=None),
    repository: FileRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return measurements converted into all supported units.

    Area units  : sq_m, sq_km, sq_ft, sq_mi, hectares, acres
    Length units: m, km, ft, mi, nautical_miles

    All conversions use exact SI factors with no external calls.
    """
    from app.services.unit_conversion import (
        build_full_area_breakdown,
        build_full_length_breakdown,
    )

    document = await _get_completed_file(file_id, repository)
    features, filtered_total = await repository.get_features(file_id, limit, offset, geometry_type)
    summary_raw = await repository.summarize_features(file_id)

    feature_list: list[dict[str, Any]] = []
    for feat in features:
        geom_type = feat["geometry_type"]
        status = feat["measurement_status"]
        area_bd: dict[str, Any] | None = None
        length_bd: dict[str, Any] | None = None

        if status == "CALCULATED":
            if geom_type in {"Polygon", "MultiPolygon"}:
                val = feat.get("area_sq_m")
                if val is not None:
                    area_bd = build_full_area_breakdown(val)
            elif geom_type in {"LineString", "MultiLineString"}:
                val = feat.get("length_m")
                if val is not None:
                    length_bd = build_full_length_breakdown(val)

        feature_list.append(
            {
                "feature_index": feat["feature_index"],
                "layer": feat.get("layer"),
                "geometry_type": geom_type,
                "measurement_status": status,
                "area": area_bd,
                "length": length_bd,
                "projected_crs": feat.get("projected_crs"),
                "method": feat.get("measurement_method"),
                "note": feat.get("note"),
            }
        )

    summary = {
        "total_area": build_full_area_breakdown(summary_raw["total_area_sq_m"]),
        "total_length": build_full_length_breakdown(summary_raw["total_length_m"]),
        "counts_by_geometry_type": summary_raw["counts_by_geometry_type"],
        "counts_by_measurement_status": summary_raw["counts_by_measurement_status"],
    }

    return {
        "file_id": file_id,
        "status": document["status"],
        "crs": document.get("crs"),
        "feature_count": document["feature_count"],
        "summary": summary,
        "pagination": {"limit": limit, "offset": offset, "returned": len(feature_list)},
        "features": feature_list,
        "filtered_total": filtered_total,
    }


@router.get(
    "/{file_id}/quality-audit",
    response_model=TopologyAuditResponse,
    include_in_schema=False,
)
@router.get("/{file_id}/quality-audit/", response_model=TopologyAuditResponse)
async def get_topology_audit(
    file_id: str,
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
        description="Maximum number of features to inspect.",
    ),
    repository: FileRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Run a topology quality audit and return a 0-100 health score.

    Checks performed per polygon feature:

    * Self-intersecting rings (bow-tie / figure-8)
    * Sliver polygons (isoperimetric quotient < 0.05)
    * Duplicate consecutive vertices
    * Spike vertices (interior angle < 5 degrees)
    * Null / empty geometries

    Quality score: starts at 100, deducted 5 per error and 1 per warning.
    """
    from app.services.topology_audit import audit_features

    await _get_completed_file(file_id, repository)
    features, _ = await repository.get_features(file_id, limit=limit, offset=0)
    report = audit_features(file_id=file_id, features=features)
    return report.to_dict()


@router.get(
    "/{file_id}/report.pdf",
    include_in_schema=False,
    responses={200: {"content": {"application/pdf": {}}}},
)
@router.get(
    "/{file_id}/report",
    summary="Download PDF measurement certificate",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_pdf_report(
    file_id: str,
    repository: FileRepository = Depends(get_repository),
) -> Response:
    """Generate and stream a PDF measurement certificate.

    The certificate contains:

    * Project metadata (filename, ID, upload time, SHA-256 placeholder)
    * CRS audit (source CRS, measurement projection, datum)
    * Aggregate measurements in all units (sq m, ha, ac, km2 / m, km, mi)
    * Top-15 largest polygon features table
    """
    from app.services.pdf_report import generate_pdf_report

    document = await _get_completed_file(file_id, repository)
    summary = await repository.summarize_features(file_id)
    top_features_raw, _ = await repository.get_features(
        file_id,
        limit=15,
        offset=0,
        geometry_type="Polygon",
    )

    pdf_bytes = generate_pdf_report(
        file_doc=document,
        summary=summary,
        top_features=top_features_raw,
        sha256_hash=None,
    )

    safe_name = re.sub(r"[^\w\-.]", "_", document.get("filename", file_id))
    filename = f"{safe_name}_measurement_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get(
    "/{file_id}/features/simplified",
    response_model=SimplificationResponse,
    include_in_schema=False,
)
@router.get(
    "/{file_id}/features/simplified/",
    response_model=SimplificationResponse,
)
async def get_simplified_features(
    file_id: str,
    tolerance: float = Query(
        default=0.0001,
        ge=1e-9,
        le=10.0,
        description=(
            "Douglas-Peucker tolerance in coordinate units. "
            "For WGS84: 0.0001 approx 11 m, 0.001 approx 111 m, 0.01 approx 1.1 km."
        ),
    ),
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
        description="Maximum number of features to simplify and return.",
    ),
    geometry_type: str | None = Query(
        default=None,
        description="Filter by geometry type (e.g. Polygon, LineString).",
    ),
    repository: FileRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Return Douglas-Peucker simplified geometries for fast map rendering.

    Reduces coordinate counts by 80-95% while preserving shape topology.
    Each feature response includes original and simplified vertex counts
    and the reduction percentage achieved.
    """
    from app.services.simplification import simplify_features

    await _get_completed_file(file_id, repository)
    features, _ = await repository.get_features(
        file_id, limit=limit, offset=0, geometry_type=geometry_type
    )
    result = simplify_features(
        file_id=file_id,
        features=features,
        tolerance=tolerance,
    )
    return result.to_dict()
