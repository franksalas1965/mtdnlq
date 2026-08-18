"""Excepciones personalizadas de MTDNLQ."""


class MTDNLQException(Exception):
    """Excepción base del sistema."""
    def __init__(self, message: str, code: str = "MTDNLQ_error"):
        self.message = message
        self.code = code
        super().__init__(message)


class LLMUnavailableError(MTDNLQException):
    """El proveedor LLM no está disponible."""
    def __init__(self, provider: str, detail: str = ""):
        message = f"El proveedor LLM '{provider}' no está disponible."
        if detail:
            message = f"{message} {detail}"
        super().__init__(message, code="llm_unavailable")
        self.detail = detail


class SQLGenerationError(MTDNLQException):
    """El LLM no pudo generar SQL válido."""
    def __init__(self, detail: str = ""):
        super().__init__(
            "No se pudo generar SQL válido para la pregunta proporcionada. "
            "Intente reformularla con más especificidad.",
            code="sql_generation_failed"
        )
        self.detail = detail


class SQLForbiddenError(MTDNLQException):
    """El SQL generado contiene operaciones no permitidas."""
    def __init__(self, reason: str):
        super().__init__(
            f"Operación SQL no permitida: {reason}",
            code="sql_forbidden"
        )


class DatabaseError(MTDNLQException):
    """Error durante la ejecución de la consulta en la base de datos."""
    def __init__(self, detail: str = ""):
        super().__init__(
            "Error al ejecutar la consulta en la base de datos.",
            code="db_error"
        )
        self.detail = detail


class QueryTimeoutError(MTDNLQException):
    """La consulta excedió el tiempo máximo permitido."""
    def __init__(self, timeout: int):
        super().__init__(
            f"La consulta excedió el tiempo máximo de {timeout} segundos.",
            code="db_timeout"
        )
