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
        ge=1,
        le=1000,
        description="Número máximo de resultados a retornar",
    )
    explain: bool = Field(
        default=False,
        description="Si es True, incluye una explicación del SQL generado",
    )


class QueryResponse(BaseModel):
    """Respuesta con los resultados de la consulta."""
    question: str
    sql: str = Field(description="SQL geoespacial generado por el LLM")
    results: Any = Field(description="Resultados: GeoJSON FeatureCollection o lista de objetos")
    total: int = Field(description="Número de registros retornados")
    time_ms: float = Field(description="Tiempo total de procesamiento en milisegundos")
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


class HealthResponse(BaseModel):
    """Estado del servicio."""
    status: str
    database: str
    llm_provider: str
    llm_model: str
    schema_cached: bool
    uptime_seconds: float


class ErrorResponse(BaseModel):
    """Respuesta de error estándar."""
    error: str
    message: str
    detail: str | None = None
    request_id: str | None = None
