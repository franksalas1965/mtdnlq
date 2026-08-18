"""Proveedor LLM: Ollama (modelos locales)."""
import re
import httpx
from .base import LLMProvider
from ..core.config import settings
from ..core.exceptions import LLMUnavailableError, SQLGenerationError

SYSTEM_PROMPT = (
    "Eres un experto en SQL geoespacial y PostGIS. Traduce preguntas en lenguaje natural "
    "a SQL válido para PostgreSQL+PostGIS. Solo SELECT. Retorna solo el SQL, sin markdown."
)


class OllamaProvider(LLMProvider):
    """Implementa LLMProvider usando un servidor Ollama local."""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.llm_model

    async def generate_sql(self, prompt: str) -> str:
        timeout = float(settings.ollama_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "options": {"temperature": 0},
                    },
                )
                response.raise_for_status()
                data = response.json()
                sql = data["message"]["content"].strip()
                return self._clean_sql(sql)
        except httpx.ConnectError as e:
            raise LLMUnavailableError("ollama") from e
        except Exception as e:
            raise SQLGenerationError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/api/tags")
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
        # Respuesta con texto previo: extraer desde WITH o SELECT
        match = re.search(r"(?is)\b((?:WITH\b.+?\bSELECT\b)|SELECT\b.+)$", text)
        if match:
            return match.group(1).strip().rstrip(";")
        return text
