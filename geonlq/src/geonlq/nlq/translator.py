"""
Orquestador de traducción NL → SQL.
Gestiona los reintentos con feedback del error anterior.
"""
import logging
from ..llm.base import LLMProvider
from .prompt_builder import build_prompt
from .sql_validator import validate_sql
from ..core.config import settings
from ..core.exceptions import SQLGenerationError, SQLForbiddenError

logger = logging.getLogger(__name__)


async def translate_to_sql(
    question: str,
    llm: LLMProvider,
    max_results: int | None = None,
) -> tuple[str, str]:
    """
    Traduce una pregunta en lenguaje natural a SQL geoespacial válido.

    Estrategia de reintentos: si el SQL generado falla la validación,
    se reintenta enviando el SQL fallido y el error como contexto adicional.

    Args:
        question:    Pregunta en lenguaje natural.
        llm:         Proveedor LLM a usar.
        max_results: Límite de filas para el resultado.

    Returns:
        Tupla (sql_validado, prompt_usado).

    Raises:
        SQLGenerationError: Si tras todos los reintentos no se obtiene SQL válido.
        SQLForbiddenError:  Si el SQL generado contiene operaciones prohibidas.
        LLMUnavailableError: Si el LLM no responde.
    """
    prompt = build_prompt(question)
    last_error = ""
    last_sql = ""

    for attempt in range(1, settings.max_llm_retries + 2):  # +2: intento inicial + reintentos
        if attempt > 1:
            # Reintento: añadir feedback del error anterior al prompt
            retry_context = (
                f"\n\nEl SQL generado anteriormente fue INCORRECTO:\n"
                f"SQL: {last_sql}\n"
                f"Error: {last_error}\n"
                f"Por favor genera un SQL corregido para la pregunta original."
            )
            current_prompt = prompt + retry_context
            logger.info("Reintento %d/%d para la pregunta: %.80s",
                        attempt, settings.max_llm_retries + 1, question)
        else:
            current_prompt = prompt

        try:
            raw_sql = await llm.generate_sql(current_prompt)
            last_sql = raw_sql
            validated_sql = validate_sql(raw_sql, max_results=max_results)
            logger.info("SQL generado en intento %d: %.200s", attempt, validated_sql)
            return validated_sql, current_prompt

        except SQLForbiddenError:
            raise  # No reintentamos operaciones prohibidas

        except SQLGenerationError as e:
            last_error = (e.detail or "").strip() or e.message
            logger.warning("Validación SQL falló (intento %d): %s", attempt, last_error[:300])
            if attempt > settings.max_llm_retries:
                logger.error("NLQ sin SQL válido tras %d intentos: %s", attempt, last_error[:500])
                raise SQLGenerationError(last_error) from e

        except Exception as e:
            last_error = str(e)
            if not last_sql:
                last_sql = "(sin SQL — fallo al llamar al LLM)"
            logger.warning("Error LLM (intento %d): %s", attempt, last_error[:300])
            if attempt > settings.max_llm_retries:
                raise SQLGenerationError(last_error) from e

    raise SQLGenerationError("Se agotaron los reintentos sin generar SQL válido.")
