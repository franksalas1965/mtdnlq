"""Tabla query_history — creación automática si no existe."""
from __future__ import annotations

import logging
import threading

from sqlalchemy import text

from ..core.config import settings
from .connection import get_db_session

logger = logging.getLogger(__name__)

_CREATE_QUERY_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS public.query_history (
    id            BIGSERIAL PRIMARY KEY,
    question      TEXT NOT NULL,
    sql_generated TEXT,
    llm_provider  VARCHAR(50),
    llm_model     VARCHAR(100),
    result_count  INTEGER,
    execution_ms  NUMERIC(10, 2),
    status        VARCHAR(20),
    error_msg     TEXT,
    created_at    TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_query_history_created_at
    ON public.query_history (created_at DESC);
"""

_lock = threading.Lock()
_ensured_scales: set[int] = set()


def ensure_query_history_table(scale: int | None = None) -> None:
    """Crea public.query_history en la BD de la escala si aún no existe."""
    if scale is None:
        from ..core.scale import parse_scale_from_database_url

        scale = parse_scale_from_database_url(settings.database_url)

    with _lock:
        if scale in _ensured_scales:
            return

        with get_db_session(scale) as session:
            session.execute(text(_CREATE_QUERY_HISTORY_SQL))

        _ensured_scales.add(scale)
        logger.info("Tabla query_history verificada en escala %s", scale)


def ensure_query_history_for_enabled_scales() -> None:
    """Asegura query_history en todas las escalas MTD habilitadas."""
    for scale in settings.mtd_enabled_scales_list:
        try:
            ensure_query_history_table(scale)
        except Exception as exc:
            logger.warning(
                "No se pudo crear query_history en escala %s: %s",
                scale,
                exc,
            )
