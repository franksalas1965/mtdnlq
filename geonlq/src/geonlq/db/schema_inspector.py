"""
Inspector de esquema PostGIS.
Lee automáticamente las tablas, columnas y geometrías disponibles,
construye una descripción en texto para inyectar en los prompts del LLM,
y cachea el resultado para no repetir la consulta en cada petición.
"""
import time
import logging
from dataclasses import dataclass, field
from sqlalchemy import text
from .connection import get_db_session
from ..core.config import settings

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
        self._cache: dict[str, TableInfo] | None = None
        self._cache_time: float = 0
        self._ttl: int = settings.schema_cache_ttl

    def get_schema(self, force_refresh: bool = False) -> dict[str, TableInfo]:
        """Retorna el esquema cacheado, recargándolo si expiró."""
        now = time.time()
        if force_refresh or self._cache is None or (now - self._cache_time) > self._ttl:
            self._cache = self._load_schema()
            self._cache_time = now
            logger.info("Esquema PostGIS recargado (%d tablas)", len(self._cache))
        return self._cache

    def _load_schema(self) -> dict[str, TableInfo]:
        """Carga tablas y columnas desde el catálogo de PostgreSQL."""
        tables: dict[str, TableInfo] = {}
        allowed = settings.allowed_schemas_list

        with get_db_session() as session:
            # 1. Tablas con geometría (PostGIS geometry_columns)
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

            # 2. También incluir tablas sin geometría
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

            # 3. Columnas de cada tabla
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

    def build_schema_description(self) -> str:
        """
        Construye una descripción en texto del esquema para incluir en el prompt.
        Formato optimizado para que el LLM entienda qué tablas y columnas existen.
        """
        schema = self.get_schema()
        lines = ["ESQUEMA DE BASE DE DATOS PostGIS:\n"]

        for key, table in schema.items():
            if table.name == "query_history":
                continue  # No exponer la tabla interna al LLM

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


# Instancia singleton
schema_inspector = SchemaInspector()
