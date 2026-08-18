"""
Orquestador principal del flujo NL → SQL → Resultado.
Coordina todos los componentes y registra el historial.
"""
import time
import logging
from collections.abc import Callable
from typing import Any, Literal
from sqlalchemy import text
from ..nlq.translator import translate_to_sql
from ..db.executor import execute_query
from ..db.connection import get_db_session
from ..llm.factory import create_llm_provider
from ..api.schemas import QueryRequest, QueryResponse
from ..core.config import settings
from ..core.exceptions import DatabaseError, QueryTimeoutError
from ..core.scale import database_name
from .query_progress import QueryProgressTracker

logger = logging.getLogger(__name__)

_SQL_TIMEOUT_HINT = (
    "\n\n[OPTIMIZACIÓN: La consulta anterior excedió el timeout de PostgreSQL. "
    "Reescriba usando EXISTS (SELECT 1 FROM ...) en lugar de varios JOIN. "
    "Filtre ILIKE dentro de cada EXISTS. "
    "Use ST_DWithin(geom::geography, geom::geography, metros) solo dentro de EXISTS. "
    "Para geometría con varios filtros espaciales use CTE: "
    "WITH candidatos AS (SELECT geo_id FROM ... WHERE EXISTS ... LIMIT N) "
    "SELECT ..., ST_AsGeoJSON(geom)::json AS geometry FROM tabla JOIN candidatos USING (geo_id).]"
)

# Proveedor LLM (singleton creado al importar)
_llm_provider = None


def get_llm_provider():
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = create_llm_provider()
    return _llm_provider


async def process_query(
    request: QueryRequest,
    on_phase: Callable[[str, dict[str, Any]], None] | None = None,
) -> QueryResponse:
    """
    Procesa una consulta en lenguaje natural de principio a fin.

    Flujo:
      1. Construir prompt con esquema PostGIS
      2. Enviar al LLM → SQL
      3. Validar SQL
      4. Ejecutar en PostGIS
      5. Formatear resultado y detectar modo de visualización
      6. Registrar en historial
    """
    start_time = time.perf_counter()
    progress = QueryProgressTracker(on_phase=on_phase)
    sql_generated = ""
    status = "success"
    error_msg = None
    rows = []
    scale = request.scale

    if scale not in settings.mtd_enabled_scales_list:
        raise DatabaseError(
            f"Escala {scale} no habilitada. Escalas disponibles: "
            f"{settings.mtd_enabled_scales_list}"
        )

    try:
        progress.enter("preparing")
        llm = get_llm_provider()
        question_for_llm = request.question

        for exec_attempt in range(2):
            try:
                progress.enter("generating_sql", attempt=exec_attempt + 1)
                sql_generated, _ = await translate_to_sql(
                    question=question_for_llm,
                    llm=llm,
                    max_results=request.max_results,
                    scale=scale,
                )
                progress.set_sql(sql_generated)

                progress.enter("executing_sql", attempt=exec_attempt + 1)
                rows = execute_query(
                    sql_generated, max_results=request.max_results, scale=scale
                )
                break
            except QueryTimeoutError as e:
                if exec_attempt == 0:
                    logger.warning(
                        "Timeout SQL (intento %d), reintentando con SQL optimizado",
                        exec_attempt + 1,
                    )
                    question_for_llm = request.question + _SQL_TIMEOUT_HINT
                    continue
                raise DatabaseError(
                    f"La consulta excedió {settings.sql_timeout}s. "
                    "Simplifique la pregunta, cree índices GIST (docs/sql/create_gist_indexes_mtd10.sql) "
                    "o aumente SQL_TIMEOUT en .env."
                ) from e

        progress.enter("formatting")
        results = _format_results(rows, request.output_format)
        display_mode, columns, has_geometry = _detect_display_mode(rows, results)

        explanation = None
        if request.explain:
            progress.enter("explaining")
            explanation = await _generate_explanation(request.question, sql_generated, llm)

        timing = progress.finish()
        elapsed_ms = timing.get("total", (time.perf_counter() - start_time) * 1000)

        response = QueryResponse(
            question=request.question,
            sql=sql_generated,
            results=results,
            total=len(rows),
            time_ms=round(elapsed_ms, 2),
            timing_ms=timing,
            explanation=explanation,
            display_mode=display_mode,
            columns=columns,
            has_geometry=has_geometry,
            scale=scale,
            database=database_name(scale),
        )

    except Exception as e:
        status = "error"
        error_msg = str(e)
        raise

    finally:
        _record_history(
            question=request.question,
            sql=sql_generated,
            result_count=len(rows) if status == "success" else 0,
            execution_ms=(time.perf_counter() - start_time) * 1000,
            status=status,
            error_msg=error_msg,
        )

    return response


def _format_results(rows: list[dict], output_format: str) -> dict | list:
    """Convierte las filas a GeoJSON FeatureCollection o lista tabular."""
    if output_format == "geojson":
        features = []
        for row in rows:
            geometry = None
            properties = {}
            for key, value in row.items():
                if key == "geometry" or (
                    isinstance(value, dict) and value.get("type") in (
                        "Point", "LineString", "Polygon",
                        "MultiPoint", "MultiLineString", "MultiPolygon",
                        "GeometryCollection",
                    )
                ):
                    geometry = value
                else:
                    properties[key] = value
            features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": properties,
            })
        return {"type": "FeatureCollection", "features": features}
    else:
        return rows


def _detect_display_mode(
    rows: list[dict],
    results: dict | list,
) -> tuple[Literal["map", "table", "summary"], list[str], bool]:
    """
    Detecta el modo de visualización óptimo para el cliente web.

    Returns:
        (display_mode, columns, has_geometry)
        display_mode:
            "map"     → hay geometría → mostrar en mapa (MapLibre)
            "summary" → sin geometría, 1 fila o columna numérica sola → resumen
            "table"   → sin geometría, múltiples filas → tabla (MUI DataGrid)
        columns: lista de nombres de columnas (propiedades sin geometría)
        has_geometry: True si algún feature tiene geometría no nula
    """
    if not rows:
        return "table", [], False

    first_row = rows[0]
    columns = [
        k for k in first_row.keys()
        if k != "geometry" and not (
            isinstance(first_row[k], dict) and
            first_row[k].get("type") in (
                "Point", "LineString", "Polygon",
                "MultiPoint", "MultiLineString", "MultiPolygon",
                "GeometryCollection",
            )
        )
    ]

    has_geometry = False
    if isinstance(results, dict) and results.get("type") == "FeatureCollection":
        has_geometry = any(
            f.get("geometry") is not None
            for f in results.get("features", [])
        )

    if has_geometry:
        return "map", columns, True

    is_summary = (
        len(rows) == 1 or
        (len(rows) <= 3 and len(columns) <= 3)
    )

    if is_summary:
        return "summary", columns, False

    return "table", columns, False


async def _generate_explanation(question: str, sql: str, llm) -> str:
    """Pide al LLM una explicación breve del SQL en lenguaje natural."""
    try:
        prompt = (
            f"Explica en 2-3 frases en español qué hace el siguiente SQL en el contexto "
            f"de la pregunta. Sé conciso y técnico.\n\n"
            f"Pregunta: {question}\n"
            f"SQL: {sql}\n\n"
            f"Explicación:"
        )
        return await llm.generate_sql(prompt)
    except Exception:
        return None


def _record_history(question, sql, result_count, execution_ms, status, error_msg):
    """Registra la consulta en query_history (best-effort)."""
    try:
        with get_db_session() as session:
            session.execute(text("""
                INSERT INTO query_history
                    (question, sql_generated, llm_provider, llm_model,
                     result_count, execution_ms, status, error_msg)
                VALUES
                    (:q, :sql, :prov, :model, :count, :ms, :status, :err)
            """), {
                "q": question,
                "sql": sql,
                "prov": settings.llm_provider,
                "model": settings.llm_model,
                "count": result_count,
                "ms": round(execution_ms, 2),
                "status": status,
                "err": error_msg,
            })
    except Exception as e:
        logger.warning("No se pudo registrar en historial: %s", e)
