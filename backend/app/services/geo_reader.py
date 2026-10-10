"""Read KML and zipped Shapefiles into a normalized feature record format."""

import json
import logging
import math
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pyogrio
from lxml import etree
from pyproj import CRS
from shapely import force_2d
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    mapping,
)
from shapely.geometry.base import BaseGeometry

from app.core.errors import ReaderValidationError, TooManyFeatures
from app.models import FeatureRecord
from app.services.measurement import measure_geometry

logger = logging.getLogger(__name__)
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
RawFeature = tuple[int, str | None, BaseGeometry | None, str | None, dict[str, Any]]


def read_and_measure(
    input_path: Path,
    file_type: str,
    maximum_features: int,
) -> tuple[list[FeatureRecord], str | None, list[str]]:
    """Read every layer, measure every feature, and return safe records."""
    if file_type == "shapefile":
        geometries, warnings = _read_shapefiles(input_path, maximum_features)
    else:
        geometries, warnings = _read_kml(input_path, maximum_features)

    records: list[FeatureRecord] = []
    crs_values: set[str] = set()
    for feature_index, layer, geometry, source_crs, properties in geometries:
        if source_crs:
            crs_values.add(source_crs)
        safe_geometry: dict[str, Any] | None = None
        feature_note: str | None = None
        clean_geometry = force_2d(geometry) if geometry is not None else None
        if geometry is not None and (geometry.has_z or geometry.has_m):
            warnings.append("Z/M coordinates were dropped; measurements use 2D geometry.")
        if clean_geometry is not None:
            try:
                safe_geometry = json.loads(json.dumps(mapping(clean_geometry), allow_nan=False))
            except (TypeError, ValueError):
                feature_note = "Geometry could not be serialized as valid GeoJSON."
                clean_geometry = None
        result = measure_geometry(clean_geometry, source_crs)
        note = "; ".join(part for part in [result.note, feature_note] if part) or None
        records.append(
            FeatureRecord(
                feature_index=feature_index,
                layer=layer,
                geometry_type=result.geometry_type,
                geometry=safe_geometry,
                crs=source_crs,
                properties=properties,
                measurement_status=result.status,
                area_sq_m=result.area_sq_m,
                length_m=result.length_m,
                projected_crs=result.projected_crs,
                measurement_method=result.method,
                note=note,
                source_geometry=clean_geometry,
            )
        )
    source_crs = (
        next(iter(crs_values)) if len(crs_values) == 1 else ("Mixed" if crs_values else None)
    )
    return records, source_crs, list(dict.fromkeys(warnings))


def _read_shapefiles(
    archive_path: Path, maximum_features: int
) -> tuple[list[RawFeature], list[str]]:
    """Safely extract a validated archive and read each Shapefile layer."""
    warnings: list[str] = []
    records: list[tuple[int, str | None, BaseGeometry | None, str | None, dict[str, Any]]] = []
    extract_dir = archive_path.parent / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extract_dir)
    root = extract_dir
    shape_paths = sorted(path for path in root.rglob("*") if path.suffix.lower() == ".shp")
    for shape_path in shape_paths:
        frame = gpd.read_file(shape_path, engine="pyogrio")
        layer_crs = _frame_crs(frame)
        if layer_crs is None:
            if not _coordinates_are_lon_lat(frame):
                raise ReaderValidationError(
                    f"{shape_path.name} has no .prj CRS file and its coordinates are not valid "
                    "longitude/latitude values."
                )
            frame = frame.set_crs("EPSG:4326")
            layer_crs = "EPSG:4326"
            warnings.append(f"{shape_path.name} has no .prj file; assumed EPSG:4326.")
        records.extend(
            _frame_records(
                frame,
                len(records),
                shape_path.stem,
                layer_crs,
                maximum_features,
                warnings,
            )
        )
    return records, warnings


def _read_kml(kml_path: Path, maximum_features: int) -> tuple[list[RawFeature], list[str]]:
    """Prefer the GDAL KML driver, falling back to the built-in XML parser."""
    driver_names = pyogrio.list_drivers()
    if not any(name in driver_names for name in ("KML", "LIBKML")):
        logger.info("GDAL KML driver is unavailable; using the XML fallback reader")
        warnings = ["GDAL KML driver unavailable; used the built-in KML reader."]
        return _parse_kml_fallback(kml_path, maximum_features, warnings), warnings
    try:
        layers = pyogrio.list_layers(kml_path)
        if not len(layers):
            return [], []
        layer_names = [str(layer[0]) for layer in layers] or [None]
        records: list[tuple[int, str | None, BaseGeometry | None, str | None, dict[str, Any]]] = []
        warnings: list[str] = []
        for layer_name in layer_names:
            frame = gpd.read_file(kml_path, layer=layer_name, engine="pyogrio")
            records.extend(
                _frame_records(
                    frame,
                    len(records),
                    layer_name,
                    "EPSG:4326",
                    maximum_features,
                    warnings,
                )
            )
        return records, warnings
    except (ValueError, RuntimeError, OSError, IndexError, pyogrio.errors.DataSourceError):
        logger.warning("GDAL could not read the KML; using the XML fallback reader", exc_info=True)
        warnings = ["GDAL could not read the KML; used the built-in KML reader."]
        return _parse_kml_fallback(kml_path, maximum_features, warnings), warnings


def _frame_records(
    frame: gpd.GeoDataFrame,
    starting_index: int,
    layer: str | None,
    crs: str | None,
    maximum_features: int,
    warnings: list[str],
) -> list[tuple[int, str | None, BaseGeometry | None, str | None, dict[str, Any]]]:
    """Convert a GeoDataFrame layer to safe, indexed feature inputs."""
    records = []
    geometry_column = frame.geometry.name
    for row_number, (_, row) in enumerate(frame.iterrows()):
        feature_index = starting_index + row_number
        if feature_index >= maximum_features:
            raise TooManyFeatures(maximum_features)
        geometry = row[geometry_column]
        properties, property_warnings = sanitize_properties(
            {key: value for key, value in row.items() if key != geometry_column}
        )
        warnings.extend(property_warnings)
        records.append((feature_index, layer, geometry, crs, properties))
    return records


def _frame_crs(frame: gpd.GeoDataFrame) -> str | None:
    """Return a normalized CRS string or None for an unreferenced layer."""
    if frame.crs is None:
        return None
    return CRS.from_user_input(frame.crs).to_string()


def _coordinates_are_lon_lat(frame: gpd.GeoDataFrame) -> bool:
    """Check that every available coordinate is inside geographic bounds."""
    bounds = frame.geometry.bounds
    if bounds.empty:
        return False
    valid = (
        bounds["minx"].between(-180, 180)
        & bounds["maxx"].between(-180, 180)
        & bounds["miny"].between(-90, 90)
        & bounds["maxy"].between(-90, 90)
    )
    return bool(valid.all() and frame.geometry.notna().any())


def sanitize_properties(properties: dict[Any, Any]) -> tuple[dict[str, Any], list[str]]:
    """Sanitize property names and recursively convert values to safe types."""
    safe_properties: dict[str, Any] = {}
    warnings: list[str] = []
    for raw_key, raw_value in properties.items():
        key = _safe_property_key(raw_key, safe_properties)
        safe_properties[key] = _safe_value(raw_value, warnings)
    return safe_properties, warnings


def _safe_property_key(raw_key: Any, existing: dict[str, Any]) -> str:
    """Normalize unsafe key characters and disambiguate collisions."""
    key = str(raw_key).replace(".", "_").lstrip("$").strip() or "field"
    base = key
    suffix = 2
    while key in existing:
        key = f"{base}_{suffix}"
        suffix += 1
    return key


def _safe_value(value: Any, warnings: list[str]) -> Any:
    """Convert common geospatial property values to standard Python values."""
    if isinstance(value, np.generic):
        value = value.item()
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, int) and not INT64_MIN <= value <= INT64_MAX:
        return str(value)
    if isinstance(value, bytes):
        warnings.append("A bytes property was replaced with null.")
        return None
    if isinstance(value, dict):
        safe_values: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = _safe_property_key(raw_key, safe_values)
            safe_values[key] = _safe_value(item, warnings)
        return safe_values
    if isinstance(value, list | tuple):
        return [_safe_value(item, warnings) for item in value]
    if isinstance(value, str | int | float | bool):
        return value
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    warnings.append(f"Unsupported property value {type(value).__name__} was converted to text.")
    return str(value)


def _parse_kml_fallback(
    kml_path: Path, maximum_features: int, warnings: list[str] | None = None
) -> list[RawFeature]:
    """Parse KML placemarks, geometry collections, and ExtendedData with lxml."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.parse(str(kml_path), parser).getroot()
    records = []
    for placemark in root.xpath(".//*[local-name()='Placemark']"):
        raw_properties: dict[str, Any] = {}
        for child in placemark:
            tag = etree.QName(child).localname
            if tag in {"name", "description"} and child.text:
                raw_properties[tag] = child.text.strip()
            elif tag == "ExtendedData":
                for data in child.xpath(".//*[local-name()='Data']"):
                    key = data.get("name")
                    value = data.xpath("string(./*[local-name()='value'])")
                    if key:
                        raw_properties[key] = value or None
                for data in child.xpath(".//*[local-name()='SimpleData']"):
                    key = data.get("name")
                    if key:
                        raw_properties[key] = (data.text or "").strip() or None
        geometry_nodes = [
            child
            for child in placemark
            if etree.QName(child).localname in {"Point", "LineString", "Polygon", "MultiGeometry"}
        ]
        geometries = []
        for node in geometry_nodes:
            geometry = _parse_kml_geometry(node)
            if geometry is not None:
                geometries.append(geometry)
        if not geometries:
            geometry: BaseGeometry | None = None
        elif len(geometries) == 1:
            geometry = geometries[0]
        else:
            geometry = _combine_geometries(geometries)
        safe_properties, property_warnings = sanitize_properties(raw_properties)
        if warnings is not None:
            warnings.extend(property_warnings)
        records.append(
            (
                len(records),
                None,
                geometry,
                "EPSG:4326",
                safe_properties,
            )
        )
        if len(records) > maximum_features:
            raise TooManyFeatures(maximum_features)
    return records


def _parse_kml_geometry(node: Any) -> BaseGeometry | None:
    """Recursively parse one KML geometry element."""
    tag = etree.QName(node).localname
    if tag == "MultiGeometry":
        parts = [geometry for child in node if (geometry := _parse_kml_geometry(child)) is not None]
        return _combine_geometries(parts) if parts else GeometryCollection()
    if tag == "Point":
        coordinates = _coordinates_from_text(node.xpath("string(.//*[local-name()='coordinates'])"))
        return Point(coordinates[0]) if coordinates else None
    if tag == "LineString":
        coordinates = _coordinates_from_text(node.xpath("string(.//*[local-name()='coordinates'])"))
        return LineString(coordinates) if len(coordinates) >= 2 else None
    if tag == "Polygon":
        outer = node.xpath(
            "string(.//*[local-name()='outerBoundaryIs']//*[local-name()='coordinates'])"
        )
        exterior = _coordinates_from_text(outer)
        if len(exterior) < 4:
            return None
        inner_coordinates = node.xpath(
            ".//*[local-name()='innerBoundaryIs']//*[local-name()='coordinates']"
        )
        holes = [_coordinates_from_text(node.xpath("string(.)")) for node in inner_coordinates]
        return Polygon(exterior, [ring for ring in holes if len(ring) >= 4])
    return None


def _coordinates_from_text(text: str) -> list[tuple[float, ...]]:
    """Parse whitespace-separated KML coordinate tuples."""
    coordinates: list[tuple[float, ...]] = []
    for raw_coordinate in text.split():
        try:
            parts = tuple(float(value) for value in raw_coordinate.split(",") if value != "")
        except ValueError:
            continue
        if len(parts) >= 2:
            coordinates.append(parts)
    return coordinates


def _combine_geometries(geometries: list[BaseGeometry]) -> BaseGeometry:
    """Create a homogeneous Multi* or a mixed GeometryCollection."""
    if all(geometry.geom_type == "Point" for geometry in geometries):
        return MultiPoint(geometries)
    if all(geometry.geom_type == "LineString" for geometry in geometries):
        return MultiLineString(geometries)
    if all(geometry.geom_type == "Polygon" for geometry in geometries):
        return MultiPolygon(geometries)
    return GeometryCollection(geometries)
