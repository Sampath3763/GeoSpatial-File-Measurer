"""Geometry simplification service using the Douglas-Peucker algorithm.

Returns simplified GeoJSON feature collections for lightweight map rendering.
No web, database, or file-system dependencies (Single Responsibility Principle).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

_MIN_TOLERANCE = 1e-9
_MAX_TOLERANCE = 10.0
DEFAULT_TOLERANCE = 0.0001


@dataclass(slots=True)
class SimplifiedFeature:
    """One Douglas-Peucker simplified feature ready for GeoJSON serialisation."""

    feature_index: int
    geometry_type: str
    original_vertex_count: int
    simplified_vertex_count: int
    reduction_pct: float
    geometry: dict[str, Any] | None


@dataclass
class SimplificationResult:
    """Result of a simplification run over one file's features."""

    file_id: str
    tolerance: float
    feature_count: int
    features: list[SimplifiedFeature]
    total_original_vertices: int
    total_simplified_vertices: int

    @property
    def overall_reduction_pct(self) -> float:
        """Percentage of vertices eliminated across all features."""
        if self.total_original_vertices == 0:
            return 0.0
        return round(
            100.0 * (1 - self.total_simplified_vertices / self.total_original_vertices),
            2,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible summary and feature list."""
        return {
            "file_id": self.file_id,
            "tolerance": self.tolerance,
            "feature_count": self.feature_count,
            "total_original_vertices": self.total_original_vertices,
            "total_simplified_vertices": self.total_simplified_vertices,
            "overall_reduction_pct": self.overall_reduction_pct,
            "features": [
                {
                    "feature_index": f.feature_index,
                    "geometry_type": f.geometry_type,
                    "original_vertex_count": f.original_vertex_count,
                    "simplified_vertex_count": f.simplified_vertex_count,
                    "reduction_pct": f.reduction_pct,
                    "geometry": f.geometry,
                }
                for f in self.features
            ],
        }


def _vertex_count(geom: BaseGeometry) -> int:
    """Count total coordinate tuples in any Shapely geometry."""
    if geom is None or geom.is_empty:
        return 0
    if hasattr(geom, "geoms"):
        return sum(_vertex_count(part) for part in geom.geoms)
    if hasattr(geom, "exterior"):
        count = len(geom.exterior.coords)
        for interior in getattr(geom, "interiors", []):
            count += len(interior.coords)
        return count
    if hasattr(geom, "coords"):
        return len(geom.coords)
    return 0


def _clamp_tolerance(tolerance: float) -> float:
    return max(_MIN_TOLERANCE, min(_MAX_TOLERANCE, float(tolerance)))


def _simplify_one(
    raw_geometry: dict[str, Any] | None,
    tolerance: float,
) -> tuple[BaseGeometry | None, BaseGeometry | None]:
    if not raw_geometry:
        return None, None
    try:
        original = shape(raw_geometry)
        if original.is_empty:
            return original, original
        simplified = original.simplify(tolerance, preserve_topology=True)
        if not simplified.is_valid:
            simplified = make_valid(simplified)
        return original, simplified
    except Exception:
        return None, None


def simplify_features(
    file_id: str,
    features: list[dict[str, Any]],
    tolerance: float = DEFAULT_TOLERANCE,
) -> SimplificationResult:
    """Apply Douglas-Peucker simplification to a list of stored features.

    Parameters
    ----------
    file_id:
        Forwarded to the result for traceability.
    features:
        Raw feature dicts from the repository. Each must have ``feature_index``,
        ``geometry_type``, and ``geometry`` (a GeoJSON geometry dict).
    tolerance:
        Simplification tolerance in native coordinate units.
        For WGS84: 0.0001 approx 11 m at equator.
    """
    safe_tol = _clamp_tolerance(tolerance)
    simplified_features: list[SimplifiedFeature] = []
    total_orig = 0
    total_simp = 0

    for feat in features:
        idx = feat.get("feature_index", 0)
        geom_type = feat.get("geometry_type", "Unknown")
        raw_geom = feat.get("geometry")

        original, simplified = _simplify_one(raw_geom, safe_tol)

        orig_verts = _vertex_count(original) if original else 0
        simp_verts = _vertex_count(simplified) if simplified else 0
        total_orig += orig_verts
        total_simp += simp_verts

        reduction = round(100.0 * (1 - simp_verts / orig_verts), 2) if orig_verts > 0 else 0.0
        geom_dict: dict[str, Any] | None = (
            mapping(simplified) if simplified and not simplified.is_empty else None
        )

        simplified_features.append(
            SimplifiedFeature(
                feature_index=idx,
                geometry_type=geom_type,
                original_vertex_count=orig_verts,
                simplified_vertex_count=simp_verts,
                reduction_pct=reduction,
                geometry=geom_dict,
            )
        )

    return SimplificationResult(
        file_id=file_id,
        tolerance=safe_tol,
        feature_count=len(features),
        features=simplified_features,
        total_original_vertices=total_orig,
        total_simplified_vertices=total_simp,
    )
