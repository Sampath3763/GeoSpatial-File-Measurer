"""KML parser behavior, including the lxml fallback."""

from pathlib import Path

from conftest import SAMPLE_KML

from app.services.geo_reader import _parse_kml_fallback, read_and_measure


def test_fallback_parser_reads_kml_geometries_and_extended_data(tmp_path: Path) -> None:
    """The fallback parses point, polygon, line, 3D coordinates, and properties."""
    path = tmp_path / "sample.kml"
    path.write_text(SAMPLE_KML, encoding="utf-8")
    records = _parse_kml_fallback(path, 100)
    assert [record[2].geom_type for record in records] == ["Point", "Polygon", "LineString"]
    assert records[0][2].has_z is True
    assert records[1][4]["parcel_id"] == "A-1"


def test_fallback_and_pyogrio_readers_agree_on_sample(tmp_path: Path) -> None:
    """When GDAL has its KML driver, both readers expose the same feature types."""
    path = tmp_path / "sample.kml"
    path.write_text(SAMPLE_KML, encoding="utf-8")
    fallback = _parse_kml_fallback(path, 100)
    primary, _crs, _warnings = read_and_measure(path, "kml", 100)
    assert [record.geometry_type for record in primary] == [
        record[2].geom_type for record in fallback
    ]
    assert primary[0].geometry is not None
    assert len(primary[0].geometry["coordinates"]) == 2
    assert any("Z/M" in warning for warning in _warnings)
