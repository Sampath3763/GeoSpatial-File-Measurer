"""HTTP-level upload validation and rollback behavior."""

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from conftest import make_shapefile_zip, upload_files
from fastapi import UploadFile
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.api.dependencies import get_repository
from app.core.config import Settings
from app.core.errors import FileProcessingError
from app.main import create_app
from app.repositories.memory_repository import MemoryRepository
from app.services.file_service import FileService
from app.services.upload_validation import sanitize_filename


def test_client_filename_is_reduced_to_a_display_basename() -> None:
    """Client paths and control characters never become filesystem paths."""
    assert sanitize_filename("../../surveys\\final.kml") == "final.kml"
    assert sanitize_filename(None) == "upload"


def test_rejects_unsupported_extension(app_context: Any) -> None:
    """Unsupported extensions return 415 and a consistent error envelope."""
    client, _repository, _application = app_context
    response = client.post("/api/files/", files=upload_files("notes.txt", b"hello"))
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_missing_and_empty_uploads_are_bad_requests(app_context: Any) -> None:
    """Missing multipart input and empty upload bodies return 400."""
    client, _repository, _application = app_context
    missing = client.post("/api/files/")
    empty = client.post("/api/files/", files=upload_files("empty.kml", b""))
    assert missing.status_code == 400
    assert empty.status_code == 400
    assert missing.json()["error"]["code"] == "FILE_REQUIRED"
    assert empty.json()["error"]["code"] == "EMPTY_FILE"


def test_rejects_corrupt_zip_and_missing_shapefile_sidecar(app_context: Any) -> None:
    """Malformed archives and missing required components are rejected."""
    client, _repository, _application = app_context
    corrupt = client.post("/api/files/", files=upload_files("bad.zip", b"not a zip"))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("roads.shp", b"shape")
        zipped.writestr("roads.shx", b"index")
    missing_dbf = client.post(
        "/api/files/",
        files=upload_files("missing.zip", archive.getvalue()),
    )
    assert corrupt.status_code == 422
    assert corrupt.json()["error"]["code"] == "CORRUPT_ZIP"
    assert missing_dbf.status_code == 422
    assert "dbf" in missing_dbf.json()["error"]["message"]


def test_rejects_zip_slip_paths(app_context: Any) -> None:
    """Archive entries cannot write outside the temporary extraction directory."""
    client, _repository, _application = app_context
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("../roads.shp", b"shape")
        zipped.writestr("../roads.shx", b"index")
        zipped.writestr("../roads.dbf", b"attributes")
    response = client.post(
        "/api/files/",
        files=upload_files("unsafe.zip", archive.getvalue()),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSAFE_ZIP_PATH"


def test_upload_limit_is_enforced_while_streaming(app_context: Any) -> None:
    """A body over the configured byte limit is rejected with 413."""
    client, _repository, _application = app_context
    content = b"x" * (1024 * 1024 + 1)
    response = client.post("/api/files/", files=upload_files("large.kml", content))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_zip_entry_and_expanded_size_limits_are_enforced(app_context: Any) -> None:
    """Archives with too many entries or excessive expanded size fail safely."""
    client, _repository, _application = app_context
    many_entries = io.BytesIO()
    with zipfile.ZipFile(many_entries, "w", zipfile.ZIP_DEFLATED) as archive:
        for index in range(101):
            archive.writestr(f"entry-{index}.txt", "x")
    too_many = client.post(
        "/api/files/",
        files=upload_files("entries.zip", many_entries.getvalue()),
    )
    expanded_archive = io.BytesIO()
    with zipfile.ZipFile(expanded_archive, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.txt", b"x" * (4 * 1024 * 1024 + 1))
    too_large = client.post(
        "/api/files/",
        files=upload_files("expanded.zip", expanded_archive.getvalue()),
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "ZIP_ENTRY_LIMIT"
    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "UNZIPPED_SIZE_LIMIT"


def test_repository_failure_cleans_up_inserted_features(sample_kml: bytes) -> None:
    """A mid-write failure removes inserted rows and marks the file failed."""

    class FailingRepository(MemoryRepository):
        """Fail after a batch has been inserted to simulate a partial write."""

        async def insert_features(self, file_id: str, features: list[Any]) -> None:
            await super().insert_features(file_id, features)
            raise RuntimeError("simulated insert failure")

    repository = FailingRepository()
    service = FileService(repository, Settings(db_backend="memory"))
    upload = UploadFile(file=io.BytesIO(sample_kml), filename="sample.kml")
    with pytest.raises(FileProcessingError):
        import asyncio

        asyncio.run(service.upload(upload))
    assert len(repository.files) == 1
    file_id, document = next(iter(repository.files.items()))
    assert document["status"] == "FAILED"
    assert file_id not in repository.features


def test_feature_limit_returns_413_and_marks_upload_failed(sample_kml: bytes) -> None:
    """The configured maximum feature count is enforced by the reader."""
    application = create_app(Settings(db_backend="memory", max_features_per_file=2))
    repository = MemoryRepository()
    application.dependency_overrides[get_repository] = lambda: repository
    with TestClient(application) as client:
        response = client.post(
            "/api/files/",
            files=upload_files("too-many.kml", sample_kml),
        )
    assert response.status_code == 413
    payload = response.json()["error"]
    assert payload["code"] == "FEATURE_LIMIT_EXCEEDED"
    file_id = payload["details"]["file_id"]
    assert repository.files[file_id]["status"] == "FAILED"
    assert file_id not in repository.features


def test_zero_feature_kml_is_completed_with_warning(app_context: Any) -> None:
    """An empty but valid KML file is stored as completed with a warning."""
    client, _repository, _application = app_context
    empty_kml = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document/></kml>'
    response = client.post("/api/files/", files=upload_files("empty.kml", empty_kml))
    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["feature_count"] == 0
    assert any("no features" in warning.lower() for warning in response.json()["warnings"])


def test_missing_prj_assumes_wgs84_only_for_valid_longitude_latitude(
    app_context: Any, tmp_path: Path
) -> None:
    """A .prj-free layer is accepted only when its bounds fit WGS84."""
    client, repository, _application = app_context
    valid_archive = make_shapefile_zip(
        tmp_path / "valid",
        "valid",
        box(1, 1, 1.01, 1.01),
        crs=None,
    )
    valid_upload = client.post(
        "/api/files/",
        files=upload_files("valid.zip", valid_archive),
    )
    assert valid_upload.status_code == 201
    assert any(".prj" in warning for warning in valid_upload.json()["warnings"])
    invalid_archive = make_shapefile_zip(
        tmp_path / "invalid",
        "invalid",
        box(200, 100, 201, 101),
        crs=None,
    )
    invalid_upload = client.post(
        "/api/files/",
        files=upload_files("invalid.zip", invalid_archive),
    )
    assert invalid_upload.status_code == 422
    assert "no .prj" in invalid_upload.json()["error"]["message"]
    file_id = invalid_upload.json()["error"]["details"]["file_id"]
    assert repository.files[file_id]["status"] == "FAILED"
    assert file_id not in repository.features
