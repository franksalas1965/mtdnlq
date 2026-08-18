"""Seguimiento de fases y tiempos en el pipeline NL → SQL → PostGIS."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

QueryPhase = Literal[
    "preparing",
    "generating_sql",
    "executing_sql",
    "formatting",
    "explaining",
    "completed",
]

PhaseCallback = Callable[[QueryPhase, dict[str, Any]], None]

PHASE_LABELS_ES: dict[str, str] = {
    "preparing": "Preparando esquema",
    "generating_sql": "Generando SQL (LLM)",
    "executing_sql": "Ejecutando en PostGIS",
    "formatting": "Formateando resultados",
    "explaining": "Generando explicación",
    "completed": "Completado",
}


@dataclass
class QueryProgressTracker:
    """Acumula tiempos por fase y notifica cambios a clientes async."""

    on_phase: PhaseCallback | None = None
    timing_ms: dict[str, float] = field(default_factory=dict)
    sql_generated: str = ""
    _phase_start: float = field(default_factory=time.perf_counter, repr=False)
    _current_phase: str = field(default="", repr=False)

    def enter(self, phase: QueryPhase, **extra: Any) -> None:
        if self._current_phase:
            elapsed = (time.perf_counter() - self._phase_start) * 1000
            self.timing_ms[self._current_phase] = round(
                self.timing_ms.get(self._current_phase, 0) + elapsed, 2
            )
        self._current_phase = phase
        self._phase_start = time.perf_counter()
        self._emit(phase, extra)

    def set_sql(self, sql: str) -> None:
        self.sql_generated = sql
        if self._current_phase:
            self._emit(self._current_phase)

    def finish(self) -> dict[str, float]:
        self.enter("completed")
        phase_total = round(
            sum(
                ms
                for name, ms in self.timing_ms.items()
                if name not in ("total", "completed")
            ),
            2,
        )
        self.timing_ms["total"] = phase_total
        return dict(self.timing_ms)

    def _emit(self, phase: QueryPhase, extra: dict[str, Any] | None = None) -> None:
        if not self.on_phase:
            return
        payload: dict[str, Any] = {
            "phase": phase,
            "phase_label": PHASE_LABELS_ES.get(phase, phase),
            "sql": self.sql_generated or None,
            "timing_ms": dict(self.timing_ms),
        }
        if extra:
            payload.update(extra)
        self.on_phase(phase, payload)
