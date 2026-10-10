"""FastAPI application factory, lifespan management, and global error handling."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.routes.files import router as files_router
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError, DatabaseUnavailable
from app.db.sqlite import init_sqlite_db
from app.repositories.memory_repository import MemoryRepository
from app.repositories.sqlite_repository import SqliteRepository

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI app; tests can pass isolated settings."""
    configuration = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.settings = configuration
        application.state.repository = None
        application.state.db_connection = None

        if configuration.db_backend == "memory":
            application.state.repository = MemoryRepository()
            logger.info("Initialized In-Memory repository")
        elif configuration.db_backend == "mongodb" and configuration.mongodb_uri:
            try:
                from app.db.mongo import connect_mongo
                from app.repositories.mongo_repository import MongoRepository

                client, database = await connect_mongo(
                    configuration.mongodb_uri,
                    configuration.mongodb_db_name,
                )
                application.state.db_connection = client
                application.state.repository = MongoRepository(database)
                logger.info("Connected to MongoDB at %s", configuration.mongodb_uri)
            except Exception as error:
                logger.error("Failed to connect to MongoDB: %s", error)
        else:
            # Default to local-first zero-dependency SQLite
            try:
                sqlite_db = await init_sqlite_db(configuration.sqlite_db_path)
                application.state.db_connection = sqlite_db
                application.state.repository = SqliteRepository(sqlite_db)
                logger.info("Initialized SQLite repository at %s", configuration.sqlite_db_path)
            except Exception as error:
                logger.exception("Failed to initialize SQLite database: %s", error)

        try:
            yield
        finally:
            conn = application.state.db_connection
            if conn is not None and hasattr(conn, "close"):
                res = conn.close()
                if hasattr(res, "__await__"):
                    await res

    application = FastAPI(
        title="Geospatial File Measurement API",
        version="1.0.0",
        description="Upload KML and zipped Shapefiles, extract features, and calculate projected measurements.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Enable CORS for local testing and web clients
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/", include_in_schema=False)
    async def root_redirect():
        """Redirect root requests directly to interactive Swagger docs."""
        return RedirectResponse(url="/docs")

    @application.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @application.get("/api/openapi.json", include_in_schema=False)
    async def openapi_alias():
        """Alias for /openapi.json."""
        return application.openapi()

    application.include_router(files_router)
    application.include_router(health_router)
    application.state.settings = configuration

    @application.exception_handler(AppError)
    async def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_ERROR",
                    "message": "The request did not match the API requirements.",
                    "details": {"issues": jsonable_encoder(error.errors())},
                }
            },
        )

    @application.exception_handler(HTTPException)
    async def handle_http_error(_request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(error.detail),
                    "details": None,
                }
            },
            headers=error.headers,
        )

    return application


app = create_app()
