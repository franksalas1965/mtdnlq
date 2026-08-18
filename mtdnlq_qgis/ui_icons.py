# -*- coding: utf-8 -*-
"""Iconos del tema QGIS con fallback opcional."""
from qgis.core import QgsApplication


def theme_icon(primary: str, fallback: str = ""):
    """Devuelve un icono del tema QGIS; prueba fallback si el principal no existe."""
    icon = QgsApplication.getThemeIcon(primary)
    if icon.isNull() and fallback:
        icon = QgsApplication.getThemeIcon(fallback)
    return icon
