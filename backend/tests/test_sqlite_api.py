"""End-to-end integration test with the real SQLite repository."""

from pathlib import Path

from conftest import SAMPLE_KML, upload_files
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_full_api_workflow_with_sqlite(tmp_path: Path) -> None:
    """Verify that file upload, extraction, measurements, and listing work with SQLite."""
    db_path = str(tmp_path / "e2e_test.db")
    settings = Settings(
        db_backend="sqlite",
        sqlite_db_path=db_path,
        max_upload_mb=10,
    )
    application = create_app(settings)

    with TestClient(application) as client:
        # Health check
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["backend"] == "sqlite"

        # Upload KML file
        upload_resp = client.post(
            "/api/files/",
            files=upload_files("survey.kml", SAMPLE_KML.encode("utf-8")),
        )
        assert upload_resp.status_code == 201
        file_info = upload_resp.json()
        file_id = file_info["id"]
        assert file_info["status"] == "COMPLETED"
        assert file_info["feature_count"] == 3
        assert file_info["crs"] == "EPSG:4326"

        # GET /api/files/{id}/
        file_resp = client.get(f"/api/files/{file_id}/")
        assert file_resp.status_code == 200
        assert file_resp.json()["id"] == file_id
        assert file_resp.json()["filename"] == "survey.kml"

        # GET /api/files/{id}/measurements/
        measurements_resp = client.get(f"/api/files/{file_id}/measurements/")
        assert measurements_resp.status_code == 200
        measurements = measurements_resp.json()
        assert measurements["file_id"] == file_id
        assert measurements["feature_count"] == 3
        assert measurements["summary"]["total_area_sq_m"] > 0
        assert len(measurements["features"]) == 3

        # GET /api/files/{id}/features/
        features_resp = client.get(f"/api/files/{file_id}/features/")
        assert features_resp.status_code == 200
        assert features_resp.json()["total"] == 3
        assert len(features_resp.json()["features"]) == 3

        # GET /api/files/
        list_resp = client.get("/api/files/")
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1
        assert list_resp.json()["files"][0]["id"] == file_id

        # DELETE /api/files/{id}/
        del_resp = client.delete(f"/api/files/{file_id}/")
        assert del_resp.status_code == 204

        # Verify 404 after delete
        not_found = client.get(f"/api/files/{file_id}/")
        assert not_found.status_code == 404
