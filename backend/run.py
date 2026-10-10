"""Entrypoint script to run the Geospatial File Measurement API server locally."""

import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import uvicorn  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    """Run uvicorn development server."""
    settings = get_settings()
    print(f"Starting Geospatial File Measurement API on http://{settings.host}:{settings.port}")
    print(f"Storage backend: {settings.db_backend}")
    print(f"API Docs available at: http://{settings.host}:{settings.port}/docs")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
