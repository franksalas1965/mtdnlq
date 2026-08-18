"""Configuración central del servicio MTD-NLQ."""
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .scale import parse_enabled_scales, parse_scale_from_database_url

# Raíz del proyecto (mtdnlq/) — .env siempre desde aquí, no desde el cwd de uvicorn
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"

# Modelos por defecto según modo Ollama (ver docs/CONFIGURACION_LLM.md)
DEFAULT_LLM_MODEL_LOCAL = "qwen2.5-coder:7b"
DEFAULT_LLM_MODEL_CLOUD = "gemma4:31b"
# Valores que activan selección automática al cambiar local ↔ cloud
_LLM_MODEL_AUTO_LOCAL = frozenset(
    {"gpt-4o", "qwen2.5-coder:1.5b", DEFAULT_LLM_MODEL_LOCAL}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.is_file() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Base de datos — plantilla de conexión; el nombre mtdN cambia según escala
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5433/mtd10"

    # Escalas atendidas por esta instancia (una URL de servicio, varias BDs)
    # Ej.: 10000,25000,100000 → mtd10, mtd25, mtd100 en el mismo PostgreSQL
    mtd_enabled_scales: str = "10000"

    # Proveedor LLM
    llm_provider: Literal["openai", "anthropic", "ollama"] = "ollama"
    llm_model: str = "gpt-4o"

    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Ollama — local (CPU/GPU) o cloud (ollama.com)
    ollama_mode: Literal["local", "cloud"] = "local"
    ollama_base_url: str = "http://localhost:11434"
    ollama_cloud_base_url: str = "https://ollama.com"
    ollama_api_key: str = ""
    # local: auto | cpu | gpu  —  cloud ignora device (hardware remoto)
    ollama_device: Literal["auto", "cpu", "gpu"] = "auto"
    # -1 = dejar a Ollama; 0 = solo CPU; >0 = capas en GPU
    ollama_num_gpu: int = -1
    # 0 = auto; >0 = hilos CPU explícitos (solo local)
    ollama_num_thread: int = 0
    ollama_timeout_seconds: int = 180

    # CORS — orígenes permitidos separados por coma
    cors_origins: str = "*"

    # Caché de esquema
    schema_cache_ttl: int = 300  # segundos

    # Límites
    max_results: int = 100
    sql_timeout: int = 120  # segundos (consultas espaciales con JOIN pueden tardar)
    max_llm_retries: int = 2
    max_concurrent_llm_jobs: int = 1
    max_queued_jobs: int = 100
    job_retention_seconds: int = 3600

    # Esquemas extra a excluir siempre (patrón por sufijo)
    excluded_schema_suffixes: str = "configuraciones"

    # Fallback si no se auto-descubren esquemas (compatibilidad mtd10)
    allowed_schemas: str = (
        "10_areas_verdes_y_terrenos,10_hidrografia,10_hidrografia_presas,"
        "10_limites_estatales,10_objetivos_economicos,10_provincias_y_cercas,"
        "10_puntos_de_apoyo,10_puntos_poblados,10_red_vial,10_relieve"
    )

    # Logging
    log_level: str = "INFO"

    # API
    api_title: str = "MTD-NLQ — Consultas NL sobre Mapa Topográfico Digital (MTD)"
    api_version: str = "1.0.0"
    debug: bool = False

    @model_validator(mode="after")
    def resolve_llm_model_for_ollama_mode(self) -> Self:
        """Asigna modelo cloud/local si LLM_MODEL no fue fijado explícitamente."""
        if self.llm_provider != "ollama":
            return self
        if self.ollama_mode == "cloud":
            if self.llm_model in _LLM_MODEL_AUTO_LOCAL:
                object.__setattr__(self, "llm_model", DEFAULT_LLM_MODEL_CLOUD)
        elif self.llm_model == "gpt-4o":
            object.__setattr__(self, "llm_model", DEFAULT_LLM_MODEL_LOCAL)
        return self

    @property
    def llm_model_auto_selected(self) -> bool:
        """True si el modelo activo proviene del default según OLLAMA_MODE."""
        if self.llm_provider != "ollama":
            return False
        if self.ollama_mode == "cloud":
            return self.llm_model == DEFAULT_LLM_MODEL_CLOUD
        return self.llm_model == DEFAULT_LLM_MODEL_LOCAL

    @property
    def allowed_schemas_list(self) -> list[str]:
        return [s.strip() for s in self.allowed_schemas.split(",") if s.strip()]

    @property
    def mtd_enabled_scales_list(self) -> list[int]:
        return parse_enabled_scales(self.mtd_enabled_scales)

    @property
    def default_scale(self) -> int:
        return parse_scale_from_database_url(self.database_url)

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def recommended_client_timeout_seconds(self) -> int:
        """Tiempo mínimo recomendado para clientes (plugin, web)."""
        attempts = self.max_llm_retries + 1
        return attempts * self.ollama_timeout_seconds + 60


settings = Settings()
