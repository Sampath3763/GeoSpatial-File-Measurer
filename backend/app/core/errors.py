"""Domain errors translated into the API's stable JSON error envelope."""

from typing import Any


class AppError(Exception):
    """An expected application error safe to return to an API caller."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class DatabaseUnavailable(AppError):
    """The database is not configured or cannot be reached."""

    def __init__(self, message: str = "The database is unavailable.") -> None:
        super().__init__("DATABASE_UNAVAILABLE", message, 503)


class FileProcessingError(AppError):
    """A file was accepted but its contents could not be processed."""

    def __init__(self, message: str, file_id: str, status_code: int = 422) -> None:
        super().__init__(
            "FILE_PROCESSING_FAILED",
            message,
            status_code,
            {"file_id": file_id},
        )


class ReaderValidationError(Exception):
    """A safe, user-actionable content error raised by a geospatial reader."""


class TooManyFeatures(AppError):
    """An upload exceeded the configured feature-count limit."""

    def __init__(self, maximum: int, file_id: str | None = None) -> None:
        details: dict[str, Any] = {"max_features": maximum}
        if file_id:
            details["file_id"] = file_id
        super().__init__(
            "FEATURE_LIMIT_EXCEEDED",
            f"The file contains more than the maximum of {maximum:,} features.",
            413,
            details,
        )
