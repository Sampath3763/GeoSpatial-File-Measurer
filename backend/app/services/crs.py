"""CRS normalization and per-feature projected CRS selection."""

from functools import lru_cache
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


@lru_cache(maxsize=128)
def get_transformer(source: str, target: str) -> Transformer:
    """Return a cached transformer that always consumes x/y coordinates."""
    return Transformer.from_crs(source, target, always_xy=True, force_over=True)


def normalize_to_wgs84(geometry: BaseGeometry, source_crs: str) -> BaseGeometry:
    """Transform any supported source geometry to longitude/latitude."""
    source = CRS.from_user_input(source_crs)
    if source == CRS.from_epsg(4326):
        return geometry
    transformer = get_transformer(source.to_string(), "EPSG:4326")
    return transform(transformer.transform, geometry)


def _coordinates(geometry: BaseGeometry) -> list[tuple[float, float]]:
    """Get all 2D coordinate pairs from a geometry."""
    coordinates: list[tuple[float, float]] = []
    if isinstance(geometry, Polygon | MultiPolygon):
        polygons = [geometry] if isinstance(geometry, Polygon) else geometry.geoms
        for polygon in polygons:
            rings = [polygon.exterior, *polygon.interiors]
            for ring in rings:
                coordinates.extend((float(x), float(y)) for x, y, *_ in ring.coords)
    elif isinstance(geometry, LineString | MultiLineString):
        lines = [geometry] if isinstance(geometry, LineString) else geometry.geoms
        for line in lines:
            coordinates.extend((float(x), float(y)) for x, y, *_ in line.coords)
    return coordinates


def crosses_antimeridian(geometry: BaseGeometry) -> bool:
    """Detect longitude sequences whose ordinary bounds cross the dateline."""
    coordinates = _coordinates(geometry)
    if len(coordinates) < 2:
        return False
    longitudes = [coordinate[0] for coordinate in coordinates]
    return max(longitudes) - min(longitudes) > 180


def select_measurement_crs(geometry_wgs84: BaseGeometry) -> tuple[str, str]:
    """Choose the feature's measurement CRS and method."""
    point = geometry_wgs84.representative_point()
    longitude, latitude = float(point.x), float(point.y)
    if latitude > 84:
        return "EPSG:32661", "utm_projected"
    if latitude < -80:
        return "EPSG:32761", "utm_projected"

    coordinates = _coordinates(geometry_wgs84)
    zones = {
        min(60, max(1, int((lon + 180) // 6) + 1)) for lon, _ in coordinates if -180 <= lon <= 180
    }
    crosses_zone = len(zones) > 1
    crosses_dateline = crosses_antimeridian(geometry_wgs84)
    if crosses_dateline or crosses_zone:
        if geometry_wgs84.geom_type in {"LineString", "MultiLineString"}:
            return "geodesic", "geodesic"
        return "EPSG:6933", "equal_area_projected"

    zone = min(60, max(1, int((longitude + 180) // 6) + 1))
    epsg = (32600 if latitude >= 0 else 32700) + zone
    return f"EPSG:{epsg}", "utm_projected"


def project_geometry(geometry_wgs84: BaseGeometry, target_crs: str) -> BaseGeometry:
    """Project WGS84 geometry to a target projected CRS."""
    transformer = get_transformer("EPSG:4326", target_crs)
    if target_crs == "EPSG:6933" and crosses_antimeridian(geometry_wgs84):
        import numpy as np

        def unwrap_longitudes(x: Any, y: Any, z: Any = None) -> tuple[Any, ...]:
            adjusted_x = np.where(np.asarray(x) < 0, np.asarray(x) + 360, x)
            return (adjusted_x, y, z) if z is not None else (adjusted_x, y)

        geometry_wgs84 = transform(unwrap_longitudes, geometry_wgs84)
    return transform(transformer.transform, geometry_wgs84)


def geodesic_length(geometry: BaseGeometry) -> float:
    """Calculate geodesic length in metres, respecting multi-line parts."""
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    return float(geod.geometry_length(geometry))
