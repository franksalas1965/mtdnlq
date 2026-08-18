# -*- coding: utf-8 -*-
"""Cliente HTTP para la API REST de MTD-NLQ (stdlib, sin dependencias externas)."""
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any


class MtdnlqApiError(Exception):
    """Error al comunicarse con MTD-NLQ."""

    def __init__(self, message: str, status_code: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class MtdnlqClient:
    """Cliente configurable para MTD-NLQ."""

    def __init__(self, base_url: str, timeout_seconds: int = 180):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        timeout: int | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        wait = timeout if timeout is not None else self.timeout_seconds
        try:
            with urllib.request.urlopen(req, timeout=wait) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            payload = {}
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                pass
            detail = payload.get("detail", payload)
            if isinstance(detail, dict):
                message = detail.get("message") or detail.get("error") or str(exc)
            else:
                message = str(detail) if detail else str(exc)
            raise MtdnlqApiError(message, status_code=exc.code, payload=payload) from exc
        except urllib.error.URLError as exc:
            if _is_timeout(exc.reason):
                raise MtdnlqApiError(
                    _timeout_message(wait, path)
                ) from exc
            raise MtdnlqApiError(
                f"No se pudo conectar con {self.base_url}: {exc.reason}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise MtdnlqApiError(
                _timeout_message(wait, path)
            ) from exc

    def health(self) -> dict:
        return self._request("GET", "/api/v1/health", timeout=min(60, self.timeout_seconds))

    def query(
        self,
        question: str,
        output_format: str = "geojson",
        max_results: int = 100,
        explain: bool = False,
        scale: int = 10000,
    ) -> dict:
        return self._request(
            "POST",
            "/api/v1/query",
            {
                "question": question,
                "output_format": output_format,
                "max_results": max_results,
                "explain": explain,
                "scale": scale,
            },
        )

    def submit_query_async(
        self,
        question: str,
        output_format: str = "geojson",
        max_results: int = 100,
        explain: bool = False,
        scale: int = 10000,
    ) -> dict:
        """Encola consulta (HTTP 202). Devuelve job_id y poll_url."""
        return self._request(
            "POST",
            "/api/v1/query/async",
            {
                "question": question,
                "output_format": output_format,
                "max_results": max_results,
                "explain": explain,
                "scale": scale,
            },
            timeout=30,
        )

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/api/v1/jobs/{job_id}", timeout=30)

    def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 3.0,
        deadline_seconds: int | None = None,
        on_status=None,
    ) -> dict:
        """
        Poll hasta completed/failed o timeout.
        on_status(status_dict) opcional para actualizar UI.
        """
        deadline = time.time() + (deadline_seconds or self.timeout_seconds)
        while time.time() < deadline:
            status = self.get_job(job_id)
            if on_status:
                on_status(status)
            state = status.get("status")
            if state == "completed":
                result = status.get("result")
                if result is None:
                    raise MtdnlqApiError("Job completado sin resultado")
                return result
            if state == "failed":
                err = status.get("error") or {}
                msg = err.get("message") or err.get("error") or "Consulta fallida"
                detail = err.get("detail")
                if detail:
                    msg = f"{msg} — {detail}"
                raise MtdnlqApiError(msg, payload=status)
            time.sleep(poll_interval)
        raise MtdnlqApiError(
            f"Tiempo de espera agotado ({deadline_seconds or self.timeout_seconds}s) "
            f"esperando el job {job_id}. El servidor sigue procesando; "
            "puede consultar el job_id más tarde."
        )


def _is_timeout(reason) -> bool:
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    text = str(reason).lower()
    return "timed out" in text or "timeout" in text


def _timeout_message(timeout_seconds: int, path: str) -> str:
    if path.endswith("/health"):
        return (
            f"MTD-NLQ no respondió en {timeout_seconds}s. "
            "Compruebe que el servicio esté en ejecución (uvicorn :8001). "
            "Si hay otra consulta NL en curso, espere y reintente."
        )
    if "/jobs/" in path:
        return f"No se pudo consultar el estado del job en {timeout_seconds}s."
    if path.endswith("/async"):
        return f"No se pudo encolar la consulta en {timeout_seconds}s."
    return (
        f"Tiempo de espera agotado ({timeout_seconds}s). "
        "Las consultas con LLM local pueden tardar varios minutos "
        f"(hasta ~{timeout_seconds // 60} min). "
        "Use modo asíncrono o aumente «Tiempo de espera» en Configuración."
    )
