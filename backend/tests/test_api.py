"""API behavior tests using the in-memory repository."""

from datetime import UTC, datetime
from typing import Any

from conftest import ready_file, upload_files


def test_kml_upload_metadata_measurements_features_and_delete(
    app_context: Any, sample_kml: bytes
) -> None:
    """The main upload workflow persists a file and exposes all result endpoints."""
    client, repository, _application = app_context
    uploaded = client.post("/api/files/", files=upload_files("field.kml", sample_kml))
    assert uploaded.status_code == 201
    file_info = uploaded.json()
    file_id = file_info["id"]
    assert file_info["status"] == "COMPLETED"
    assert file_info["feature_count"] == 3
    assert file_info["crs"] == "EPSG:4326"
    assert any("Z/M" in warning for warning in file_info["warnings"])

    detail = client.get(f"/api/files/{file_id}/")
    assert detail.status_code == 200
    assert detail.json()["filename"] == "field.kml"

    measurements = client.get(f"/api/files/{file_id}/measurements/?limit=1&offset=0")
    assert measurements.status_code == 200
    payload = measurements.json()
    assert payload["pagination"] == {"limit": 1, "offset": 0, "returned": 1}
    assert payload["feature_count"] == 3
    assert sum(payload["summary"]["counts_by_geometry_type"].values()) == 3
    assert payload["summary"]["total_area_sq_m"] > 0
    assert payload["summary"]["total_length_m"] > 100_000
    assert payload["features"][0]["geometry_type"] == "Point"
    assert payload["features"][0]["measurement_status"] == "NOT_APPLICABLE"

    filtered = client.get(
        f"/api/files/{file_id}/measurements/?geometry_type=Polygon&limit=10"
    )
    assert filtered.status_code == 200
    assert len(filtered.json()["features"]) == 1
    assert filtered.json()["summary"] == payload["summary"]

    feature_page = client.get(f"/api/files/{file_id}/features/?limit=2&offset=1")
    assert feature_page.status_code == 200
    feature_payload = feature_page.json()
    assert feature_payload["total"] == 3
    assert len(feature_payload["features"]) == 2
    assert feature_payload["features"][0]["geometry"] is not None
    properties = feature_payload["features"][0]["properties"]
    assert any(
        key.casefold() == "name" and value == "Survey boundary"
        for key, value in properties.items()
    )

    history = client.get("/api/files/?limit=10&offset=0")
    assert history.status_code == 200
    assert history.json()["total"] == 1

    deleted = client.delete(f"/api/files/{file_id}/")
    assert deleted.status_code == 204
    assert file_id not in repository.files
    assert file_id not in repository.features
    assert client.get(f"/api/files/{file_id}/").status_code == 404


def test_shapefile_zip_upload_reads_projected_geometry_and_properties(
    app_context: Any, sample_shapefile_zip: bytes
) -> None:
    """A complete zipped Shapefile is stored with CRS and safe attributes."""
    client, _repository, _application = app_context
    uploaded = client.post(
        "/api/files/",
        files=upload_files("survey.zip", sample_shapefile_zip),
    )
    assert uploaded.status_code == 201
    file_info = uploaded.json()
    assert file_info["file_type"] == "shapefile"
    assert file_info["status"] == "COMPLETED"
    assert file_info["feature_count"] == 1
    assert file_info["crs"] == "EPSG:4326"
    file_id = file_info["id"]
    feature_page = client.get(f"/api/files/{file_id}/features/")
    assert feature_page.status_code == 200
    properties = feature_page.json()["features"][0]["properties"]
    assert "parcel_id" in properties
    assert "owner" in properties
    measurements = client.get(f"/api/files/{file_id}/measurements/")
    assert measurements.status_code == 200
    assert measurements.json()["summary"]["total_area_sq_m"] > 0


def test_file_not_found_and_malformed_ids_share_a_404_envelope(app_context: Any) -> None:
    """Unknown and malformed ids return 404 with standardized error structure."""
    client, _repository, _application = app_context
    for file_id in ("not-an-id", "a" * 32):
        response = client.get(f"/api/files/{file_id}/")
        assert response.status_code == 404
        assert set(response.json()) == {"error"}
        assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_measurements_reject_processing_files_with_409(app_context: Any) -> None:
    """A processing upload cannot expose incomplete measurements."""
    client, repository, _application = app_context
    file_id = "b" * 32
    repository.files[file_id] = ready_file(
        file_id,
        status="PROCESSING",
        created_at=datetime.now(UTC),
    )
    repository.features[file_id] = []
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FILE_NOT_READY"


def test_health_endpoint_reports_status(app_context: Any) -> None:
    """Health check reports healthy when repository is ready."""
    client, _repository, _application = app_context
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "backend" in data
