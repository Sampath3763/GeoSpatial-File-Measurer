"""Production-grade SQLite repository for local-first zero-dependency persistence."""

import json
import sqlite3
from typing import Any

from app.db.sqlite import SqliteDatabase
from app.models import FeatureRecord
from app.repositories.base import FileRepository


class SqliteRepository(FileRepository):
    """File and feature storage backed by a local SQLite database."""

    def __init__(self, db: SqliteDatabase) -> None:
        self.db = db

    @property
    def backend_name(self) -> str:
        return "sqlite"

    async def health_check(self) -> bool:
        def _check(conn: sqlite3.Connection) -> bool:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            res = cur.fetchone()
            cur.close()
            return bool(res and res[0] == 1)

        return await self.db.execute(_check)

    async def create_file(self, document: dict[str, Any]) -> None:
        def _create(conn: sqlite3.Connection) -> None:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO uploaded_files (
                    id, filename, file_type, size_bytes, crs, feature_count,
                    status, warnings, error_message, geometry_type_counts,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    document["id"],
                    document["filename"],
                    document["file_type"],
                    document["size_bytes"],
                    document.get("crs"),
                    document.get("feature_count", 0),
                    document.get("status", "PENDING"),
                    json.dumps(document.get("warnings", [])),
                    document.get("error_message"),
                    json.dumps(document.get("geometry_type_counts", {})),
                    str(document["created_at"]),
                    str(document.get("completed_at")) if document.get("completed_at") else None,
                ),
            )
            cur.close()

        await self.db.execute(_create)

    async def update_file(self, file_id: str, fields: dict[str, Any]) -> None:
        def _update(conn: sqlite3.Connection) -> None:
            if not fields:
                return
            set_clauses = []
            values = []
            for key, val in fields.items():
                if key in {"warnings", "geometry_type_counts"} and not isinstance(val, str):
                    val = json.dumps(val)
                elif val is not None and not isinstance(val, (int, float, str, bytes)):
                    val = str(val)
                set_clauses.append(f"{key} = ?")
                values.append(val)
            values.append(file_id)

            sql = f"UPDATE uploaded_files SET {', '.join(set_clauses)} WHERE id = ?;"
            cur = conn.cursor()
            cur.execute(sql, values)
            cur.close()

        await self.db.execute(_update)

    async def insert_features(self, file_id: str, features: list[FeatureRecord]) -> None:
        def _insert(conn: sqlite3.Connection) -> None:
            if not features:
                return
            cur = conn.cursor()
            rows = [
                (
                    file_id,
                    f.feature_index,
                    f.layer,
                    f.geometry_type,
                    json.dumps(f.geometry) if f.geometry is not None else None,
                    f.crs,
                    json.dumps(f.properties if f.properties is not None else {}),
                    f.measurement_status,
                    f.area_sq_m,
                    f.length_m,
                    f.projected_crs,
                    f.measurement_method,
                    f.note,
                )
                for f in features
            ]
            cur.executemany(
                """
                INSERT INTO features (
                    file_id, feature_index, layer, geometry_type, geometry,
                    crs, properties, measurement_status, area_sq_m, length_m,
                    projected_crs, measurement_method, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
            cur.close()

        await self.db.execute(_insert)

    async def delete_features(self, file_id: str) -> None:
        def _delete(conn: sqlite3.Connection) -> None:
            cur = conn.cursor()
            cur.execute("DELETE FROM features WHERE file_id = ?;", (file_id,))
            cur.close()

        await self.db.execute(_delete)

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        def _get(conn: sqlite3.Connection) -> dict[str, Any] | None:
            cur = conn.cursor()
            cur.execute("SELECT * FROM uploaded_files WHERE id = ?;", (file_id,))
            row = cur.fetchone()
            cur.close()
            if not row:
                return None
            data = dict(row)
            data["warnings"] = json.loads(data["warnings"] or "[]")
            data["geometry_type_counts"] = json.loads(data["geometry_type_counts"] or "{}")
            return data

        return await self.db.execute(_get)

    async def list_files(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        def _list(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], int]:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM uploaded_files;")
            total = cur.fetchone()[0]

            cur.execute(
                "SELECT * FROM uploaded_files ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                (limit, offset),
            )
            rows = cur.fetchall()
            cur.close()

            items = []
            for row in rows:
                data = dict(row)
                data["warnings"] = json.loads(data["warnings"] or "[]")
                data["geometry_type_counts"] = json.loads(data["geometry_type_counts"] or "{}")
                items.append(data)
            return items, total

        return await self.db.execute(_list)

    async def delete_file(self, file_id: str) -> bool:
        def _delete(conn: sqlite3.Connection) -> bool:
            cur = conn.cursor()
            cur.execute("DELETE FROM features WHERE file_id = ?;", (file_id,))
            cur.execute("DELETE FROM uploaded_files WHERE id = ?;", (file_id,))
            deleted = cur.rowcount > 0
            cur.close()
            return deleted

        return await self.db.execute(_delete)

    async def get_features(
        self, file_id: str, limit: int, offset: int, geometry_type: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        def _get_feats(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], int]:
            cur = conn.cursor()
            if geometry_type:
                cur.execute(
                    "SELECT COUNT(*) FROM features WHERE file_id = ? AND geometry_type = ?;",
                    (file_id, geometry_type),
                )
                filtered_total = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT * FROM features WHERE file_id = ? AND geometry_type = ?
                    ORDER BY feature_index ASC LIMIT ? OFFSET ?;
                    """,
                    (file_id, geometry_type, limit, offset),
                )
            else:
                cur.execute("SELECT COUNT(*) FROM features WHERE file_id = ?;", (file_id,))
                filtered_total = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT * FROM features WHERE file_id = ?
                    ORDER BY feature_index ASC LIMIT ? OFFSET ?;
                    """,
                    (file_id, limit, offset),
                )
            rows = cur.fetchall()
            cur.close()

            features = []
            for row in rows:
                item = dict(row)
                if item["geometry"]:
                    item["geometry"] = json.loads(item["geometry"])
                if item["properties"]:
                    item["properties"] = json.loads(item["properties"])
                else:
                    item["properties"] = {}
                features.append(item)
            return features, filtered_total

        return await self.db.execute(_get_feats)

    async def summarize_features(self, file_id: str) -> dict[str, Any]:
        def _summary(conn: sqlite3.Connection) -> dict[str, Any]:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(area_sq_m), 0.0),
                    COALESCE(SUM(length_m), 0.0)
                FROM features
                WHERE file_id = ? AND measurement_status = 'CALCULATED';
                """,
                (file_id,),
            )
            sums = cur.fetchone()
            total_area = round(float(sums[0]), 4) if sums else 0.0
            total_length = round(float(sums[1]), 4) if sums else 0.0

            cur.execute(
                "SELECT geometry_type, COUNT(*) FROM features WHERE file_id = ? GROUP BY geometry_type;",
                (file_id,),
            )
            geom_counts = {row[0]: row[1] for row in cur.fetchall()}

            cur.execute(
                "SELECT measurement_status, COUNT(*) FROM features WHERE file_id = ? GROUP BY measurement_status;",
                (file_id,),
            )
            status_counts = {row[0]: row[1] for row in cur.fetchall()}
            cur.close()

            return {
                "total_area_sq_m": total_area,
                "total_length_m": total_length,
                "counts_by_geometry_type": geom_counts,
                "counts_by_measurement_status": status_counts,
            }

        return await self.db.execute(_summary)
