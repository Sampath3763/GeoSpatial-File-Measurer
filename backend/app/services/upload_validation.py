"""Streaming upload limits and defensive archive validation."""

import re
import zipfile
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import AppError

CHUNK_SIZE = 1024 * 1024


def sanitize_filename(filename: str | None) -> str:
    """Reduce an untrusted client name to a display-only basename."""
    raw_name = (filename or "").replace("\\", "/").split("/")[-1]
    safe_name = "".join(character for character in raw_name if character.isprintable()).strip()
    return safe_name or "upload"


async def save_upload_stream(
    upload: UploadFile,
    target_path: str,
    settings: Settings,
) -> int:
    """Write chunks to a temporary path and reject uploads above the byte limit."""
    total_bytes = 0
    try:
        with open(target_path, "wb") as destination:
            while chunk := await upload.read(CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_bytes:
                    raise AppError(
                        "UPLOAD_TOO_LARGE",
                        f"Upload exceeds the {settings.max_upload_mb} MB limit.",
                        413,
                        {"max_upload_mb": settings.max_upload_mb},
                    )
                destination.write(chunk)
    finally:
        await upload.close()
    if total_bytes == 0:
        raise AppError("EMPTY_FILE", "The uploaded file is empty.", 400)
    return total_bytes


def validate_shapefile_archive(archive_path: str, settings: Settings) -> None:
    """Reject unsafe archives and ensure every .shp has required sidecars."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_zip_entries:
                raise AppError(
                    "ZIP_ENTRY_LIMIT",
                    f"The ZIP contains more than {settings.max_zip_entries} entries.",
                    422,
                    {"max_zip_entries": settings.max_zip_entries},
                )
            expanded_bytes = sum(entry.file_size for entry in entries)
            if expanded_bytes > settings.max_unzipped_bytes:
                raise AppError(
                    "UNZIPPED_SIZE_LIMIT",
                    f"The ZIP expands beyond the {settings.max_unzipped_mb} MB limit.",
                    422,
                    {"max_unzipped_mb": settings.max_unzipped_mb},
                )
            _reject_unsafe_paths(entries)
            shapefiles = {
                _casefold_path(entry.filename)
                for entry in entries
                if entry.filename.lower().endswith(".shp")
            }
            if not shapefiles:
                raise AppError(
                    "SHAPEFILE_MISSING",
                    "The ZIP must contain at least one .shp Shapefile.",
                    422,
                )
            missing: set[str] = set()
            archive_names = {_casefold_path(entry.filename) for entry in entries}
            for shape_path in shapefiles:
                for suffix in (".shx", ".dbf"):
                    companion = shape_path[:-4] + suffix
                    if companion not in archive_names:
                        missing.add(suffix)
            if missing:
                missing_names = ", ".join(sorted(missing))
                raise AppError(
                    "SHAPEFILE_COMPONENTS_MISSING",
                    f"The ZIP is missing required Shapefile component(s): {missing_names}.",
                    422,
                    {"missing_components": sorted(missing)},
                )
            corrupt_entry = archive.testzip()
            if corrupt_entry:
                raise AppError(
                    "CORRUPT_ZIP",
                    f"The ZIP contains a corrupt entry: {PurePosixPath(corrupt_entry).name}.",
                    422,
                )
    except zipfile.BadZipFile as error:
        raise AppError(
            "CORRUPT_ZIP",
            "The uploaded .zip file is invalid or corrupt.",
            422,
        ) from error


def _reject_unsafe_paths(entries: list[Any]) -> None:
    """Reject traversal, absolute paths, Windows drives, and symlink entries."""
    for entry in entries:
        name = entry.filename
        normalized = name.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(name)
        if (
            normalized.startswith("/")
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or ".." in posix_path.parts
            or "\x00" in name
        ):
            raise AppError("UNSAFE_ZIP_PATH", "The ZIP contains an unsafe file path.", 422)
        mode = entry.external_attr >> 16
        if mode and (mode & 0o170000) == 0o120000:
            raise AppError("UNSAFE_ZIP_PATH", "The ZIP contains a symbolic link.", 422)


def _casefold_path(path: str) -> str:
    """Normalize an archive path for case-insensitive sidecar matching."""
    return re.sub(r"/+", "/", path.replace("\\", "/")).casefold()
