# -*- coding: utf-8 -*-
"""Aplica simbología MTD (QML) a capas QGIS."""
from __future__ import annotations

from typing import Any

from qgis.core import (
    Qgis,
    QgsDataSourceUri,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeatureRenderer,
    QgsMapLayer,
    QgsMessageLog,
    QgsProject,
    QgsReadWriteContext,
    QgsRenderContext,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtXml import QDomDocument

LOG_TAG = "MTD-NLQ"


def _log(message: str, level=Qgis.Warning) -> None:
    QgsMessageLog.logMessage(message, LOG_TAG, level)


def find_project_layer(schema: str, table: str) -> QgsVectorLayer | None:
    """Capa PostGIS ya cargada en el proyecto con el mismo schema.tabla."""
    schema_l = schema.lower()
    table_l = table.lower()

    for layer in QgsProject.instance().mapLayers().values():
        if layer.type() != QgsMapLayer.VectorLayer:
            continue
        if not isinstance(layer, QgsVectorLayer):
            continue
        if layer.providerType() != "postgres":
            continue

        uri = QgsDataSourceUri(layer.source())
        if uri.schema().lower() == schema_l and uri.table().lower() == table_l:
            return layer
    return None


def load_renderer_from_qml(style_qml: str) -> QgsFeatureRenderer | None:
    """Carga el renderer-v2 del QML de layer_styles."""
    doc = QDomDocument("qgis")
    if not doc.setContent(style_qml):
        _log("QML de estilo no válido (setContent falló)")
        return None

    node = doc.documentElement().firstChildElement("renderer-v2")
    if node.isNull():
        _log("QML sin nodo renderer-v2")
        return None

    renderer = QgsFeatureRenderer.load(node, QgsReadWriteContext())
    if renderer is None:
        _log("QgsFeatureRenderer.load devolvió None")
    return renderer


def _render_context_for_layer(layer: QgsVectorLayer, feature) -> QgsRenderContext:
    ctx = QgsRenderContext()
    expr_ctx = QgsExpressionContext()
    expr_ctx.appendScope(QgsExpressionContextUtils.layerScope(layer))
    if feature is not None and feature.isValid():
        expr_ctx.setFeature(feature)
    ctx.setExpressionContext(expr_ctx)
    return ctx


def _first_feature(layer: QgsVectorLayer):
    for feat in layer.getFeatures():
        return feat
    return None


def apply_qml_to_layer(
    layer: QgsVectorLayer,
    style_qml: str,
    feature_props: dict[str, Any] | None = None,
) -> bool:
    if not style_qml or not style_qml.strip():
        return False

    renderer = load_renderer_from_qml(style_qml)
    if renderer is None:
        doc = QDomDocument("qgis")
        if not doc.setContent(style_qml):
            return False
        success, errors = layer.importNamedStyle(doc)
        if not success and errors:
            _log(f"importNamedStyle: {'; '.join(errors[:3])}")
        if success:
            layer.triggerRepaint()
        return success

    feat = _first_feature(layer)
    if feat is None or not feat.isValid():
        layer.setRenderer(renderer.clone())
        layer.triggerRepaint()
        return True

    if isinstance(renderer, QgsRuleBasedRenderer):
        ctx = _render_context_for_layer(layer, feat)
        symbol = renderer.symbolForFeature(feat, ctx)
        if symbol is not None:
            layer.setRenderer(QgsSingleSymbolRenderer(symbol.clone()))
            layer.triggerRepaint()
            geocodigo = (feature_props or {}).get("geocodigo") or feat.attribute("geocodigo")
            _log(
                f"Simbología MTD aplicada (geocodigo={geocodigo})",
                Qgis.Info,
            )
            return True
        geocodigo = (feature_props or {}).get("geocodigo") or feat.attribute("geocodigo")
        _log(
            f"Ninguna regla coincidió para geocodigo={geocodigo!r}; "
            "se usa RuleRenderer completo",
            Qgis.Warning,
        )

    layer.setRenderer(renderer.clone())
    layer.triggerRepaint()
    return True


def apply_mtd_style(
    layer: QgsVectorLayer,
    style_qml: str | None,
    source_schema: str | None = None,
    source_table: str | None = None,
    prefer_project_layer: bool = True,
    feature_props: dict[str, Any] | None = None,
) -> bool:
    """
    Aplica simbología MTD a una capa en memoria u OGR.

    Prioridad: capa PostGIS del proyecto → QML del backend.
    """
    if prefer_project_layer and source_schema and source_table:
        project_layer = find_project_layer(source_schema, source_table)
        if project_layer and project_layer.renderer() is not None:
            layer.setRenderer(project_layer.renderer().clone())
            layer.triggerRepaint()
            _log(f"Simbología copiada de capa en proyecto: {source_schema}.{source_table}", Qgis.Info)
            return True

    if not style_qml:
        _log("Sin style_qml del backend para aplicar simbología")
        return False

    return apply_qml_to_layer(layer, style_qml, feature_props=feature_props)
