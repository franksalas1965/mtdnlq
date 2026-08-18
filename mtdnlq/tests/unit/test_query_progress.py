"""Tests del tracker de fases."""
import time

from mtdnlq.services.query_progress import QueryProgressTracker


def test_progress_tracker_accumulates_phases():
    events: list[tuple[str, dict]] = []

    def on_phase(phase: str, data: dict) -> None:
        events.append((phase, dict(data)))

    tracker = QueryProgressTracker(on_phase=on_phase)
    tracker.enter("preparing")
    time.sleep(0.01)
    tracker.enter("generating_sql")
    tracker.set_sql("SELECT 1")
    time.sleep(0.01)
    tracker.enter("executing_sql")
    time.sleep(0.01)
    timing = tracker.finish()

    assert tracker.sql_generated == "SELECT 1"
    assert "preparing" in timing
    assert "generating_sql" in timing
    assert "executing_sql" in timing
    assert timing["total"] >= timing["preparing"]
    assert events[-1][0] == "completed"
    assert events[-1][1]["sql"] == "SELECT 1"
