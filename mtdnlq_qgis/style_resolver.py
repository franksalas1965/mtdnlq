# -*- coding: utf-8 -*-
"""Resuelve style_qml vía respuesta del backend o GET /layer-style."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qgis.core import Qgis, QgsMessageLog

from .api_client import MtdnlqClient
from .sql_source_parser import extract_geometry_source_table

if TYPE_CHECKING:
    from .settings_manager import SettingsManager


class StyleResolver:
    """Obtiene QML de simbología sin conectar el plugin a PostgreSQL."""

    def __init__(self, settings: "SettingsManager"):
        self.settings = settings

    def resolve(
        self,
        scale: int,
        source_schema: str | None = None,
        source_table: str | None = None,
        sql: str | None = None,
        style_qml: str | None = None,
    ) -> str | None:
        if not self.settings.get("use_mtd_layer_styles"):
            return None

        if style_qml and style_qml.strip():
            return style_qml

        schema, table = source_schema, source_table
        if (not schema or not table) and sql:
            parsed = extract_geometry_source_table(sql)
            if parsed:
                schema, table = parsed

        if not schema or not table:
            return None

        try:
            client = MtdnlqClient(
                self.settings.get("api_base_url"),
                timeout_seconds=min(60, int(self.settings.get("timeout_seconds") or 60)),
            )
            mode = self.settings.get("style_mode") or "i"
            data = client.get_layer_style(schema, table, scale=scale, style_mode=mode)
            qml = data.get("style_qml") or None
            if qml:
                QgsMessageLog.logMessage(
                    f"Estilo cargado: {schema}.{table} ({data.get('style_name') or mode})",
                    "MTD-NLQ",
                    Qgis.Info,
                )
            else:
                QgsMessageLog.logMessage(
                    f"Backend sin estilo para {schema}.{table} (found={data.get('found')})",
                    "MTD-NLQ",
                    Qgis.Warning,
                )
            return qml
        except Exception as exc:
            QgsMessageLog.logMessage(
                f"Error al obtener estilo del backend: {exc}",
                "MTD-NLQ",
                Qgis.Warning,
            )
            return None
