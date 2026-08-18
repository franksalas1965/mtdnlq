"""
Orquestador principal del flujo NL → SQL → Resultado.
Coordina todos los componentes y registra el historial.
"""
import time
import logging
from typing import Literal
from sqlalchemy import text
from ..nlq.translator import translate_to_sql
from ..db.executor import execute_query
from ..db.connection import get_db_session
from ..db.schema_inspector import schema_inspector
from ..llm.factory import create_llm_provider
from ..api.schemas import QueryRequest, QueryResponse
from ..core.config import settings

logger = logging.getLogger(__name__)

# Proveedor LLM (singleton creado al importar)
_llm_provider = None


def get_llm_provider():
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = create_llm_provider()
    return _llm_provider


async def process_query(request: QueryRequest) -> QueryResponse:
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
    sql_generated = ""
    status = "success"
    error_msg = None
    rows = []

    try:
        llm = get_llm_provider()

        # 1-3. Traducir NL → SQL (incluye prompt building y validación)
        sql_generated, _ = await translate_to_sql(
            question=request.question,
            llm=llm,
            max_results=request.max_results,
        )

        # 4. Ejecutar query
        rows = execute_query(sql_generated, max_results=request.max_results)

        # 5. Formatear resultado
        results = _format_results(rows, request.output_format)

        # Detectar modo de visualización y metadatos de columnas
        display_mode, columns, has_geometry = _detect_display_mode(rows, results)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Generar explicación si se solicitó
        explanation = None
        if request.explain:
            explanation = await _generate_explanation(request.question, sql_generated, llm)

        response = QueryResponse(
            question=request.question,
            sql=sql_generated,
            results=results,
            total=len(rows),
            time_ms=round(elapsed_ms, 2),
            explanation=explanation,
            display_mode=display_mode,
            columns=columns,
            has_geometry=has_geometry,
        )

    except Exception as e:
        status = "error"
        error_msg = str(e)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        raise

    finally:
        # 6. Registrar en historial (best-effort, no bloquear si falla)
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

    # Extraer columnas sin la columna geometry
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

    # Detectar si hay geometría
    has_geometry = False
    if isinstance(results, dict) and results.get("type") == "FeatureCollection":
        has_geometry = any(
            f.get("geometry") is not None
            for f in results.get("features", [])
        )

    if has_geometry:
        return "map", columns, True

    # Sin geometría: ¿es un resumen (1 fila o solo columnas agregadas)?
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
        return await llm.generate_sql(prompt)  # Reutilizamos el método LLM
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
