"""Accuracy, projection, and unsupported-geometry tests."""

from pyproj import Geod, Transformer
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)
from shapely.ops import transform

from app.services.measurement import measure_geometry

GEOD = Geod(ellps="WGS84")


def test_equatorial_polygon_uses_metres_and_is_not_degree_area() -> None:
    """A one-degree box is about 12,300 square kilometres, not one square degree."""
    geometry = box(0, 0, 1, 1)
    result = measure_geometry(geometry, "EPSG:4326")
    expected, _ = GEOD.geometry_area_perimeter(geometry)
    assert result.status == "CALCULATED"
    assert result.area_sq_m is not None
    assert abs(result.area_sq_m - abs(expected)) / abs(expected) < 0.005
    assert result.area_sq_m != geometry.area
    assert 12_000_000_000 < result.area_sq_m < 13_000_000_000
    assert result.projected_crs is not None


def test_one_degree_equatorial_line_matches_geodesic_length() -> None:
    """Longitude degrees are converted to physical distance in metres."""
    geometry = LineString([(0, 0), (1, 0)])
    result = measure_geometry(geometry, "EPSG:4326")
    expected = GEOD.geometry_length(geometry)
    assert result.status == "CALCULATED"
    assert result.length_m is not None
    assert abs(result.length_m - expected) / expected < 0.001
    assert result.length_m != geometry.length


def test_southern_hemisphere_selects_southern_utm() -> None:
    """A feature south of the equator uses a southern UTM EPSG code."""
    result = measure_geometry(box(18, -35, 18.1, -34.9), "EPSG:4326")
    assert result.projected_crs is not None
    assert result.projected_crs.startswith("EPSG:327")


def test_polygon_hole_is_subtracted_from_area() -> None:
    """Interior rings reduce polygon area."""
    geometry = Polygon(
        [(10, 10), (11, 10), (11, 11), (10, 11), (10, 10)],
        [[(10.2, 10.2), (10.8, 10.2), (10.8, 10.8), (10.2, 10.8), (10.2, 10.2)]],
    )
    exterior_only = Polygon([(10, 10), (11, 10), (11, 11), (10, 11), (10, 10)])
    measured = measure_geometry(geometry, "EPSG:4326")
    full = measure_geometry(exterior_only, "EPSG:4326")
    assert measured.area_sq_m is not None
    assert full.area_sq_m is not None
    assert measured.area_sq_m < full.area_sq_m


def test_multipolygon_area_is_calculated() -> None:
    """Separate polygon parts are included in the total area."""
    geometry = MultiPolygon(
        [
            box(0, 0, 0.1, 0.1),
            box(0.2, 0, 0.3, 0.1),
        ]
    )
    result = measure_geometry(geometry, "EPSG:4326")
    assert result.status == "CALCULATED"
    assert result.area_sq_m is not None and result.area_sq_m > 0


def test_multiline_length_is_calculated() -> None:
    """All parts of a MultiLineString contribute to its length."""
    geometry = MultiLineString([[(0, 0), (0.5, 0)], [(0, 1), (0.5, 1)]])
    result = measure_geometry(geometry, "EPSG:4326")
    expected = GEOD.geometry_length(geometry)
    assert result.status == "CALCULATED"
    assert result.length_m is not None
    assert abs(result.length_m - expected) / expected < 0.001


def test_antimeridian_polygon_uses_equal_area_projection_and_stays_local() -> None:
    """A dateline-crossing polygon is unwrapped before equal-area projection."""
    geometry = Polygon([(179, 10), (-179, 10), (-179, 11), (179, 11), (179, 10)])
    result = measure_geometry(geometry, "EPSG:4326")
    assert result.method == "equal_area_projected"
    assert result.projected_crs == "EPSG:6933"
    assert result.area_sq_m is not None
    assert 20_000_000_000 < result.area_sq_m < 30_000_000_000


def test_projected_input_is_normalized_before_measurement() -> None:
    """Projected source geometry is transformed to WGS84 before choosing a CRS."""
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True)
    projected = transform(to_utm.transform, box(2, 0, 2.01, 0.01))
    result = measure_geometry(projected, "EPSG:32631")
    assert result.status == "CALCULATED"
    assert result.projected_crs is not None
    assert result.projected_crs.startswith("EPSG:326")
    assert result.area_sq_m is not None and 1_000_000 < result.area_sq_m < 1_300_000


def test_point_needs_no_measurement() -> None:
    """Points are a normal NOT_APPLICABLE case."""
    result = measure_geometry(Point(4, 51), "EPSG:4326")
    assert result.status == "NOT_APPLICABLE"
    assert result.area_sq_m is None
    assert result.length_m is None


def test_geometry_collection_is_unsupported_without_raising() -> None:
    """Mixed KML MultiGeometry remains visible but is not measured."""
    geometry = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
    result = measure_geometry(geometry, "EPSG:4326")
    assert result.status == "UNSUPPORTED"
    assert "GeometryCollection" in (result.note or "")


def test_invalid_bow_tie_polygon_is_repaired() -> None:
    """A self-intersecting polygon is repaired and measured."""
    geometry = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    result = measure_geometry(geometry, "EPSG:4326")
    assert result.status == "CALCULATED"
    assert result.area_sq_m is not None and result.area_sq_m > 0
    assert result.note == "geometry repaired"
