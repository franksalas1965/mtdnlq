"""Proveedor LLM: Anthropic Claude."""
import re
import anthropic
from .base import LLMProvider
from ..core.config import settings
from ..core.exceptions import LLMUnavailableError, SQLGenerationError

SYSTEM_PROMPT = (
    "Eres un experto en SQL geoespacial y PostGIS. Tu única tarea es traducir "
    "preguntas en lenguaje natural a consultas SQL válidas para PostgreSQL con PostGIS. "
    "REGLAS: Solo SELECT. Usa funciones PostGIS estándar. SRID EPSG:4326. "
    "Retorna SOLO el SQL sin explicaciones ni markdown."
)


class AnthropicProvider(LLMProvider):
    """Implementa LLMProvider usando la API de Anthropic."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.llm_model

    async def generate_sql(self, prompt: str) -> str:
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            sql = message.content[0].text.strip()
            return self._clean_sql(sql)
        except anthropic.APIConnectionError as e:
            raise LLMUnavailableError("anthropic") from e
        except Exception as e:
            raise SQLGenerationError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            await self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _clean_sql(text: str) -> str:
        text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*", "", text)
        return text.strip()
