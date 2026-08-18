"""Utilidades de conexión Ollama local, cloud y opciones CPU/GPU."""
from ..core.config import (
    DEFAULT_LLM_MODEL_CLOUD,
    DEFAULT_LLM_MODEL_LOCAL,
    settings,
)


def resolve_ollama_base_url() -> str:
    """URL base sin /api (ej. http://localhost:11434 o https://ollama.com)."""
    if settings.ollama_mode == "cloud":
        return settings.ollama_cloud_base_url.rstrip("/")
    return settings.ollama_base_url.rstrip("/")


def build_ollama_headers() -> dict[str, str]:
    """Cabeceras HTTP; cloud requiere Bearer OLLAMA_API_KEY."""
    headers: dict[str, str] = {}
    if settings.ollama_mode == "cloud":
        key = (settings.ollama_api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    return headers


def cloud_api_key_configured() -> bool:
    return bool((settings.ollama_api_key or "").strip())


def build_ollama_options() -> dict:
    """
    Opciones del payload Ollama (temperature, num_gpu, num_thread).

    - cloud: el hardware lo gestiona ollama.com; no forzar GPU local.
    - local cpu: num_gpu=0
    - local gpu: num_gpu=-1 (todas las capas) o valor explícito
    - local auto: omitir num_gpu salvo OLLAMA_NUM_GPU explícito
    """
    options: dict = {"temperature": 0}

    if settings.ollama_mode == "cloud":
        return options

    device = settings.ollama_device.lower()
    if device == "cpu":
        options["num_gpu"] = 0
    elif device == "gpu":
        options["num_gpu"] = settings.ollama_num_gpu if settings.ollama_num_gpu >= 0 else -1
    elif device == "auto" and settings.ollama_num_gpu >= 0:
        options["num_gpu"] = settings.ollama_num_gpu

    if settings.ollama_num_thread > 0:
        options["num_thread"] = settings.ollama_num_thread

    return options


def llm_public_info() -> dict:
    """Metadatos LLM para /health (sin secretos)."""
    base = resolve_ollama_base_url()
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "llm_model_auto_selected": settings.llm_model_auto_selected,
        "default_llm_model_cloud": DEFAULT_LLM_MODEL_CLOUD,
        "default_llm_model_local": DEFAULT_LLM_MODEL_LOCAL,
        "ollama_mode": settings.ollama_mode,
        "ollama_device": settings.ollama_device if settings.ollama_mode == "local" else "cloud",
        "ollama_base_url": base,
        "ollama_api_key_configured": cloud_api_key_configured(),
        "ollama_timeout_seconds": settings.ollama_timeout_seconds,
        "max_concurrent_llm_jobs": settings.max_concurrent_llm_jobs,
    }
