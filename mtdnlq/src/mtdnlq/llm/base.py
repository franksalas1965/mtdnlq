"""Interfaz abstracta para proveedores LLM."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Contrato que deben cumplir todos los proveedores LLM."""

    @abstractmethod
    async def generate_sql(self, prompt: str) -> str:
        """
        Recibe un prompt completo y retorna el SQL generado.

        Args:
            prompt: Prompt construido por PromptBuilder con esquema,
                    ejemplos y la pregunta del usuario.

        Returns:
            SQL geoespacial válido (solo SELECT).

        Raises:
            LLMUnavailableError: Si el proveedor no responde.
            SQLGenerationError: Si el LLM retorna texto que no es SQL.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verifica que el proveedor está accesible.

        Returns:
            True si el proveedor responde correctamente.
        """
