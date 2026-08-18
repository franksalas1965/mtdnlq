"""Configuración central del servicio GeoNLQ usando pydantic-settings."""
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Base de datos
    database_url: str = "postgresql+psycopg2://geonlq_reader:password@localhost:5432/geonlq"

    # Proveedor LLM
    llm_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    llm_model: str = "gpt-4o"

    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # CORS — orígenes permitidos separados por coma
    # En desarrollo: "*" permite cualquier origen
    # En producción: especificar el dominio del cliente web
    cors_origins: str = "*"

    # Caché de esquema
    schema_cache_ttl: int = 300  # segundos

    # Límites
    max_results: int = 100
    sql_timeout: int = 30  # segundos
    max_llm_retries: int = 2
    ollama_timeout_seconds: int = 180

    # Seguridad
    allowed_schemas: str = "public"  # separados por coma

    # Logging
    log_level: str = "INFO"

    # API
    api_title: str = "GeoNLQ — Consultas en Lenguaje Natural sobre PostGIS"
    api_version: str = "1.0.0"
    debug: bool = False

    @property
    def allowed_schemas_list(self) -> list[str]:
        return [s.strip() for s in self.allowed_schemas.split(",")]

    @property
    def cors_origins_list(self) -> list[str]:
        """Convierte la cadena de orígenes CORS en lista."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
