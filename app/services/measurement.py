"""Pure geometry measurement functions with no web or database dependencies."""

import math
from dataclasses import dataclass

from shapely import force_2d, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.services.crs import (
    geodesic_length,
    normalize_to_wgs84,
    project_geometry,
    select_measurement_crs,
)


@dataclass(slots=True)
class MeasurementResult:
    """The measurement status and derived values for a single feature."""

    geometry_type: str
    status: str
    area_sq_m: float | None = None
    length_m: float | None = None
    projected_crs: str | None = None
    method: str | None = None
    note: str | None = None


def _polygonal_parts(geometry: BaseGeometry) -> BaseGeometry | None:
    """Keep only polygonal parts returned by make_valid."""
    if isinstance(geometry, Polygon | MultiPolygon):
        return geometry
    if isinstance(geometry, GeometryCollection):
        parts = [part for part in geometry.geoms if isinstance(part, Polygon | MultiPolygon)]
        if parts:
            return unary_union(parts)
    return None


def measure_geometry(
    geometry: BaseGeometry | None,
    source_crs: str | None,
) -> MeasurementResult:
    """Measure supported geometries after normalizing them to WGS84."""
    geometry_type = geometry.geom_type if geometry is not None else "Unknown"
    if geometry is None:
        return MeasurementResult(geometry_type, "UNSUPPORTED", note="Feature has no geometry.")
    geometry = force_2d(geometry)
    geometry_type = geometry.geom_type
    if geometry.is_empty:
        return MeasurementResult(geometry_type, "UNSUPPORTED", note="Geometry is empty.")
    if geometry_type in {"Point", "MultiPoint"}:
        return MeasurementResult(
            geometry_type,
            "NOT_APPLICABLE",
            note="Point geometries do not have area or length measurements.",
        )
    if geometry_type == "GeometryCollection":
        return MeasurementResult(
            geometry_type,
            "UNSUPPORTED",
            note="GeometryCollection is not supported for measurement.",
        )
    if geometry_type not in {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}:
        return MeasurementResult(
            geometry_type,
            "UNSUPPORTED",
            note=f"{geometry_type} is not supported for measurement.",
        )
    if not source_crs:
        return MeasurementResult(
            geometry_type,
            "ERROR",
            note="A source CRS is required to calculate measurements.",
        )

    note = None
    try:
        if geometry_type in {"Polygon", "MultiPolygon"} and not geometry.is_valid:
            repaired = _polygonal_parts(make_valid(geometry))
            if repaired is None or repaired.is_empty:
                return MeasurementResult(
                    geometry_type,
                    "ERROR",
                    note="Invalid polygon could not be repaired into polygonal geometry.",
                )
            geometry = repaired
            note = "geometry repaired"

        normalized = normalize_to_wgs84(geometry, source_crs)
        measurement_crs, method = select_measurement_crs(normalized)
        if method == "geodesic":
            value = geodesic_length(normalized)
            if not math.isfinite(value):
                raise ValueError("Geodesic length is not finite.")
            return MeasurementResult(
                geometry_type,
                "CALCULATED",
                length_m=round(value, 4),
                method=method,
                note=note,
            )

        projected = project_geometry(normalized, measurement_crs)
        if geometry_type in {"Polygon", "MultiPolygon"}:
            area = float(projected.area)
            if not math.isfinite(area):
                raise ValueError("Projected area is not finite.")
            return MeasurementResult(
                geometry_type,
                "CALCULATED",
                area_sq_m=round(area, 4),
                projected_crs=measurement_crs,
                method=method,
                note=note,
            )
        length = float(projected.length)
        if not math.isfinite(length):
            raise ValueError("Projected length is not finite.")
        return MeasurementResult(
            geometry_type,
            "CALCULATED",
            length_m=round(length, 4),
            projected_crs=measurement_crs,
            method=method,
            note=note,
        )
    except Exception as error:
        return MeasurementResult(
            geometry_type,
            "ERROR",
            note=f"Measurement failed: {type(error).__name__}.",
        )
