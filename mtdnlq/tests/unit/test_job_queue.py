"""Tests de la cola de jobs asíncrona."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mtdnlq.api.schemas import QueryRequest, QueryResponse
from mtdnlq.services.job_queue import JobQueue


@pytest.mark.asyncio
async def test_job_queue_runs_and_completes():
    queue = JobQueue()
    request = QueryRequest(question="Cuantos rios hay", scale=10000)
    fake_result = QueryResponse(
        question=request.question,
        sql="SELECT 1",
        results=[],
        total=0,
        time_ms=1.0,
        timing_ms={"generating_sql": 0.5, "executing_sql": 0.3, "total": 1.0},
        scale=10000,
        database="mtd10",
    )

    with patch("mtdnlq.services.job_queue.process_query", new=AsyncMock(return_value=fake_result)):
        job = await queue.submit(request)
        await asyncio.sleep(0.1)
        stored = queue.get(job.id)
        assert stored is not None
        assert stored.status == "completed"
        assert stored.result.total == 0


@pytest.mark.asyncio
async def test_job_queue_records_failure():
    queue = JobQueue()
    request = QueryRequest(question="Consulta invalida", scale=10000)

    with patch(
        "mtdnlq.services.job_queue.process_query",
        new=AsyncMock(side_effect=RuntimeError("fallo LLM")),
    ):
        job = await queue.submit(request)
        await asyncio.sleep(0.1)
        stored = queue.get(job.id)
        assert stored.status == "failed"
        assert stored.error["error"] == "internal_error"
