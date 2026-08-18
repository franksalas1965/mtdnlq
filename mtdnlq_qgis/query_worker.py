# -*- coding: utf-8 -*-
"""Worker en segundo plano para no bloquear la UI de QGIS."""
from qgis.PyQt.QtCore import QThread, pyqtSignal

from .api_client import MtdnlqApiError, MtdnlqClient

PHASE_STATUS_ES = {
    "preparing": "Preparando esquema…",
    "generating_sql": "Generando SQL (LLM)…",
    "executing_sql": "Ejecutando en PostGIS…",
    "formatting": "Formateando resultados…",
    "explaining": "Generando explicación…",
    "completed": "Finalizando…",
}


class QueryWorker(QThread):
    """Consulta síncrona (legacy) o asíncrona con polling según use_async."""

    finished_ok = pyqtSignal(dict)
    finished_error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        timeout_seconds: int,
        question: str,
        output_format: str,
        max_results: int,
        explain: bool,
        scale: int,
        use_async: bool = True,
        poll_interval_seconds: int = 3,
    ):
        super().__init__()
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.question = question
        self.output_format = output_format
        self.max_results = max_results
        self.explain = explain
        self.scale = scale
        self.use_async = use_async
        self.poll_interval_seconds = poll_interval_seconds

    def run(self):
        try:
            client = MtdnlqClient(self.base_url, self.timeout_seconds)
            if self.use_async:
                self._run_async(client)
            else:
                self._run_sync(client)
        except MtdnlqApiError as exc:
            self.finished_error.emit(self._format_api_error(exc))
        except Exception as exc:
            self.finished_error.emit(str(exc))

    def _run_sync(self, client: MtdnlqClient):
        self.status_update.emit("Consultando (modo síncrono)…")
        data = client.query(
            question=self.question,
            output_format=self.output_format,
            max_results=self.max_results,
            explain=self.explain,
            scale=self.scale,
        )
        self.finished_ok.emit(data)

    def _run_async(self, client: MtdnlqClient):
        self.status_update.emit("Encolando consulta…")
        submitted = client.submit_query_async(
            question=self.question,
            output_format=self.output_format,
            max_results=self.max_results,
            explain=self.explain,
            scale=self.scale,
        )
        job_id = submitted.get("job_id")
        if not job_id:
            raise MtdnlqApiError("El servidor no devolvió job_id")

        def on_status(status: dict):
            state = status.get("status")
            if state == "queued":
                pos = status.get("queue_position")
                if pos and pos > 1:
                    self.status_update.emit(f"En cola (posición {pos})…")
                else:
                    self.status_update.emit("En cola, esperando turno…")
            elif state == "running":
                phase = status.get("phase") or ""
                label = status.get("phase_label") or PHASE_STATUS_ES.get(phase)
                if label:
                    timing = status.get("timing_ms") or {}
                    db_ms = timing.get("executing_sql")
                    if phase == "executing_sql" and db_ms:
                        self.status_update.emit(f"{label} ({db_ms:.0f} ms)…")
                    else:
                        self.status_update.emit(f"{label}…")
                else:
                    self.status_update.emit("Procesando…")

        result = client.wait_for_job(
            job_id,
            poll_interval=float(self.poll_interval_seconds),
            deadline_seconds=self.timeout_seconds,
            on_status=on_status,
        )
        self.finished_ok.emit(result)

    @staticmethod
    def _format_api_error(exc: MtdnlqApiError) -> str:
        detail = ""
        if exc.payload:
            detail_obj = exc.payload.get("detail", exc.payload)
            if isinstance(detail_obj, dict) and detail_obj.get("detail"):
                detail = f" — {detail_obj['detail']}"
            err = exc.payload.get("error")
            if isinstance(err, dict) and err.get("detail"):
                detail = f" — {err['detail']}"
        code = f" (HTTP {exc.status_code})" if exc.status_code else ""
        return f"{exc}{detail}{code}"


class HealthWorker(QThread):
    finished_ok = pyqtSignal(dict)
    finished_error = pyqtSignal(str)

    def __init__(self, base_url: str, timeout_seconds: int = 10):
        super().__init__()
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def run(self):
        try:
            client = MtdnlqClient(self.base_url, self.timeout_seconds)
            self.finished_ok.emit(client.health())
        except Exception as exc:
            self.finished_error.emit(str(exc))
