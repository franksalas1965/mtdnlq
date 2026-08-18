# -*- coding: utf-8 -*-
"""
Almacén local de consultas exitosas — «Query Capsules».

Técnica híbrida:
  - SQLite + FTS5: índice buscable (pregunta, SQL) y metadatos ligeros.
  - Carpeta por consulta (capsule): manifest JSON + assets reutilizables
    (query.sql, results.geojson) que QGIS puede cargar directamente con OGR.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from qgis.PyQt.QtCore import QStandardPaths

from .mtd_fields import normalize_geojson_results

CAPSULE_SCHEMA = "mtdnlq.capsule/v1"
MANIFEST_NAME = "capsule.mtdnlq.json"
SQL_FILE = "query.sql"
RESULTS_GEOJSON = "results.geojson"
RESULTS_JSON = "results.json"


def default_history_root() -> str:
    """Directorio de historial en datos de usuario (persiste al actualizar plugin)."""
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.expanduser("~")
    path = os.path.join(base, "MTD-NLQ", "query_history")
    os.makedirs(path, exist_ok=True)
    return path


class QueryHistoryStore:
    """Persiste y recupera cápsulas de consultas NL exitosas."""

    def __init__(self, root_dir: str | None = None, max_entries: int = 150):
        self.root = root_dir or default_history_root()
        self.capsules_dir = os.path.join(self.root, "capsules")
        self.db_path = os.path.join(self.root, "history.db")
        self.max_entries = max(10, int(max_entries))
        os.makedirs(self.capsules_dir, exist_ok=True)
        self._init_db()

    @property
    def root_path(self) -> str:
        return self.root

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS capsules (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    question TEXT NOT NULL,
                    sql_text TEXT,
                    scale INTEGER,
                    database_name TEXT,
                    total INTEGER,
                    time_ms REAL,
                    display_mode TEXT,
                    has_geometry INTEGER DEFAULT 0,
                    output_format TEXT,
                    folder_path TEXT NOT NULL
                );
                """
            )
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS capsules_fts USING fts5(
                        question,
                        sql_text,
                        content='capsules',
                        content_rowid='rowid'
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS capsules_ai AFTER INSERT ON capsules BEGIN
                        INSERT INTO capsules_fts(rowid, question, sql_text)
                        VALUES (new.rowid, new.question, new.sql_text);
                    END;
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS capsules_ad AFTER DELETE ON capsules BEGIN
                        INSERT INTO capsules_fts(capsules_fts, rowid, question, sql_text)
                        VALUES ('delete', old.rowid, old.question, old.sql_text);
                    END;
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS capsules_au AFTER UPDATE ON capsules BEGIN
                        INSERT INTO capsules_fts(capsules_fts, rowid, question, sql_text)
                        VALUES ('delete', old.rowid, old.question, old.sql_text);
                        INSERT INTO capsules_fts(rowid, question, sql_text)
                        VALUES (new.rowid, new.question, new.sql_text);
                    END;
                    """
                )
                self._fts_enabled = True
            except sqlite3.OperationalError:
                self._fts_enabled = False

    def save_success(self, question: str, response: dict) -> str | None:
        """Guarda una consulta exitosa. Devuelve el id de la cápsula."""
        question = (question or response.get("question") or "").strip()
        if not question:
            return None

        capsule_id = str(uuid.uuid4())
        folder = os.path.join(self.capsules_dir, capsule_id)
        os.makedirs(folder, exist_ok=True)

        output_format = response.get("output_format") or (
            "geojson" if response.get("has_geometry") else "table"
        )
        results = normalize_geojson_results(response.get("results"))
        assets: dict[str, str] = {"sql": SQL_FILE}

        sql_text = str(response.get("sql") or "")
        with open(os.path.join(folder, SQL_FILE), "w", encoding="utf-8") as fh:
            fh.write(sql_text)

        if output_format == "geojson" or (
            isinstance(results, dict) and results.get("type") == "FeatureCollection"
        ):
            assets["results"] = RESULTS_GEOJSON
            with open(os.path.join(folder, RESULTS_GEOJSON), "w", encoding="utf-8") as fh:
                json.dump(results, fh, ensure_ascii=False, indent=2)
        else:
            assets["results"] = RESULTS_JSON
            with open(os.path.join(folder, RESULTS_JSON), "w", encoding="utf-8") as fh:
                json.dump(results, fh, ensure_ascii=False, indent=2)

        created_at = datetime.now(timezone.utc)
        manifest = {
            "schema": CAPSULE_SCHEMA,
            "id": capsule_id,
            "created_at": created_at.isoformat(),
            "question": question,
            "sql": sql_text,
            "scale": response.get("scale"),
            "database": response.get("database"),
            "total": response.get("total", 0),
            "time_ms": response.get("time_ms"),
            "timing_ms": response.get("timing_ms") or {},
            "display_mode": response.get("display_mode"),
            "has_geometry": bool(response.get("has_geometry")),
            "columns": response.get("columns") or [],
            "output_format": output_format,
            "explanation": response.get("explanation"),
            "assets": assets,
        }
        with open(os.path.join(folder, MANIFEST_NAME), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO capsules (
                    id, created_at, question, sql_text, scale, database_name,
                    total, time_ms, display_mode, has_geometry, output_format, folder_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capsule_id,
                    created_at.timestamp(),
                    question,
                    sql_text,
                    response.get("scale"),
                    response.get("database"),
                    int(response.get("total") or 0),
                    float(response.get("time_ms") or 0),
                    response.get("display_mode"),
                    1 if response.get("has_geometry") else 0,
                    output_format,
                    folder,
                ),
            )

        self._enforce_limit()
        return capsule_id

    def _enforce_limit(self) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM capsules
                ORDER BY created_at DESC
                LIMIT -1 OFFSET ?
                """,
                (self.max_entries,),
            ).fetchall()
        for row in rows:
            self.delete(row["id"])

    def list_entries(self, search: str = "", limit: int = 100) -> list[dict[str, Any]]:
        search = search.strip()
        with self._connect() as conn:
            if search and getattr(self, "_fts_enabled", False):
                try:
                    rows = conn.execute(
                        """
                        SELECT c.* FROM capsules c
                        JOIN capsules_fts f ON c.rowid = f.rowid
                        WHERE capsules_fts MATCH ?
                        ORDER BY c.created_at DESC
                        LIMIT ?
                        """,
                        (self._fts_query(search), limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = self._search_like(conn, search, limit)
            elif search:
                rows = self._search_like(conn, search, limit)
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM capsules
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row_to_summary(dict(row)) for row in rows]

    @staticmethod
    def _search_like(conn, search: str, limit: int):
        pattern = f"%{search}%"
        return conn.execute(
            """
            SELECT * FROM capsules
            WHERE question LIKE ? OR sql_text LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()

    @staticmethod
    def _fts_query(text: str) -> str:
        tokens = [t.strip() for t in text.split() if t.strip()]
        if not tokens:
            return text
        return " ".join(f'"{tok}"*' for tok in tokens)

    def load_response(self, capsule_id: str) -> dict[str, Any] | None:
        folder = self._capsule_folder(capsule_id)
        manifest_path = os.path.join(folder, MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            return None

        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)

        assets = manifest.get("assets") or {}
        results = None
        results_name = assets.get("results")
        if results_name:
            results_path = os.path.join(folder, results_name)
            if os.path.isfile(results_path):
                with open(results_path, encoding="utf-8") as fh:
                    results = json.load(fh)

        return {
            "question": manifest.get("question"),
            "sql": manifest.get("sql"),
            "results": results,
            "total": manifest.get("total", 0),
            "time_ms": manifest.get("time_ms", 0),
            "timing_ms": manifest.get("timing_ms") or {},
            "explanation": manifest.get("explanation"),
            "display_mode": manifest.get("display_mode", "table"),
            "columns": manifest.get("columns") or [],
            "has_geometry": manifest.get("has_geometry", False),
            "scale": manifest.get("scale"),
            "database": manifest.get("database"),
            "_capsule_id": capsule_id,
            "_capsule_folder": folder,
            "_results_geojson_path": (
                os.path.join(folder, RESULTS_GEOJSON)
                if os.path.isfile(os.path.join(folder, RESULTS_GEOJSON))
                else None
            ),
        }

    def delete(self, capsule_id: str) -> bool:
        folder = self._capsule_folder(capsule_id)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM capsules WHERE id = ?", (capsule_id,))
            deleted = cur.rowcount > 0
        if os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)
        return deleted

    def capsule_folder(self, capsule_id: str) -> str:
        return self._capsule_folder(capsule_id)

    def _capsule_folder(self, capsule_id: str) -> str:
        return os.path.join(self.capsules_dir, capsule_id)

    @staticmethod
    def _row_to_summary(row: dict) -> dict[str, Any]:
        created = datetime.fromtimestamp(row["created_at"], tz=timezone.utc)
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "created_label": created.strftime("%Y-%m-%d %H:%M"),
            "question": row["question"],
            "sql": row["sql_text"],
            "scale": row["scale"],
            "database": row["database_name"],
            "total": row["total"],
            "time_ms": row["time_ms"],
            "display_mode": row["display_mode"],
            "has_geometry": bool(row["has_geometry"]),
            "folder_path": row["folder_path"],
        }
