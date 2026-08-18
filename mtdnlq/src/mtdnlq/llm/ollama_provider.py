"""Proveedor LLM: Ollama local o Ollama Cloud (ollama.com)."""
import re
import httpx
from .base import LLMProvider
from .ollama_config import (
    build_ollama_headers,
    build_ollama_options,
    cloud_api_key_configured,
    resolve_ollama_base_url,
)
from ..core.config import settings
from ..core.exceptions import LLMUnavailableError, SQLGenerationError

SYSTEM_PROMPT = (
    "Eres un experto en SQL geoespacial y PostGIS. Traduce preguntas en lenguaje natural "
    "a SQL válido para PostgreSQL+PostGIS. Solo SELECT. Retorna solo el SQL, sin markdown."
)


class OllamaProvider(LLMProvider):
    """Ollama local (CPU/GPU) u Ollama Cloud vía https://ollama.com/api."""

    def __init__(self):
        self.base_url = resolve_ollama_base_url()
        self.model = settings.llm_model
        self._headers = build_ollama_headers()

    def _ensure_available(self) -> None:
        if settings.ollama_mode == "cloud" and not cloud_api_key_configured():
            raise LLMUnavailableError(
                "ollama",
                detail="Configure OLLAMA_API_KEY en .env (https://ollama.com/settings/keys)",
            )

    async def generate_sql(self, prompt: str) -> str:
        self._ensure_available()
        timeout = float(settings.ollama_timeout_seconds)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": build_ollama_options(),
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                data = response.json()
                sql = data["message"]["content"].strip()
                return self._clean_sql(sql)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise LLMUnavailableError(
                    "ollama",
                    detail="API key inválida (OLLAMA_API_KEY)",
                ) from e
            raise SQLGenerationError(
                f"Ollama HTTP {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.ConnectError as e:
            mode = settings.ollama_mode
            raise LLMUnavailableError(f"ollama {mode}") from e
        except Exception as e:
            raise SQLGenerationError(str(e)) from e

    async def health_check(self) -> bool:
        if settings.ollama_mode == "cloud" and not cloud_api_key_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.base_url}/api/tags",
                    headers=self._headers,
                )
                return r.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _clean_sql(text: str) -> str:
        text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()
        if re.match(r"^\s*(WITH\s|SELECT\s)", text, re.IGNORECASE):
            return text.rstrip(";")
        match = re.search(r"(?is)\b((?:WITH\b.+?\bSELECT\b)|SELECT\b.+)$", text)
        if match:
            return match.group(1).strip().rstrip(";")
        return text
