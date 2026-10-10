"""Tests for the local-first SQLite repository."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.sqlite import init_sqlite_db
from app.models import FeatureRecord
from app.repositories.sqlite_repository import SqliteRepository


@pytest.mark.asyncio
async def test_sqlite_repository_full_lifecycle(tmp_path: Path) -> None:
    """Verify SQLite CRUD, features insertion, summarization, and deletion."""
    db_file = str(tmp_path / "lifecycle.db")
    db = await init_sqlite_db(db_file)
    repo = SqliteRepository(db)

    # Health check
    assert await repo.health_check() is True
    assert repo.backend_name == "sqlite"

    file_id = "0123456789abcdef0123456789abcdef"
    now = datetime.now(UTC)
    doc = {
        "id": file_id,
        "filename": "test.kml",
        "file_type": "kml",
        "size_bytes": 1024,
        "crs": "EPSG:4326",
        "feature_count": 2,
        "status": "PROCESSING",
        "warnings": ["test warning"],
        "error_message": None,
        "geometry_type_counts": {"Polygon": 1, "LineString": 1},
        "created_at": now.isoformat(),
        "completed_at": None,
    }

    # Create file
    await repo.create_file(doc)
    fetched = await repo.get_file(file_id)
    assert fetched is not None
    assert fetched["id"] == file_id
    assert fetched["filename"] == "test.kml"
    assert fetched["warnings"] == ["test warning"]
    assert fetched["geometry_type_counts"] == {"Polygon": 1, "LineString": 1}

    # Insert features
    features = [
        FeatureRecord(
            feature_index=0,
            layer="parcels",
            geometry_type="Polygon",
            geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            crs="EPSG:4326",
            properties={"name": "Parcel 1", "area_code": 101},
            measurement_status="CALCULATED",
            area_sq_m=12345.67,
            length_m=None,
            projected_crs="EPSG:32631",
            measurement_method="utm_projected",
            note=None,
        ),
        FeatureRecord(
            feature_index=1,
            layer="roads",
            geometry_type="LineString",
            geometry={"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            crs="EPSG:4326",
            properties={"name": "Road A"},
            measurement_status="CALCULATED",
            area_sq_m=None,
            length_m=5432.1,
            projected_crs="EPSG:32631",
            measurement_method="utm_projected",
            note=None,
        ),
    ]
    await repo.insert_features(file_id, features)

    # Get features
    feats, total = await repo.get_features(file_id, limit=10, offset=0)
    assert total == 2
    assert len(feats) == 2
    assert feats[0]["geometry_type"] == "Polygon"
    assert feats[0]["properties"]["name"] == "Parcel 1"
    assert feats[0]["area_sq_m"] == 12345.67
    assert feats[1]["length_m"] == 5432.1

    # Filter by geometry type
    polygon_feats, poly_total = await repo.get_features(
        file_id, limit=10, offset=0, geometry_type="Polygon"
    )
    assert poly_total == 1
    assert len(polygon_feats) == 1
    assert polygon_feats[0]["geometry_type"] == "Polygon"

    # Summarize features
    summary = await repo.summarize_features(file_id)
    assert summary["total_area_sq_m"] == 12345.67
    assert summary["total_length_m"] == 5432.1
    assert summary["counts_by_geometry_type"] == {"Polygon": 1, "LineString": 1}
    assert summary["counts_by_measurement_status"] == {"CALCULATED": 2}

    # Update file status
    completed_time = datetime.now(UTC).isoformat()
    await repo.update_file(file_id, {"status": "COMPLETED", "completed_at": completed_time})
    updated = await repo.get_file(file_id)
    assert updated["status"] == "COMPLETED"
    assert updated["completed_at"] == completed_time

    # List files
    file_list, list_count = await repo.list_files(limit=10, offset=0)
    assert list_count == 1
    assert len(file_list) == 1
    assert file_list[0]["id"] == file_id

    # Delete file
    deleted = await repo.delete_file(file_id)
    assert deleted is True
    assert await repo.get_file(file_id) is None
    deleted_feats, deleted_total = await repo.get_features(file_id, limit=10, offset=0)
    assert deleted_total == 0

    db.close()
