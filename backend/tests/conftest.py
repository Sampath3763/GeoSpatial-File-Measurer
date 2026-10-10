"""Programmatic geospatial fixtures and isolated API test dependencies."""

import io
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from app.api.dependencies import get_repository
from app.core.config import Settings
from app.db.sqlite import init_sqlite_db
from app.main import create_app
from app.repositories.memory_repository import MemoryRepository
from app.repositories.sqlite_repository import SqliteRepository

SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Placemark>
    <name>Survey point</name>
    <Point><coordinates>0,0,12</coordinates></Point>
  </Placemark>
  <Placemark>
    <name>Survey boundary</name>
    <ExtendedData>
      <Data name="parcel.id"><value>A-1</value></Data>
    </ExtendedData>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      0,0 1,0 1,1 0,1 0,0
    </coordinates></LinearRing></outerBoundaryIs></Polygon>
  </Placemark>
  <Placemark>
    <name>Baseline</name>
    <LineString><coordinates>0,0 1,0</coordinates></LineString>
  </Placemark>
</Document></kml>"""


@pytest.fixture
def app_context():
    """Create an API app backed by MemoryRepository."""
    settings = Settings(
        db_backend="memory",
        max_upload_mb=1,
        max_unzipped_mb=4,
        max_zip_entries=100,
        max_features_per_file=50_000,
    )
    application = create_app(settings)
    repository = MemoryRepository()
    application.dependency_overrides[get_repository] = lambda: repository
    application.state.repository = repository
    with TestClient(application) as client:
        yield client, repository, application


@pytest.fixture
async def sqlite_repo(tmp_path: Path):
    """Fixture providing an initialized SQLite repository."""
    db_path = str(tmp_path / "test_geo.db")
    db = await init_sqlite_db(db_path)
    repo = SqliteRepository(db)
    try:
        yield repo
    finally:
        db.close()


@pytest.fixture
def sample_kml() -> bytes:
    """Return a small KML file with a 3D point, polygon, and line."""
    return SAMPLE_KML.encode("utf-8")


@pytest.fixture
def sample_shapefile_zip(tmp_path: Path) -> bytes:
    """Create and zip a tiny WGS84 Shapefile."""
    return make_shapefile_zip(
        tmp_path,
        "survey",
        Polygon([(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01), (0, 0)]),
        crs="EPSG:4326",
    )


def make_shapefile_zip(
    tmp_path: Path,
    name: str,
    geometry: Any,
    crs: str | None,
) -> bytes:
    """Write and zip one Shapefile."""
    target_dir = tmp_path / f"shape_{name}"
    target_dir.mkdir(parents=True, exist_ok=True)
    shape_path = target_dir / f"{name}.shp"
    frame = gpd.GeoDataFrame(
        {
            "parcel.id": ["A-1"],
            "$owner": ["field team"],
            "geometry": [geometry],
        },
        crs=crs,
    )
    frame.to_file(shape_path, engine="pyogrio")
    archive_path = target_dir / f"{name}.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in target_dir.glob(f"{name}.*"):
            if path != archive_path:
                archive.write(path, path.name)
    return archive_path.read_bytes()


def upload_files(filename: str, content: bytes) -> dict[str, tuple[str, io.BytesIO, str]]:
    """Build a multipart request body with an inferred MIME type."""
    content_type = (
        "application/vnd.google-earth.kml+xml"
        if filename.lower().endswith(".kml")
        else "application/zip"
    )
    return {"file": (filename, io.BytesIO(content), content_type)}


def ready_file(file_id: str, **overrides: Any) -> dict[str, Any]:
    """Create a valid file document for testing."""
    document: dict[str, Any] = {
        "id": file_id,
        "filename": "ready.kml",
        "file_type": "kml",
        "size_bytes": 100,
        "crs": "EPSG:4326",
        "feature_count": 0,
        "status": "COMPLETED",
        "error_message": None,
        "warnings": [],
        "geometry_type_counts": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:01+00:00",
    }
    document.update(overrides)
    return document
