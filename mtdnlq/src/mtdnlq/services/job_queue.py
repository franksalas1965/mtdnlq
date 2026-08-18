"""Cola de trabajos asíncrona para consultas NL (multi-cliente / multi-escala)."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from ..api.schemas import QueryRequest, QueryResponse
from ..core.config import settings
from ..core.exceptions import (
    DatabaseError,
    LLMUnavailableError,
    MTDNLQException,
    QueryTimeoutError,
    SQLForbiddenError,
    SQLGenerationError,
)
from ..services.query_service import process_query

logger = logging.getLogger(__name__)

JobState = Literal["queued", "running", "completed", "failed"]


@dataclass
class JobRecord:
    id: str
    status: JobState
    request: QueryRequest
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    phase: str | None = None
    phase_label: str | None = None
    sql_generated: str | None = None
    timing_ms: dict[str, float] = field(default_factory=dict)
    result: QueryResponse | None = None
    error: dict[str, Any] | None = None

    def to_public_dict(self) -> dict[str, Any]:
        queued_ahead = job_queue.count_queued_before(self.id) if self.status == "queued" else 0
        payload: dict[str, Any] = {
            "job_id": self.id,
            "status": self.status,
            "question": self.request.question,
            "scale": self.request.scale,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "queue_position": queued_ahead + 1 if self.status == "queued" else None,
            "poll_url": f"/api/v1/jobs/{self.id}",
            "phase": self.phase,
            "phase_label": self.phase_label,
            "sql_generated": self.sql_generated,
            "timing_ms": dict(self.timing_ms),
        }
        if self.status == "completed" and self.result is not None:
            payload["result"] = self.result.model_dump()
        if self.status == "failed" and self.error:
            payload["error"] = self.error
        return payload


def _exception_to_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, SQLGenerationError):
        return {
            "error": exc.code,
            "message": exc.message,
            "detail": exc.detail or None,
        }
    if isinstance(exc, MTDNLQException):
        detail = getattr(exc, "detail", None)
        return {"error": exc.code, "message": exc.message, "detail": detail}
    return {"error": "internal_error", "message": str(exc)}


class JobQueue:
    """Gestiona jobs en memoria con límite de concurrencia LLM (semáforo)."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_llm_jobs)

    def _active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))

    def _purge_old_jobs(self) -> None:
        cutoff = time.time() - settings.job_retention_seconds
        to_delete = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in ("completed", "failed") and (job.completed_at or 0) < cutoff
        ]
        for job_id in to_delete:
            del self._jobs[job_id]

    async def submit(self, request: QueryRequest) -> JobRecord:
        async with self._lock:
            self._purge_old_jobs()
            if self._active_count() >= settings.max_queued_jobs:
                raise RuntimeError(
                    f"Cola llena ({settings.max_queued_jobs} trabajos). "
                    "Intente de nuevo en unos minutos."
                )
            job_id = str(uuid.uuid4())
            job = JobRecord(id=job_id, status="queued", request=request)
            self._jobs[job_id] = job

        asyncio.create_task(self._run_job(job_id))
        logger.info("Job encolado %s escala=%s", job_id, request.scale)
        return job

    async def _run_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return

        await self._semaphore.acquire()
        job.status = "running"
        job.started_at = time.time()
        logger.info("Job en ejecución %s", job_id)

        try:
            def on_phase(_phase: str, data: dict[str, Any]) -> None:
                job.phase = data.get("phase", _phase)
                job.phase_label = data.get("phase_label")
                if data.get("sql"):
                    job.sql_generated = data["sql"]
                if data.get("timing_ms"):
                    job.timing_ms = dict(data["timing_ms"])

            result = await process_query(job.request, on_phase=on_phase)
            job.result = result
            job.status = "completed"
            logger.info("Job completado %s en %.0f ms", job_id, result.time_ms)
        except Exception as exc:
            job.error = _exception_to_error(exc)
            job.status = "failed"
            logger.warning("Job fallido %s: %s", job_id, job.error.get("message", exc))
        finally:
            job.completed_at = time.time()
            self._semaphore.release()

    def get(self, job_id: str) -> JobRecord | None:
        self._purge_old_jobs()
        return self._jobs.get(job_id)

    def count_queued_before(self, job_id: str) -> int:
        job = self._jobs.get(job_id)
        if not job or job.status != "queued":
            return 0
        return sum(
            1
            for other in self._jobs.values()
            if other.status == "queued" and other.created_at < job.created_at
        )

    def stats(self) -> dict[str, int]:
        queued = sum(1 for j in self._jobs.values() if j.status == "queued")
        running = sum(1 for j in self._jobs.values() if j.status == "running")
        completed = sum(1 for j in self._jobs.values() if j.status == "completed")
        failed = sum(1 for j in self._jobs.values() if j.status == "failed")
        return {
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed,
            "max_concurrent_llm_jobs": settings.max_concurrent_llm_jobs,
            "max_queued_jobs": settings.max_queued_jobs,
        }


job_queue = JobQueue()
