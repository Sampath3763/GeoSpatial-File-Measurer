"""Response schemas for file metadata, measurements, and feature pages."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FileInfo(BaseModel):
    """Public file metadata."""

    id: str
    filename: str
    file_type: Literal["shapefile", "kml"]
    feature_count: int
    crs: str | None = None
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED"]
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    geometry_type_counts: dict[str, int] = Field(default_factory=dict)
    created_at: datetime | str
    completed_at: datetime | str | None = None

    model_config = ConfigDict(extra="ignore")


class FileList(BaseModel):
    """Paginated upload history."""

    total: int
    limit: int
    offset: int
    files: list[FileInfo]


class MeasurementFeature(BaseModel):
    """Measurement result for one source feature."""

    feature_index: int
    layer: str | None = None
    geometry_type: str
    measurement_status: Literal["CALCULATED", "NOT_APPLICABLE", "UNSUPPORTED", "ERROR"]
    measurements: dict[str, float | None] | None = None
    projected_crs: str | None = None
    method: str | None = None
    note: str | None = None


class MeasurementsSummary(BaseModel):
    """Whole-file measurement totals and counts."""

    total_area_sq_m: float
    total_length_m: float
    counts_by_geometry_type: dict[str, int]
    counts_by_measurement_status: dict[str, int]


class MeasurementsPage(BaseModel):
    """Paginated measurements with an aggregate across the entire upload."""

    file_id: str
    status: str
    crs: str | None = None
    feature_count: int
    summary: MeasurementsSummary
    pagination: dict[str, int]
    features: list[MeasurementFeature]
    filtered_total: int


class Feature(BaseModel):
    """Public source geometry and properties."""

    feature_index: int
    geometry_type: str
    geometry: dict[str, Any] | None = None
    crs: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class FeaturePage(BaseModel):
    """Paginated feature records."""

    file_id: str
    limit: int
    offset: int
    total: int
    features: list[Feature]
