"""Geometry topology health audit service.

Analyses Shapely geometries for common digitizing errors and returns a
structured quality report.  No web, database, or file-system dependencies
(Single Responsibility Principle).

Checks performed
----------------
* Self-intersecting rings    - bow-tie / figure-8 polygons
* Sliver polygons            - isoperimetric quotient below threshold
* Duplicate consecutive vertices
* Spike vertices             - extreme interior angles
* Empty / null geometries
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

_SLIVER_IQ_THRESHOLD = 0.05
_SPIKE_ANGLE_THRESHOLD_DEG = 5.0


@dataclass(slots=True)
class IssueLocation:
    """Approximate location of a detected geometry problem."""

    feature_index: int
    coordinate_index: int | None = None
    longitude: float | None = None
    latitude: float | None = None
    description: str = ""


@dataclass
class TopologyIssue:
    """A single topology defect found in one feature."""

    issue_type: str
    severity: str  # "error" | "warning" | "info"
    feature_index: int
    geometry_type: str
    description: str
    locations: list[IssueLocation] = field(default_factory=list)


@dataclass
class TopologyAuditReport:
    """Full quality-audit result for one uploaded file."""

    file_id: str
    feature_count: int
    audited_count: int
    issues: list[TopologyIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    quality_score: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dictionary."""
        return {
            "file_id": self.file_id,
            "feature_count": self.feature_count,
            "audited_count": self.audited_count,
            "quality_score": round(self.quality_score, 1),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [
                {
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "feature_index": i.feature_index,
                    "geometry_type": i.geometry_type,
                    "description": i.description,
                    "locations": [
                        {
                            "coordinate_index": loc.coordinate_index,
                            "longitude": loc.longitude,
                            "latitude": loc.latitude,
                            "description": loc.description,
                        }
                        for loc in i.locations
                    ],
                }
                for i in self.issues
            ],
        }


def _angle_at_vertex(
    prev: tuple[float, float],
    curr: tuple[float, float],
    nxt: tuple[float, float],
) -> float:
    """Return the interior angle in degrees at curr."""
    ax, ay = prev[0] - curr[0], prev[1] - curr[1]
    bx, by = nxt[0] - curr[0], nxt[1] - curr[1]
    dot = ax * bx + ay * by
    mag_a = math.hypot(ax, ay)
    mag_b = math.hypot(bx, by)
    if mag_a == 0 or mag_b == 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
    return math.degrees(math.acos(cos_angle))


def _isoperimetric_quotient(polygon: Polygon) -> float:
    """Return 4*pi*area/perimeter^2 — 1 for circle, ~0 for sliver."""
    perimeter = polygon.exterior.length
    if perimeter == 0:
        return 0.0
    return (4 * math.pi * polygon.area) / (perimeter**2)


def _check_polygon(polygon: Polygon, feature_index: int) -> list[TopologyIssue]:
    """Run all polygon-specific checks."""
    issues: list[TopologyIssue] = []

    if not polygon.is_valid:
        issues.append(
            TopologyIssue(
                issue_type="SELF_INTERSECTION",
                severity="error",
                feature_index=feature_index,
                geometry_type="Polygon",
                description=(
                    "Polygon rings self-intersect (bow-tie / figure-8). "
                    "This causes incorrect area calculations."
                ),
            )
        )

    iq = _isoperimetric_quotient(polygon)
    if 0 < iq < _SLIVER_IQ_THRESHOLD:
        issues.append(
            TopologyIssue(
                issue_type="SLIVER_POLYGON",
                severity="warning",
                feature_index=feature_index,
                geometry_type="Polygon",
                description=(
                    f"Polygon has a very low isoperimetric quotient "
                    f"({iq:.4f} < {_SLIVER_IQ_THRESHOLD}), indicating a sliver artefact."
                ),
            )
        )

    if polygon.is_empty:
        issues.append(
            TopologyIssue(
                issue_type="EMPTY_GEOMETRY",
                severity="error",
                feature_index=feature_index,
                geometry_type="Polygon",
                description="Polygon geometry is empty and contains no coordinates.",
            )
        )
        return issues

    coords = list(polygon.exterior.coords)
    dup_locs: list[IssueLocation] = []
    spike_locs: list[IssueLocation] = []
    for i in range(1, len(coords) - 1):
        if coords[i] == coords[i - 1]:
            dup_locs.append(
                IssueLocation(
                    feature_index=feature_index,
                    coordinate_index=i,
                    longitude=coords[i][0],
                    latitude=coords[i][1],
                    description="Duplicate vertex",
                )
            )
        angle = _angle_at_vertex(coords[i - 1], coords[i], coords[i + 1])
        if angle < _SPIKE_ANGLE_THRESHOLD_DEG:
            spike_locs.append(
                IssueLocation(
                    feature_index=feature_index,
                    coordinate_index=i,
                    longitude=coords[i][0],
                    latitude=coords[i][1],
                    description=f"Spike vertex with interior angle {angle:.1f} deg",
                )
            )

    if dup_locs:
        issues.append(
            TopologyIssue(
                issue_type="DUPLICATE_VERTICES",
                severity="warning",
                feature_index=feature_index,
                geometry_type="Polygon",
                description=(
                    f"{len(dup_locs)} duplicate consecutive vertex pair(s) "
                    "found on the exterior ring."
                ),
                locations=dup_locs,
            )
        )
    if spike_locs:
        issues.append(
            TopologyIssue(
                issue_type="SPIKE_VERTICES",
                severity="warning",
                feature_index=feature_index,
                geometry_type="Polygon",
                description=(
                    f"{len(spike_locs)} spike vertex/vertices with interior angle "
                    f"< {_SPIKE_ANGLE_THRESHOLD_DEG} deg detected."
                ),
                locations=spike_locs,
            )
        )

    return issues


def _audit_geometry(
    geometry: BaseGeometry | None,
    feature_index: int,
) -> list[TopologyIssue]:
    """Dispatch topology checks based on geometry type."""
    if geometry is None:
        return [
            TopologyIssue(
                issue_type="NULL_GEOMETRY",
                severity="error",
                feature_index=feature_index,
                geometry_type="Unknown",
                description="Feature has no geometry.",
            )
        ]

    issues: list[TopologyIssue] = []
    geom_type = geometry.geom_type

    if geom_type == "Polygon":
        issues.extend(_check_polygon(geometry, feature_index))
    elif geom_type == "MultiPolygon":
        assert isinstance(geometry, MultiPolygon)
        for part in geometry.geoms:
            issues.extend(_check_polygon(part, feature_index))

    return issues


def audit_features(file_id: str, features: list[dict]) -> TopologyAuditReport:
    """Run topology audit over a list of stored feature dictionaries.

    Parameters
    ----------
    file_id:
        The file UUID string, forwarded to the report for traceability.
    features:
        Raw feature dicts from ``FileRepository.get_features``. Each dict
        must contain ``feature_index``, ``geometry_type``, and ``geometry``
        (a GeoJSON geometry dict).
    """
    from shapely.geometry import shape

    all_issues: list[TopologyIssue] = []
    audited = 0

    for feat in features:
        idx = feat.get("feature_index", 0)
        raw_geom = feat.get("geometry")
        shapely_geom: BaseGeometry | None = None
        if raw_geom is not None:
            try:
                shapely_geom = shape(raw_geom)
            except Exception:
                shapely_geom = None

        feature_issues = _audit_geometry(shapely_geom, idx)
        all_issues.extend(feature_issues)
        audited += 1

    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    penalty = min(100.0, error_count * 5.0 + warning_count * 1.0)
    quality_score = max(0.0, 100.0 - penalty)

    return TopologyAuditReport(
        file_id=file_id,
        feature_count=len(features),
        audited_count=audited,
        issues=all_issues,
        error_count=error_count,
        warning_count=warning_count,
        quality_score=quality_score,
    )
