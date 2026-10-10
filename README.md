# Geospatial File Measurement System

This repository provides a production-grade, local-independent backend API for geospatial file measurement, along with an optional web review interface.

---

## Dedicated Backend API (`/backend`)

The core backend API has been completely modularized into the [`backend/`](./backend) directory. It is 100% independent of any cloud providers or Replit dependencies and runs locally out-of-the-box using standard Python tools and zero-setup SQLite persistence.

### Key Capabilities:
- **File Support**: Accepts `.kml` files and `.zip` archives containing ESRI Shapefiles.
- **Feature Extraction**: Extracts feature indices, geometry types, GeoJSON geometries, coordinate reference systems (CRS), and metadata properties.
- **Smart Projection**: Detects geographic coordinates (`EPSG:4326`) and transforms them into local projected coordinate systems (automatic UTM zones, UPS polar projections, equal-area, or geodesic) before calculating measurements.
- **Precise Measurements**: Calculates Polygon areas in $\text{m}^2$ and LineString lengths in meters. Points are handled as `NOT_APPLICABLE` and unsupported geometries are gracefully reported without crashing.
- **Local Independence**: Uses SQLite (WAL mode) as the default database for local persistence across restarts, with support for in-memory testing or optional MongoDB.
- **RESTful Endpoints**:
  - `POST /api/files/` — Upload and process a geospatial file
  - `GET /api/files/{id}/` — Get file status and metadata
  - `GET /api/files/{id}/measurements/` — Get calculated measurements and file aggregates
  - `GET /api/files/{id}/features/` — Get raw GeoJSON features and attributes
  - `GET /api/files/` — List all uploaded files
  - `DELETE /api/files/{id}/` — Delete an uploaded file and its measurements
  - `GET /api/health` — Storage-agnostic health check

### Quick Start for the Backend:

```bash
# 1. Navigate to the backend directory
cd backend

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
python run.py
```

The interactive Swagger UI is available at: **http://127.0.0.1:8000/docs**

To run the automated test suite (34 passing tests):
```bash
python -m pytest
```

For full architecture details, mathematical CRS handling formulas, and endpoint examples, see the [Backend Documentation](./backend/README.md).

---

## Repository Structure

```text
arero/
├── backend/                     # Dedicated standalone FastAPI Backend
│   ├── app/                     # Application source code (routes, services, repositories)
│   ├── samples/                 # Sample KML and Shapefile datasets
│   ├── tests/                   # Full test suite (34 tests)
│   ├── run.py                   # Local server entrypoint
│   ├── requirements.txt         # Pinned Python dependencies
│   ├── pyproject.toml           # Pytest and linter configuration
│   └── README.md                # Comprehensive backend API documentation
├── artifacts/                   # Frontend assets and review desk
│   └── geo-measurement/         # React / Vite review desk (local-independent)
└── package.json                 # Optional frontend workspace configuration
```
