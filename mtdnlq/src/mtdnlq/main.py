"""
MTD-NLQ — Punto de entrada de la aplicación FastAPI.
Consultas en lenguaje natural sobre Mapa Topográfico Digital (MTD).
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router
from .core.config import settings
from .db.connection import test_connection
from .db.schema_inspector import schema_inspector

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("mtdnlq")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida: startup → yield → shutdown."""
    # === STARTUP ===
    logger.info("Iniciando MTD-NLQ v%s", settings.api_version)

    if test_connection():
        logger.info("Conexión a PostgreSQL/PostGIS: OK")
        default_scale = settings.default_scale
        schema = schema_inspector.get_schema(default_scale)
        logger.info(
            "Esquema cargado escala %s (%d tablas). Escalas habilitadas: %s",
            default_scale,
            len(schema),
            settings.mtd_enabled_scales_list,
        )
    else:
        logger.warning("No se pudo conectar a la base de datos. Verifica DATABASE_URL en .env")

    logger.info("LLM provider: %s | Modelo: %s", settings.llm_provider, settings.llm_model)
    logger.info("CORS orígenes permitidos: %s", settings.cors_origins)
    logger.info("Servicio listo (puerto configurado al arrancar uvicorn, ej. 8001)")
    logger.info("Documentación: /docs")

    yield

    # === SHUTDOWN ===
    logger.info("MTD-NLQ detenido.")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=(
        "Servicio que permite realizar consultas geoespaciales sobre PostGIS "
        "usando lenguaje natural. Traduce preguntas en español a SQL geoespacial "
        "mediante un LLM y retorna los resultados en GeoJSON o formato tabular.\n\n"
        "**Campos clave de la respuesta:**\n"
        "- `display_mode`: `map` | `table` | `summary` — cómo mostrar el resultado en el cliente\n"
        "- `columns`: nombres de columnas sin geometría (para construir tablas)\n"
        "- `has_geometry`: si los resultados tienen geometría (para activar el mapa)\n"
        "- `results`: GeoJSON FeatureCollection — consumible directamente por MapLibre"
    ),
    lifespan=lifespan,
    debug=settings.debug,
)

# CORS — configurable desde .env (CORS_ORIGINS)
cors_origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=cors_origins != ["*"],
)

# Registrar rutas
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "MTD-NLQ",
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/api/v1/health",
        "query": "POST /api/v1/query",
        "schema": "GET /api/v1/schema",
        "history": "GET /api/v1/history",
    }
