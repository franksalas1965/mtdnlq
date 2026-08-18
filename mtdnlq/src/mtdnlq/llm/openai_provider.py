"""Proveedor LLM: OpenAI GPT."""
import re
from openai import AsyncOpenAI, APIConnectionError
from .base import LLMProvider
from ..core.config import settings
from ..core.exceptions import LLMUnavailableError, SQLGenerationError


class OpenAIProvider(LLMProvider):
    """Implementa LLMProvider usando la API de OpenAI."""

    SYSTEM_PROMPT = (
        "Eres un experto en SQL geoespacial y PostGIS. Tu única tarea es traducir "
        "preguntas en lenguaje natural a consultas SQL válidas para PostgreSQL con PostGIS. "
        "REGLAS ESTRICTAS:\n"
        "1. SIEMPRE genera solo SELECT. NUNCA INSERT, UPDATE, DELETE, DROP, CREATE, ALTER.\n"
        "2. Usa funciones PostGIS estándar: ST_Intersects, ST_Within, ST_Buffer, ST_DWithin, "
        "ST_Length, ST_Distance, ST_AsGeoJSON.\n"
        "3. El SRID de trabajo es EPSG:4326 (WGS84).\n"
        "4. Para distancias en metros, convierte geometría a geography: geom::geography.\n"
        "5. Usa ILIKE para búsquedas de texto (insensible a mayúsculas).\n"
        "6. Retorna SOLO el SQL, sin explicaciones, sin markdown, sin bloques de código.\n"
        "7. Incluye siempre ST_AsGeoJSON(geom)::json AS geometry cuando haya columna geom.\n"
        "8. Añade LIMIT si no se especifica (máximo 100 filas)."
    )

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model

    async def generate_sql(self, prompt: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,  # Determinismo máximo para SQL
                max_tokens=1024,
            )
            sql = response.choices[0].message.content.strip()
            return self._clean_sql(sql)
        except APIConnectionError as e:
            raise LLMUnavailableError("openai") from e
        except Exception as e:
            raise SQLGenerationError(str(e)) from e

    async def health_check(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    @staticmethod
    def _clean_sql(text: str) -> str:
        """Elimina bloques markdown si el LLM los incluyó."""
        text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*", "", text)
        return text.strip()
