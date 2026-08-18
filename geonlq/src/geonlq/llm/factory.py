"""Factory para instanciar el proveedor LLM según configuración."""
from .base import LLMProvider
from ..core.config import settings
from ..core.exceptions import GeoNLQException


def create_llm_provider() -> LLMProvider:
    """
    Retorna la instancia del proveedor LLM configurado en settings.LLM_PROVIDER.

    Returns:
        Instancia de LLMProvider lista para usar.

    Raises:
        GeoNLQException: Si el proveedor configurado no es reconocido.
    """
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif provider == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider()
    else:
        raise GeoNLQException(
            f"Proveedor LLM desconocido: '{provider}'. "
            f"Valores válidos: openai, anthropic, ollama",
            code="invalid_llm_provider"
        )
