# -*- coding: utf-8 -*-
"""Persistencia de configuración del plugin (QSettings)."""
from qgis.PyQt.QtCore import QSettings


ORG = "MTD-NLQ"
APP = "mtdnlq_qgis"

# max_results=0 en plugin/API = todos los registros (sin LIMIT automático)
MAX_RESULTS_UNLIMITED = 0

DEFAULTS = {
    "api_base_url": "http://localhost:8001",
    "mtd_scale": 10000,
    "auto_url_by_scale": False,
    "timeout_seconds": 600,
    "max_results": 100,
    "output_format": "geojson",
    "explain_by_default": False,
    "show_sql_panel": True,
    "show_metadata_bar": True,
    "map_crs": "EPSG:4267",
    "highlight_color": "#2563eb",
    "highlight_width": 2,
    "zoom_buffer_percent": 15,
    "remove_previous_highlight": True,
    "dock_visible_on_start": True,
    "use_async_queries": True,
    "poll_interval_seconds": 3,
    "history_max_entries": 150,
}


class SettingsManager:
    """Lee y escribe ajustes del plugin en el perfil de QGIS del usuario."""

    def __init__(self):
        self._settings = QSettings(ORG, APP)

    def get(self, key: str):
        default = DEFAULTS.get(key)
        value = self._settings.value(key, default)
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value) if value is not None else default
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        if value is None:
            return default
        return value

    def set(self, key: str, value) -> None:
        self._settings.setValue(key, value)

    def save_all(self, values: dict) -> None:
        for key, value in values.items():
            if key in DEFAULTS:
                self.set(key, value)

    def as_dict(self) -> dict:
        return {key: self.get(key) for key in DEFAULTS}
