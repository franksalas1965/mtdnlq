"""Ejecutor de consultas SQL contra PostGIS."""
import logging
import json
import re
from sqlalchemy import text
from .connection import get_db_session
from ..core.config import settings
from ..core.exceptions import DatabaseError, QueryTimeoutError

logger = logging.getLogger(__name__)

# Patrón para detectar WKB/EWKB hex (cadena hex >= 20 caracteres)
_WKB_HEX_RE = re.compile(r'^[0-9A-Fa-f]{20,}$')

# Nombres de columna que PostGIS suele usar para geometría
_GEOM_COLUMN_NAMES = {
    "geom", "the_geom", "geometry", "wkb_geometry",
    "shape", "geom_point", "geom_line", "geom_polygon",
}


def _wkb_to_geojson(hex_str: str) -> dict | None:
    """
    Convierte una cadena WKB/EWKB hex (formato nativo PostGIS) a GeoJSON dict.
    Usa shapely si está disponible; retorna None si falla.
    """
    try:
        from shapely import wkb
        from shapely.geometry import mapping
        geom = wkb.loads(hex_str, hex=True)
        return mapping(geom)
    except Exception as exc:
        logger.debug("No se pudo convertir WKB a GeoJSON: %s", exc)
        return None


def execute_query(sql: str, max_results: int | None = None) -> list[dict]:
    """
    Ejecuta una consulta SELECT en PostGIS y retorna los resultados como lista de dicts.

    Args:
        sql:         SQL a ejecutar (debe ser SELECT ya validado).
        max_results: Límite de filas. Añade LIMIT si no tiene.

    Returns:
        Lista de dicts con los resultados. Las columnas de tipo geometry
        se serializan como GeoJSON bajo la clave "geometry".

    Raises:
        QueryTimeoutError: Si la query excede el timeout configurado.
        DatabaseError:     Por cualquier otro error de BD.
    """
    limit = max_results or settings.max_results

    # Añadir LIMIT si el SQL no lo tiene
    sql_upper = sql.upper().strip()
    if "LIMIT" not in sql_upper:
        sql = f"{sql.rstrip(';')} LIMIT {limit}"

    try:
        with get_db_session() as session:
            result = session.execute(text(sql))
            columns = list(result.keys())
            rows = result.fetchall()

        records = []
        for row in rows:
            record = {}
            for col, val in zip(columns, row):
                # 1. Ya es un dict GeoJSON (ST_AsGeoJSON(geom)::json devuelve dict)
                if isinstance(val, dict) and val.get("type") in (
                    "Point", "LineString", "Polygon",
                    "MultiPoint", "MultiLineString", "MultiPolygon",
                    "GeometryCollection",
                ):
                    record["geometry"] = val
                    continue

                # 2. String que podría ser JSON GeoJSON
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, dict) and parsed.get("type") in (
                            "Point", "LineString", "Polygon",
                            "MultiPoint", "MultiLineString", "MultiPolygon",
                            "GeometryCollection", "Feature", "FeatureCollection",
                        ):
                            record["geometry"] = parsed
                            continue
                    except (json.JSONDecodeError, AttributeError):
                        pass

                    # 3. WKB hex en columna con nombre de geometría conocido
                    if col.lower() in _GEOM_COLUMN_NAMES and _WKB_HEX_RE.match(val):
                        geojson = _wkb_to_geojson(val)
                        if geojson:
                            record["geometry"] = geojson
                            logger.debug(
                                "Columna '%s' convertida de WKB a GeoJSON (%s)",
                                col, geojson.get("type"),
                            )
                            continue

                record[col] = val
            records.append(record)

        logger.info("Query ejecutada: %d filas retornadas", len(records))
        return records

    except DatabaseError:
        raise
    except Exception as e:
        error_msg = str(e)
        if "statement timeout" in error_msg.lower() or "canceling statement" in error_msg.lower():
            raise QueryTimeoutError(settings.sql_timeout) from e
        raise DatabaseError(error_msg) from e
