"""Simbología MTD desde public.layer_styles (PostgreSQL)."""
from __future__ import annotations

import logging

from sqlalchemy import text

from ..db.connection import get_db_session

logger = logging.getLogger(__name__)

VALID_MODES = frozenset({"e", "i", "s"})


def fetch_layer_style_qml(
    schema: str,
    table: str,
    scale: int,
    mode: str = "i",
) -> tuple[str | None, str | None]:
    """
    Obtiene el QML de layer_styles para una capa MTD.

    Returns:
        (style_qml, stylename) o (None, None) si no hay estilo.
    """
    if not schema or not table:
        return None, None

    style_mode = mode.strip().lower() if mode else "i"
    if style_mode not in VALID_MODES:
        style_mode = "i"

    preferred_name = f"{table}_{style_mode}"
    alt_name = f"{schema}.{table}_{style_mode}"

    try:
        with get_db_session(scale) as session:
            row = session.execute(
                text(
                    """
                    SELECT styleqml, stylename
                    FROM public.layer_styles
                    WHERE f_table_schema = :schema
                      AND f_table_name = :table
                      AND stylename = :stylename
                    LIMIT 1
                    """
                ),
                {"schema": schema, "table": table, "stylename": preferred_name},
            ).fetchone()

            if not row and alt_name != preferred_name:
                row = session.execute(
                    text(
                        """
                        SELECT styleqml, stylename
                        FROM public.layer_styles
                        WHERE f_table_schema = :schema
                          AND f_table_name = :table
                          AND stylename = :stylename
                        LIMIT 1
                        """
                    ),
                    {"schema": schema, "table": table, "stylename": alt_name},
                ).fetchone()

            if not row:
                row = session.execute(
                    text(
                        """
                        SELECT styleqml, stylename
                        FROM public.layer_styles
                        WHERE f_table_schema = :schema
                          AND f_table_name = :table
                        ORDER BY
                          CASE WHEN "useAsDefault" THEN 0 ELSE 1 END,
                          id
                        LIMIT 1
                        """
                    ),
                    {"schema": schema, "table": table},
                ).fetchone()

            if not row or not row[0]:
                return None, None

            return str(row[0]), str(row[1]) if row[1] else None
    except Exception as exc:
        logger.warning(
            "No se pudo leer layer_styles para %s.%s (escala %s): %s",
            schema,
            table,
            scale,
            exc,
        )
        return None, None
