"""
Validador de SQL generado por el LLM.
Garantiza que solo se ejecuten sentencias SELECT seguras.
"""
import re
import logging
from ..core.config import settings
from ..core.exceptions import SQLForbiddenError, SQLGenerationError

logger = logging.getLogger(__name__)

# Palabras clave que indican operaciones no permitidas
FORBIDDEN_KEYWORDS = [
    r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b",
    r"\bCREATE\b", r"\bALTER\b", r"\bTRUNCATE\b", r"\bGRANT\b",
    r"\bREVOKE\b", r"\bEXECUTE\b", r"\bCALL\b", r"\bCOPY\b",
    r"\bpg_exec\b", r"\bpg_read_file\b", r"\bpg_ls_dir\b",
]


def validate_sql(sql: str, max_results: int | None = None) -> str:
    """
    Valida y sanitiza el SQL generado.

    Args:
        sql:         SQL generado por el LLM.
        max_results: Límite máximo de filas a agregar si falta LIMIT.

    Returns:
        SQL validado y sanitizado.

    Raises:
        SQLGenerationError: Si el SQL está vacío o no es una sentencia SELECT.
        SQLForbiddenError:  Si el SQL contiene operaciones prohibidas.
    """
    if not sql or not sql.strip():
        raise SQLGenerationError("El LLM devolvió una respuesta vacía.")

    sql = sql.strip().rstrip(";")

    # Verificar palabras clave prohibidas (insensible a mayúsculas)
    for pattern in FORBIDDEN_KEYWORDS:
        if re.search(pattern, sql, re.IGNORECASE):
            keyword = re.search(pattern, sql, re.IGNORECASE).group()
            logger.warning("SQL prohibido detectado: %s en: %.200s", keyword, sql)
            raise SQLForbiddenError(f"Operación '{keyword}' no permitida.")

    # Debe comenzar con SELECT (después de posibles CTEs WITH)
    sql_stripped = sql.strip()
    if not re.match(r"^\s*(WITH\s|SELECT\s)", sql_stripped, re.IGNORECASE):
        raise SQLGenerationError(
            f"El SQL generado no comienza con SELECT: {sql_stripped[:100]}"
        )

    # Restricción de schemas: patrones schema.tabla (ignorar alias cortos tipo p.col, v.col)
    allowed = settings.allowed_schemas_list
    schema_refs = re.findall(r"\b(\w+)\.(\w+)\b", sql)
    invalid_schemas = [
        s
        for s, _col in schema_refs
        if len(s) > 2
        and s not in allowed
        and s.lower()
        not in ("st", "public", "pg_catalog", "information_schema")
    ]
    if invalid_schemas:
        logger.warning("SQL referencia schemas no permitidos: %s", invalid_schemas)
        # No bloqueamos (podría ser un alias), solo registramos

    limit = max_results or settings.max_results
    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {limit}"

    return sql
