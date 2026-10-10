"""Internal data structures shared by geospatial readers, services, and repositories."""

from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(slots=True)
class FeatureRecord:
    """A source feature and its measurement result before persistence."""

    feature_index: int
    layer: str | None
    geometry_type: str
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any]
    measurement_status: str
    area_sq_m: float | None = None
    length_m: float | None = None
    projected_crs: str | None = None
    measurement_method: str | None = None
    note: str | None = None
    source_geometry: BaseGeometry | None = None
