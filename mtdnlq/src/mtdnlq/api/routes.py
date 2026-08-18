"""Definición de endpoints de la API REST de MTDNLQ."""
import time
import logging
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from .schemas import (
    QueryRequest,
    QueryResponse,
    HealthResponse,
    ErrorResponse,
    JobSubmitResponse,
    JobStatusResponse,
    QueueStatsResponse,
)
from ..services.query_service import process_query
from ..services.job_queue import job_queue
from ..db.connection import get_db_session, test_connection
from ..db.schema_inspector import schema_inspector
from ..core.config import settings
from ..core.scale import database_name
from ..llm.ollama_config import llm_public_info
from ..core.exceptions import (
    LLMUnavailableError, SQLGenerationError, SQLForbiddenError,
    DatabaseError, QueryTimeoutError,
)

router = APIRouter(prefix="/api/v1", tags=["MTD-NLQ"])
logger = logging.getLogger(__name__)
_start_time = time.time()


def _validate_scale(scale: int) -> None:
    if scale not in settings.mtd_enabled_scales_list:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "scale_not_enabled",
                "message": (
                    f"Escala {scale} no está habilitada en este servidor. "
                    f"Escalas disponibles: {settings.mtd_enabled_scales_list}"
                ),
            },
        )


def _map_query_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMUnavailableError):
        return HTTPException(status_code=503, detail={"error": exc.code, "message": exc.message})
    if isinstance(exc, SQLForbiddenError):
        return HTTPException(status_code=400, detail={"error": exc.code, "message": exc.message})
    if isinstance(exc, SQLGenerationError):
        return HTTPException(
            status_code=422,
            detail={
                "error": exc.code,
                "message": exc.message,
                "detail": exc.detail or None,
            },
        )
    if isinstance(exc, QueryTimeoutError):
        return HTTPException(status_code=408, detail={"error": exc.code, "message": exc.message})
    if isinstance(exc, DatabaseError):
        logger.error("Error de BD: %s", exc.detail)
        return HTTPException(status_code=500, detail={"error": exc.code, "message": exc.message})
    logger.exception("Error inesperado")
    return HTTPException(status_code=500, detail={"error": "internal_error", "message": str(exc)})


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Consulta en lenguaje natural (síncrona)",
    responses={
        400: {"model": ErrorResponse, "description": "Consulta prohibida o inválida"},
        422: {"model": ErrorResponse, "description": "No se pudo generar SQL válido"},
        503: {"model": ErrorResponse, "description": "LLM no disponible"},
    },
)
async def query(request: QueryRequest):
    """
    Procesa una pregunta en lenguaje natural y retorna resultados
    geoespaciales desde PostGIS (bloquea hasta terminar).

    Para múltiples clientes concurrentes use `POST /query/async`.
    """
    try:
        _validate_scale(request.scale)
        return await process_query(request)
    except HTTPException:
        raise
    except Exception as e:
        raise _map_query_exception(e) from e


@router.post(
    "/query/async",
    response_model=JobSubmitResponse,
    status_code=202,
    summary="Encolar consulta NL (asíncrona)",
    responses={
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse, "description": "Cola llena"},
    },
)
async def query_async(request: QueryRequest):
    """
    Encola la consulta y responde de inmediato con un `job_id`.
    Consulte `GET /api/v1/jobs/{job_id}` hasta que `status` sea `completed` o `failed`.

    Recomendado para plugin QGIS, web y varios usuarios simultáneos.
    """
    _validate_scale(request.scale)
    try:
        job = await job_queue.submit(request)
        return JobSubmitResponse(
            job_id=job.id,
            scale=request.scale,
            poll_url=f"/api/v1/jobs/{job.id}",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "queue_full", "message": str(exc)},
        ) from exc


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Estado de una consulta asíncrona",
    responses={404: {"model": ErrorResponse}},
)
async def get_job_status(job_id: str):
    """Devuelve el estado del job y el resultado cuando `status=completed`."""
    job = job_queue.get(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"Job {job_id} no existe o expiró"},
        )
    data = job.to_public_dict()
    return JobStatusResponse(**data)


@router.get(
    "/queue/stats",
    response_model=QueueStatsResponse,
    summary="Estadísticas de la cola de consultas",
)
async def queue_stats():
    """Muestra cuántos jobs hay en cola, en ejecución, etc."""
    return QueueStatsResponse(**job_queue.stats())


@router.get(
    "/config/llm",
    summary="Configuración LLM del servidor (solo lectura)",
)
async def get_llm_config():
    """Metadatos del LLM activo. Las claves API nunca se exponen."""
    return llm_public_info()


@router.get(
    "/schema",
    summary="Esquema de tablas disponibles",
    description="Retorna las tablas y columnas disponibles para consultar.",
)
async def get_schema(
    scale: int = Query(default=10000, description="Denominador de escala MTD (10000, 25000…)"),
    refresh: bool = Query(default=False, description="Forzar recarga del caché"),
):
    """Retorna las tablas y columnas de la escala indicada."""
    _validate_scale(scale)
    schema = schema_inspector.get_schema(scale, force_refresh=refresh)
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
    return {"scale": scale, "database": database_name(scale), "tables": tables, "total": len(tables)}


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
    default_scale = settings.default_scale
    db_ok = test_connection(default_scale)
    schema = schema_inspector.get_schema(default_scale)

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        database="connected" if db_ok else "disconnected",
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        schema_cached=schema is not None and len(schema) > 0,
        uptime_seconds=round(time.time() - _start_time, 1),
        enabled_scales=settings.mtd_enabled_scales_list,
        recommended_client_timeout_seconds=settings.recommended_client_timeout_seconds,
        queue=job_queue.stats(),
        llm=llm_public_info(),
    )
