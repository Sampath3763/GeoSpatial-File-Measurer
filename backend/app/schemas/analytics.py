"""Response schemas for analytics endpoints.

Pure Pydantic data-transfer objects - no business logic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UnitValue(BaseModel):
    """A single measurement value with its human-readable label."""

    value: float
    label: str


class AreaBreakdown(BaseModel):
    """Area expressed in every supported unit."""

    sq_m: UnitValue
    sq_km: UnitValue
    sq_ft: UnitValue
    sq_mi: UnitValue
    hectares: UnitValue
    acres: UnitValue

    model_config = ConfigDict(extra="ignore")


class LengthBreakdown(BaseModel):
    """Length expressed in every supported unit."""

    m: UnitValue
    km: UnitValue
    ft: UnitValue
    mi: UnitValue
    nautical_miles: UnitValue

    model_config = ConfigDict(extra="ignore")


class FeatureUnitMeasurement(BaseModel):
    """Multi-unit measurement for one feature."""

    feature_index: int
    layer: str | None = None
    geometry_type: str
    measurement_status: Literal["CALCULATED", "NOT_APPLICABLE", "UNSUPPORTED", "ERROR"]
    area: AreaBreakdown | None = None
    length: LengthBreakdown | None = None
    projected_crs: str | None = None
    method: str | None = None
    note: str | None = None


class SummaryUnitBreakdown(BaseModel):
    """Whole-file summary with multi-unit totals."""

    total_area: AreaBreakdown
    total_length: LengthBreakdown
    counts_by_geometry_type: dict[str, int]
    counts_by_measurement_status: dict[str, int]


class MultiUnitMeasurementsPage(BaseModel):
    """Paginated multi-unit measurements response."""

    file_id: str
    status: str
    crs: str | None = None
    feature_count: int
    summary: SummaryUnitBreakdown
    pagination: dict[str, int]
    features: list[FeatureUnitMeasurement]
    filtered_total: int


class IssueLocationResponse(BaseModel):
    """Approximate coordinate location of a topology defect."""

    coordinate_index: int | None = None
    longitude: float | None = None
    latitude: float | None = None
    description: str = ""


class TopologyIssueResponse(BaseModel):
    """A single topology defect found in one feature."""

    issue_type: str
    severity: Literal["error", "warning", "info"]
    feature_index: int
    geometry_type: str
    description: str
    locations: list[IssueLocationResponse] = Field(default_factory=list)


class TopologyAuditResponse(BaseModel):
    """Full quality-audit response for one uploaded file."""

    file_id: str
    feature_count: int
    audited_count: int
    quality_score: float = Field(
        description="Overall data quality score from 0 (worst) to 100 (perfect)."
    )
    error_count: int
    warning_count: int
    issues: list[TopologyIssueResponse] = Field(default_factory=list)


class SimplifiedFeatureResponse(BaseModel):
    """One Douglas-Peucker simplified feature."""

    feature_index: int
    geometry_type: str
    original_vertex_count: int
    simplified_vertex_count: int
    reduction_pct: float
    geometry: dict[str, Any] | None = None


class SimplificationResponse(BaseModel):
    """Simplification result with per-feature geometries and statistics."""

    file_id: str
    tolerance: float
    feature_count: int
    total_original_vertices: int
    total_simplified_vertices: int
    overall_reduction_pct: float
    features: list[SimplifiedFeatureResponse]
