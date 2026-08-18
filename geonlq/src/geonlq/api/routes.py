"""Definición de endpoints de la API REST de GeoNLQ."""
import time
import logging
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from .schemas import QueryRequest, QueryResponse, HealthResponse, ErrorResponse
from ..services.query_service import process_query
from ..db.connection import get_db_session, test_connection
from ..db.schema_inspector import schema_inspector
from ..core.config import settings
from ..core.exceptions import (
    LLMUnavailableError, SQLGenerationError, SQLForbiddenError,
    DatabaseError, QueryTimeoutError,
)

router = APIRouter(prefix="/api/v1", tags=["GeoNLQ"])
logger = logging.getLogger(__name__)
_start_time = time.time()


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Consulta en lenguaje natural",
    responses={
        400: {"model": ErrorResponse, "description": "Consulta prohibida o inválida"},
        422: {"model": ErrorResponse, "description": "No se pudo generar SQL válido"},
        503: {"model": ErrorResponse, "description": "LLM no disponible"},
    },
)
async def query(request: QueryRequest):
    """
    Procesa una pregunta en lenguaje natural y retorna resultados
    geoespaciales desde PostGIS.

    **Ejemplo:**
    ```json
    {
      "question": "Dame los puentes de la Carretera Central con carga mayor a 10 toneladas",
      "output_format": "geojson",
      "max_results": 50
    }
    ```
    """
    try:
        return await process_query(request)
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail={"error": e.code, "message": e.message})
    except SQLForbiddenError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})
    except SQLGenerationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": e.code,
                "message": e.message,
                "detail": e.detail or None,
            },
        )
    except QueryTimeoutError as e:
        raise HTTPException(status_code=408, detail={"error": e.code, "message": e.message})
    except DatabaseError as e:
        logger.error("Error de BD: %s", e.detail)
        raise HTTPException(status_code=500, detail={"error": e.code, "message": e.message})
    except Exception as e:
        logger.exception("Error inesperado")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": str(e)})


@router.get(
    "/schema",
    summary="Esquema de tablas disponibles",
    description="Retorna las tablas y columnas disponibles para consultar.",
)
async def get_schema(refresh: bool = Query(default=False, description="Forzar recarga del caché")):
    """Retorna la descripción del esquema PostGIS en texto."""
    schema = schema_inspector.get_schema(force_refresh=refresh)
    tables = []
    for key, table in schema.items():
        if table.name == "query_history":
            continue
        tables.append({
            "name": table.name,
            "schema": table.schema,
            "comment": table.comment,
            "geometry_column": table.geometry_column,
            "geometry_type": table.geometry_type,
            "srid": table.srid,
            "columns": [
                {"name": c.name, "type": c.data_type, "comment": c.comment}
                for c in table.columns
            ],
        })
    return {"tables": tables, "total": len(tables)}


@router.get(
    "/history",
    summary="Historial de consultas",
)
async def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default=None, description="Filtrar por estado: success, error, blocked"),
):
    """Retorna el historial de consultas procesadas."""
    try:
        with get_db_session() as session:
            where = "WHERE status = :status" if status else ""
            rows = session.execute(text(f"""
                SELECT id, question, sql_generated, llm_provider, llm_model,
                       result_count, execution_ms, status, error_msg, created_at
                FROM query_history
                {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """), {"status": status, "limit": limit, "offset": offset}).fetchall()

            total = session.execute(text(
                f"SELECT COUNT(*) FROM query_history {where}",
            ), {"status": status}).scalar()

        return {
            "items": [dict(zip(row._fields, row)) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado del servicio",
)
async def health():
    """Verifica el estado de todos los componentes del sistema."""
    db_ok = test_connection()
    schema = schema_inspector.get_schema()

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        database="connected" if db_ok else "disconnected",
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        schema_cached=schema is not None and len(schema) > 0,
        uptime_seconds=round(time.time() - _start_time, 1),
    )
