"""Modelos Pydantic para requests y responses de la API."""
from typing import Any, Literal
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Petición de consulta en lenguaje natural."""
    question: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Pregunta en lenguaje natural sobre los datos geoespaciales",
        examples=["Dame los puentes de la Carretera Central con carga mayor a 10 toneladas"],
    )
    output_format: Literal["geojson", "table"] = Field(
        default="geojson",
        description="Formato de los resultados: 'geojson' o 'table' (JSON tabular)",
    )
    max_results: int = Field(
        default=100,
        ge=0,
        le=1000,
        description=(
            "Número máximo de resultados a retornar. "
            "Use 0 para devolver todos los registros (sin LIMIT automático)."
        ),
    )
    explain: bool = Field(
        default=False,
        description="Si es True, incluye una explicación del SQL generado",
    )
    scale: int = Field(
        default=10000,
        description=(
            "Denominador de escala MTD: 10000=1:10 000 (mtd10), "
            "25000=1:25 000 (mtd25), 100000=1:100 000 (mtd100). "
            "Un mismo servicio puede atender varias escalas en paralelo."
        ),
        examples=[10000, 25000],
    )


class QueryResponse(BaseModel):
    """Respuesta con los resultados de la consulta."""
    question: str
    sql: str = Field(description="SQL geoespacial generado por el LLM")
    results: Any = Field(description="Resultados: GeoJSON FeatureCollection o lista de objetos")
    total: int = Field(description="Número de registros retornados")
    time_ms: float = Field(description="Tiempo total de procesamiento en milisegundos")
    timing_ms: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Desglose de tiempos por fase: preparing, generating_sql, "
            "executing_sql, formatting, explaining, total"
        ),
    )
    explanation: str | None = Field(
        default=None,
        description="Explicación del SQL generado (solo si explain=True)",
    )
    # ── Campos para el cliente web ────────────────────────────────────────────
    display_mode: Literal["map", "table", "summary"] = Field(
        default="table",
        description=(
            "Modo de visualización recomendado para el cliente web.\n"
            "  map     → los resultados tienen geometría, mostrar en mapa\n"
            "  table   → sin geometría, múltiples filas, mostrar como tabla\n"
            "  summary → sin geometría, 1 fila o agregación, mostrar como resumen"
        ),
    )
    columns: list[str] = Field(
        default_factory=list,
        description="Nombres de las columnas del resultado (útil para renderizar tablas)",
    )
    has_geometry: bool = Field(
        default=False,
        description="True si al menos un feature tiene geometría no nula",
    )
    scale: int = Field(
        default=10000,
        description="Escala MTD usada en la consulta (denominador, ej. 10000)",
    )
    database: str = Field(
        default="",
        description="Base de datos PostGIS consultada (ej. mtd10)",
    )


class HealthResponse(BaseModel):
    """Estado del servicio."""
    status: str
    database: str
    llm_provider: str
    llm_model: str
    schema_cached: bool
    uptime_seconds: float
    enabled_scales: list[int] = Field(
        default_factory=list,
        description="Escalas MTD habilitadas en esta instancia",
    )
    recommended_client_timeout_seconds: int = Field(
        default=600,
        description="Timeout HTTP recomendado para clientes (plugin, web)",
    )
    queue: dict = Field(
        default_factory=dict,
        description="Estado de la cola asíncrona de consultas",
    )
    llm: dict = Field(
        default_factory=dict,
        description="Configuración LLM activa en el servidor (sin secretos)",
    )


class ErrorResponse(BaseModel):
    """Respuesta de error estándar."""
    error: str
    message: str
    detail: str | None = None
    request_id: str | None = None


class JobSubmitResponse(BaseModel):
    """Respuesta al encolar una consulta asíncrona (HTTP 202)."""
    job_id: str
    status: Literal["queued"] = "queued"
    scale: int
    poll_url: str
    message: str = "Consulta encolada. Consulte GET /api/v1/jobs/{job_id} hasta status=completed."


class JobStatusResponse(BaseModel):
    """Estado de un job asíncrono."""
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    question: str
    scale: int
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    queue_position: int | None = Field(
        default=None,
        description="Posición en cola (1 = siguiente en ejecutarse)",
    )
    poll_url: str
    phase: str | None = Field(
        default=None,
        description="Fase actual del pipeline (generating_sql, executing_sql, …)",
    )
    phase_label: str | None = Field(
        default=None,
        description="Etiqueta legible de la fase actual",
    )
    sql_generated: str | None = Field(
        default=None,
        description="SQL parcial o final mientras el job está en ejecución",
    )
    timing_ms: dict[str, float] = Field(
        default_factory=dict,
        description="Tiempos acumulados por fase hasta el momento del poll",
    )
    result: QueryResponse | None = None
    error: dict | None = None


class QueueStatsResponse(BaseModel):
    """Estadísticas de la cola de jobs."""
    queued: int
    running: int
    completed: int
    failed: int
    max_concurrent_llm_jobs: int
    max_queued_jobs: int
