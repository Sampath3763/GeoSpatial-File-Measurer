# Geospatial Backend API & GIS Processing Architecture

This document outlines the file locations, architectural flow, and endpoints responsible for analyzing, projecting, and calculating measurements for GIS files (.kml and Shapefile .zip).

---

## 1. Core GIS Processing Files

The following files contain the primary logic for processing, reading, transforming, and measuring geospatial data:

### 1.1 GIS File Parser & Feature Extractor
* **File Location**: [`backend/app/services/geo_reader.py`](file:///d:/Projects/arero/backend/app/services/geo_reader.py)
* **Key Function**: `read_and_measure(input_path, file_type, maximum_features)`
* **Responsibilities**:
  * Ingests `.kml` files and `.zip` archives containing Shapefiles.
  * Inspects and extracts individual feature geometries (`Polygon`, `LineString`, `Point`, `MultiPolygon`, etc.).
  * Sanitizes attributes and metadata properties into safe data types.
  * Strips 3D Z/M coordinates down to 2D representations while logging appropriate warnings.
  * Incorporates an `lxml` XML parser fallback to guarantee parsing even if the host environment lacks GDAL KML drivers.

---

### 1.2 Coordinate Reference System (CRS) & Projection Strategy
* **File Location**: [`backend/app/services/crs.py`](file:///d:/Projects/arero/backend/app/services/crs.py)
* **Key Functions**:
  * `normalize_to_wgs84(geometry, source_crs)`
  * `select_measurement_crs(geometry_wgs84)`
  * `project_geometry(geometry_wgs84, target_crs)`
  * `geodesic_length(geometry)`
* **Responsibilities**:
  * Normalizes geographic coordinates (`EPSG:4326`) using `pyproj.Transformer`.
  * **Dynamic UTM Zone Selection**: Evaluates feature longitude/latitude and selects the optimal local UTM zone (`EPSG:32600 + zone` for Northern Hemisphere, `EPSG:32700 + zone` for Southern Hemisphere).
  * **Polar Projections**: Maps latitudes $> 84^\circ$ to UPS North (`EPSG:32661`) and $< -80^\circ$ to UPS South (`EPSG:32761`).
  * **Dateline & Multi-Zone**: Employs cylindrical equal-area (`EPSG:6933`) for polygons or geodesic calculation (`pyproj.Geod`) for lines crossing the antimeridian.

---

### 1.3 Geometric Measurements Engine
* **File Location**: [`backend/app/services/measurement.py`](file:///d:/Projects/arero/backend/app/services/measurement.py)
* **Key Function**: `measure_geometry(geometry, source_crs)`
* **Responsibilities**:
  * **Polygon / MultiPolygon**: Calculates projected surface area in $\text{m}^2$, hectares, and $\text{km}^2$.
  * **LineString / MultiLineString**: Calculates projected length in meters and kilometers.
  * **Point / MultiPoint**: Classifies as `NOT_APPLICABLE` (no area/distance).
  * **Geometry Repair**: Automatically repairs self-intersecting rings via `shapely.make_valid` while preserving valid polygonal parts.
  * **Fault Tolerance**: Gracefully handles `GeometryCollection` or unsupported types with `UNSUPPORTED` status without interrupting processing.

---

### 1.4 Archive & Upload Security Validation
* **File Location**: [`backend/app/services/upload_validation.py`](file:///d:/Projects/arero/backend/app/services/upload_validation.py)
* **Key Functions**:
  * `validate_shapefile_archive(archive_path, settings)`
  * `save_upload_stream(upload, target_path, settings)`
  * `sanitize_filename(filename)`
* **Responsibilities**:
  * Verifies presence of mandatory Shapefile sidecar components (`.shp`, `.shx`, `.dbf`).
  * Enforces streaming upload limits (`max_upload_mb`) and uncompressed size bounds (`max_unzipped_mb`) to prevent Zip Bombs.
  * Guards against Zip Slip path traversal attacks (`../` directory escapes).

---

## 2. Pipeline Orchestration & Endpoints

### 2.1 File Service Coordinator
* **File Location**: [`backend/app/services/file_service.py`](file:///d:/Projects/arero/backend/app/services/file_service.py)
* **Key Class**: `FileService`
* **Workflow**:
  1. Streams uploaded bytes into a temporary sandbox.
  2. Runs security validation on archive structures.
  3. Records an initial `PROCESSING` document in the repository.
  4. Calls `geo_reader.read_and_measure` asynchronously on a background thread.
  5. Performs batch insertion of feature records (`insert_features`).
  6. Finalizes file status to `COMPLETED` with aggregated summaries.

---

### 2.2 FastAPI Route Controllers
* **File Location**: [`backend/app/api/routes/files.py`](file:///d:/Projects/arero/backend/app/api/routes/files.py)
* **Endpoints**:
  * `POST /api/files/`: Accepts `.kml` or `.zip` Shapefiles and processes them synchronously.
  * `GET /api/files/`: Returns a paginated list of all uploaded files.
  * `GET /api/files/{file_id}/`: Returns file metadata, total features, and processing status.
  * `GET /api/files/{file_id}/measurements/`: Returns feature-level area/length measurements and whole-file summaries.
  * `GET /api/files/{file_id}/features/`: Returns raw GeoJSON geometries and property dictionaries (supports `include_geometry=false` for high-speed preview).
  * `DELETE /api/files/{file_id}/`: Deletes an uploaded file document and its stored features.

* **Health Check**:
  * **File Location**: [`backend/app/api/routes/health.py`](file:///d:/Projects/arero/backend/app/api/routes/health.py)
  * `GET /api/health` or `/api/healthz`: Verifies database connectivity.

---

## 3. Data Storage & Local Persistence

* **Database Engine**: SQLite running in WAL (Write-Ahead Logging) mode.
* **Database File Path**:
  ```text
  D:\Projects\arero\backend\data\geo_measurement.db
  ```
* **Database Implementation**:
  * Connection & Schema Init: [`backend/app/db/sqlite.py`](file:///d:/Projects/arero/backend/app/db/sqlite.py)
  * Repository Operations: [`backend/app/repositories/sqlite_repository.py`](file:///d:/Projects/arero/backend/app/repositories/sqlite_repository.py)

### Tables Stored:
1. **`uploaded_files`**:
   - `id`: File UUID (Hex)
   - `filename`: Original upload name
   - `file_type`: `kml` or `shapefile`
   - `crs`: Detected source CRS
   - `feature_count`: Total geometries found
   - `status`: `COMPLETED` / `PROCESSING` / `FAILED`
   - `geometry_type_counts`: JSON breakdown of feature types
   - `created_at` / `completed_at`: Timestamps

2. **`features`**:
   - `file_id`: Foreign key linked to `uploaded_files.id`
   - `feature_index`: Feature sequence number
   - `geometry_type`: GeoJSON type (`Polygon`, `LineString`, etc.)
   - `geometry`: 2D GeoJSON structure
   - `properties`: Extracted attribute dictionary
   - `measurement_status`: `CALCULATED`, `NOT_APPLICABLE`, etc.
   - `area_sq_m`: Area in $\text{m}^2$
   - `length_m`: Length in meters
   - `projected_crs`: Local UTM projection applied

---

## 4. Run Commands

### 4.1 Backend Server
```powershell
cd D:\Projects\arero\backend
python run.py
```
* **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### 4.2 Frontend Web Review Desk
```powershell
cd D:\Projects\arero
npx pnpm --filter @workspace/geo-measurement run dev
```
* **UI URL**: [http://localhost:3000](http://localhost:3000)

### 4.3 Automated Tests
```powershell
cd D:\Projects\arero\backend
python -m pytest
```
