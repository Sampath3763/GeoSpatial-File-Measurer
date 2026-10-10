"""Optional MongoDB client setup and index creation."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def connect_mongo(uri: str, database_name: str) -> tuple[Any, Any]:
    """Connect to MongoDB if pymongo is installed and URI is configured."""
    try:
        try:
            from pymongo import AsyncMongoClient
        except ImportError:
            # Fallback for environments with standard pymongo / motor
            from pymongo import MongoClient as AsyncMongoClient  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pymongo is not installed in the environment.") from exc

    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000, tz_aware=True)
    try:
        if hasattr(client.admin, "command") and callable(client.admin.command):
            res = client.admin.command("ping")
            if hasattr(res, "__await__"):
                await res
        database = client[database_name]
        return client, database
    except Exception:
        if hasattr(client, "close"):
            res = client.close()
            if hasattr(res, "__await__"):
                await res
        logger.warning("MongoDB startup check failed")
        raise
