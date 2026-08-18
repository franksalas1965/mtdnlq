"""
Inspector de esquema PostGIS.
Lee automáticamente las tablas, columnas y geometrías disponibles,
construye una descripción en texto para inyectar en los prompts del LLM,
y cachea el resultado por escala MTD.
"""
import time
import logging
from dataclasses import dataclass, field
from sqlalchemy import text
from .connection import get_db_session
from ..core.config import settings
from ..core.scale import scale_prefix

logger = logging.getLogger(__name__)


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    comment: str = ""
    nullable: bool = True


@dataclass
class TableInfo:
    schema: str
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    geometry_column: str = ""
    geometry_type: str = ""
    srid: int = 4326
    comment: str = ""


class SchemaInspector:
    """Inspecciona el esquema de PostGIS y construye contexto para el LLM."""

    def __init__(self):
        self._cache: dict[int, dict[str, TableInfo]] = {}
        self._cache_time: dict[int, float] = {}
        self._ttl: int = settings.schema_cache_ttl

    def get_schema(self, scale: int, force_refresh: bool = False) -> dict[str, TableInfo]:
        """Retorna el esquema cacheado para una escala, recargándolo si expiró."""
        now = time.time()
        last = self._cache_time.get(scale, 0)
        if force_refresh or scale not in self._cache or (now - last) > self._ttl:
            self._cache[scale] = self._load_schema(scale)
            self._cache_time[scale] = now
            logger.info(
                "Esquema PostGIS recargado escala %s (%d tablas)",
                scale,
                len(self._cache[scale]),
            )
        return self._cache[scale]

    def _discover_schemas(self, session, scale: int) -> list[str]:
        """Lista esquemas temáticos N_* en la BD de la escala."""
        prefix = scale_prefix(scale)
        like_pattern = prefix.replace("_", "\\_") + "%"
        rows = session.execute(
            text("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name LIKE :pattern ESCAPE '\\'
                ORDER BY schema_name
            """),
            {"pattern": like_pattern},
        ).fetchall()

        excluded = [
            s.strip().lower()
            for s in settings.excluded_schema_suffixes.split(",")
            if s.strip()
        ]
        schemas = []
        for row in rows:
            name = row.schema_name
            if any(name.lower().endswith(ex) for ex in excluded):
                continue
            schemas.append(name)

        if schemas:
            return schemas

        # Fallback: filtrar ALLOWED_SCHEMAS del .env por prefijo
        return [
            s for s in settings.allowed_schemas_list
            if s.startswith(prefix)
        ]

    def _load_schema(self, scale: int) -> dict[str, TableInfo]:
        tables: dict[str, TableInfo] = {}

        with get_db_session(scale) as session:
            allowed = self._discover_schemas(session, scale)
            if not allowed:
                logger.warning("Sin esquemas MTD para escala %s", scale)
                return tables

            geo_rows = session.execute(text("""
                SELECT f_table_schema, f_table_name, f_geometry_column, type, srid
                FROM geometry_columns
                WHERE f_table_schema = ANY(:schemas)
            """), {"schemas": allowed}).fetchall()

            for row in geo_rows:
                key = f"{row.f_table_schema}.{row.f_table_name}"
                tables[key] = TableInfo(
                    schema=row.f_table_schema,
                    name=row.f_table_name,
                    geometry_column=row.f_geometry_column,
                    geometry_type=row.type,
                    srid=row.srid,
                )

            table_rows = session.execute(text("""
                SELECT table_schema, table_name,
                       obj_description(
                           (quote_ident(table_schema)||'.'||quote_ident(table_name))::regclass
                       ) AS table_comment
                FROM information_schema.tables
                WHERE table_schema = ANY(:schemas)
                  AND table_type = 'BASE TABLE'
            """), {"schemas": allowed}).fetchall()

            for row in table_rows:
                key = f"{row.table_schema}.{row.table_name}"
                if key not in tables:
                    tables[key] = TableInfo(
                        schema=row.table_schema,
                        name=row.table_name,
                        comment=row.table_comment or "",
                    )
                else:
                    tables[key].comment = row.table_comment or ""

            col_rows = session.execute(text("""
                SELECT
                    c.table_schema,
                    c.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    col_description(
                        (quote_ident(c.table_schema)||'.'||quote_ident(c.table_name))::regclass,
                        c.ordinal_position
                    ) AS col_comment
                FROM information_schema.columns c
                WHERE c.table_schema = ANY(:schemas)
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
            """), {"schemas": allowed}).fetchall()

            for row in col_rows:
                key = f"{row.table_schema}.{row.table_name}"
                if key in tables:
                    tables[key].columns.append(ColumnInfo(
                        name=row.column_name,
                        data_type=row.data_type,
                        comment=row.col_comment or "",
                        nullable=(row.is_nullable == "YES"),
                    ))

        return tables

    def build_schema_description(self, scale: int) -> str:
        schema = self.get_schema(scale)
        lines = [f"ESQUEMA DE BASE DE DATOS PostGIS (escala {scale}):\n"]

        for key, table in schema.items():
            if table.name == "query_history":
                continue

            lines.append(f"Tabla: {table.schema}.{table.name}")
            if table.comment:
                lines.append(f"  Descripción: {table.comment}")
            if table.geometry_column:
                lines.append(
                    f"  Geometría: columna '{table.geometry_column}' "
                    f"tipo {table.geometry_type} SRID={table.srid}"
                )
            lines.append("  Columnas:")
            for col in table.columns:
                comment_part = f"  -- {col.comment}" if col.comment else ""
                lines.append(f"    - {col.name} ({col.data_type}){comment_part}")
            lines.append("")

        return "\n".join(lines)


schema_inspector = SchemaInspector()
