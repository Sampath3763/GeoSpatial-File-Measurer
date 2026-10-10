"""Create small local KML and zipped Shapefile files for manual testing."""

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon

SAMPLES_DIR = Path(__file__).resolve().parent
KML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Survey marker</name>
      <Point><coordinates>-122.4194,37.7749,15</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Sample parcel</name>
      <ExtendedData>
        <Data name="parcel.id"><value>SF-001</value></Data>
        <Data name="survey.team"><value>North crew</value></Data>
      </ExtendedData>
      <Polygon>
        <outerBoundaryIs><LinearRing><coordinates>
          -122.4200,37.7745 -122.4190,37.7745
          -122.4190,37.7753 -122.4200,37.7753 -122.4200,37.7745
        </coordinates></LinearRing></outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Access path</name>
      <LineString>
        <coordinates>-122.4210,37.7749 -122.4194,37.7749</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


def _write_shape(directory: Path, name: str, geometry: Polygon | LineString) -> None:
    """Write one WGS84 layer as an ESRI Shapefile."""
    frame = gpd.GeoDataFrame(
        {
            "parcel_id": [name],
            "team_name": ["North crew"],
        },
        geometry=[geometry],
        crs="EPSG:4326",
    )
    frame.to_file(directory / f"{name}.shp", engine="pyogrio")


def main() -> None:
    """Generate sample.kml and a ZIP containing polygon and line layers."""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / "sample.kml").write_text(KML_SAMPLE, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="geo-measurement-samples-") as temp_dir:
        directory = Path(temp_dir)
        boundary = Polygon(
            [
                (-122.4200, 37.7745),
                (-122.4190, 37.7745),
                (-122.4190, 37.7753),
                (-122.4200, 37.7753),
                (-122.4200, 37.7745),
            ]
        )
        path = LineString([(-122.4210, 37.7749), (-122.4194, 37.7749)])
        _write_shape(directory, "sample_boundary", boundary)
        _write_shape(directory, "sample_path", path)
        zip_path = SAMPLES_DIR / "sample_shapefile.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(directory.glob("*")):
                archive.write(file_path, file_path.name)
    print(f"Created {SAMPLES_DIR / 'sample.kml'}")
    print(f"Created {SAMPLES_DIR / 'sample_shapefile.zip'}")


if __name__ == "__main__":
    main()
