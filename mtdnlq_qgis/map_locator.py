# -*- coding: utf-8 -*-
"""Localización puntual de un resultado geográfico en el mapa de QGIS."""
import json
import os
from typing import TYPE_CHECKING

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsJsonUtils,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsSymbol,
    QgsSingleSymbolRenderer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

from .mtd_fields import stringify_mtd_properties
from .mtd_style_loader import apply_mtd_style
from .style_resolver import StyleResolver

if TYPE_CHECKING:
    from .settings_manager import SettingsManager


HIGHLIGHT_LAYER_PREFIX = "MTD-NLQ — localizar"
HISTORY_LAYER_PREFIX = "MTD-NLQ — historial"

BASE_LAYER_REQUIRED_MSG = (
    "Para localizar un resultado en el mapa debe haber al menos una capa cargada "
    "en el proyecto (OSM, WMS, shapefile, GeoPackage, etc.).\n\n"
    "Añada una capa base en QGIS e inténtelo de nuevo."
)


class MapLocator:
    """Crea una capa temporal con un solo feature y hace zoom."""

    def __init__(self, iface, settings_manager: "SettingsManager"):
        self.iface = iface
        self.settings = settings_manager
        self._style_resolver = StyleResolver(settings_manager)
        self._layer_counter = 0

    def _remove_previous_layers(self) -> None:
        if not self.settings.get("remove_previous_highlight"):
            return
        project = QgsProject.instance()
        to_remove = [
            layer.id()
            for layer in project.mapLayers().values()
            if layer.name().startswith(HIGHLIGHT_LAYER_PREFIX)
        ]
        if to_remove:
            project.removeMapLayers(to_remove)

    def has_base_layers(self) -> bool:
        """True si el proyecto tiene al menos una capa que no sea el resaltado MTD-NLQ."""
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if layer.name().startswith(HIGHLIGHT_LAYER_PREFIX):
                continue
            if layer.isValid():
                return True
        return False

    def _layer_type_for_geometry(self, geometry: QgsGeometry) -> str:
        wkb = geometry.wkbType()
        gtype = QgsWkbTypes.geometryType(wkb)
        if gtype == QgsWkbTypes.PointGeometry:
            return "MultiPoint" if QgsWkbTypes.isMultiType(wkb) else "Point"
        if gtype == QgsWkbTypes.LineGeometry:
            return "MultiLineString" if QgsWkbTypes.isMultiType(wkb) else "LineString"
        return "MultiPolygon" if QgsWkbTypes.isMultiType(wkb) else "Polygon"

    def _style_layer(self, layer: QgsVectorLayer) -> None:
        color = QColor(self.settings.get("highlight_color"))
        width = self.settings.get("highlight_width")
        geom_type = layer.geometryType()

        if geom_type == QgsWkbTypes.PointGeometry:
            symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
            symbol.setColor(color)
            symbol.setSize(4)
        elif geom_type == QgsWkbTypes.LineGeometry:
            symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
            symbol.setColor(color)
            symbol.setWidth(width)
        else:
            symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
            symbol.setColor(QColor(color.red(), color.green(), color.blue(), 80))
            symbol.symbolLayer(0).setStrokeColor(color)
            symbol.symbolLayer(0).setStrokeWidth(width)

        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

    def _apply_layer_style(
        self,
        layer: QgsVectorLayer,
        scale: int,
        source_schema: str | None = None,
        source_table: str | None = None,
        sql: str | None = None,
        style_qml: str | None = None,
        feature_props: dict | None = None,
    ) -> bool:
        qml = self._style_resolver.resolve(
            scale=scale,
            source_schema=source_schema,
            source_table=source_table,
            sql=sql,
            style_qml=style_qml,
        )

        if apply_mtd_style(
            layer,
            qml,
            source_schema,
            source_table,
            feature_props=feature_props,
        ):
            return True

        if self.settings.get("fallback_highlight"):
            self._style_layer(layer)
        return False

    def _source_crs(self) -> QgsCoordinateReferenceSystem:
        """CRS de las geometrías MTD (NAD27 por defecto)."""
        authid = (self.settings.get("map_crs") or "EPSG:4267").strip()
        crs = QgsCoordinateReferenceSystem(authid)
        if crs.isValid():
            return crs
        return QgsCoordinateReferenceSystem("EPSG:4267")

    def _min_buffer_map_units(self, crs: QgsCoordinateReferenceSystem, extent: QgsRectangle) -> float:
        """Margen mínimo de zoom en unidades del CRS destino (mapa)."""
        if crs.isGeographic():
            return max(extent.width() * 0.05, extent.height() * 0.05, 0.002)
        return max(extent.width() * 0.05, extent.height() * 0.05, 100.0)

    def _extent_for_canvas(self, layer: QgsVectorLayer) -> QgsRectangle | None:
        """Transforma la extensión de la capa al CRS del lienzo (p. ej. OSM en EPSG:3857)."""
        canvas = self.iface.mapCanvas()
        canvas_crs = canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()
        extent = layer.extent()
        if extent.isNull() or extent.isEmpty():
            return None

        if layer_crs.isValid() and canvas_crs.isValid() and layer_crs != canvas_crs:
            transform = QgsCoordinateTransform(
                layer_crs,
                canvas_crs,
                QgsProject.instance().transformContext(),
            )
            try:
                extent = transform.transformBoundingBox(extent)
            except Exception:
                return None

        if extent.width() <= 0 or extent.height() <= 0:
            extent.grow(self._min_buffer_map_units(canvas_crs, extent))

        buffer_pct = self.settings.get("zoom_buffer_percent")
        if buffer_pct > 0:
            x_buffer = extent.width() * buffer_pct / 100.0
            y_buffer = extent.height() * buffer_pct / 100.0
            min_buf = self._min_buffer_map_units(canvas_crs, extent)
            extent.grow(max(x_buffer, y_buffer, min_buf))

        return extent

    def _build_layer(self, feature_dict: dict, layer_name: str) -> QgsVectorLayer | None:
        geometry_data = feature_dict.get("geometry")
        if not geometry_data:
            return None

        geometry = QgsJsonUtils.geometryFromGeoJson(json.dumps(geometry_data))
        if geometry.isNull() or geometry.isEmpty():
            return None

        source_crs = self._source_crs()
        geom_type = self._layer_type_for_geometry(geometry)
        layer = QgsVectorLayer(
            f"{geom_type}?crs={source_crs.authid()}",
            layer_name,
            "memory",
        )
        if not layer.isValid():
            return None
        layer.setCrs(source_crs)

        props = stringify_mtd_properties(feature_dict.get("properties") or {})
        fields = QgsFields()
        for key in props:
            fields.append(QgsField(str(key), QMetaType.Type.QString))

        layer.dataProvider().addAttributes(fields.toList())
        layer.updateFields()

        feat = QgsFeature(fields)
        feat.setGeometry(geometry)
        feat.setAttributes([str(props.get(f.name(), "")) for f in fields])
        layer.dataProvider().addFeature(feat)
        layer.updateExtents()
        return layer

    def locate_feature(
        self,
        feature_dict: dict,
        label: str = "",
        scale: int = 10000,
        source_schema: str | None = None,
        source_table: str | None = None,
        sql: str | None = None,
        style_qml: str | None = None,
    ) -> bool:
        """Muestra un único GeoJSON Feature en el mapa y hace zoom."""
        if not self.has_base_layers():
            QMessageBox.warning(
                self.iface.mainWindow(),
                "MTD-NLQ — Localizar en mapa",
                BASE_LAYER_REQUIRED_MSG,
            )
            return False

        self._remove_previous_layers()
        self._layer_counter += 1
        layer_name = f"{HIGHLIGHT_LAYER_PREFIX} #{self._layer_counter}"
        if label:
            layer_name = f"{HIGHLIGHT_LAYER_PREFIX}: {label[:40]}"

        layer = self._build_layer(feature_dict, layer_name)
        if not layer:
            return False

        props = feature_dict.get("properties") or {}
        self._apply_layer_style(
            layer,
            scale=scale,
            source_schema=source_schema,
            source_table=source_table,
            sql=sql,
            style_qml=style_qml,
            feature_props=props,
        )
        QgsProject.instance().addMapLayer(layer)

        extent = self._extent_for_canvas(layer)
        if extent is None:
            return False

        canvas = self.iface.mapCanvas()
        canvas.setExtent(extent)
        canvas.refresh()
        QApplication.processEvents()
        return True

    def load_geojson_file(
        self,
        path: str,
        label: str = "",
        scale: int = 10000,
        source_schema: str | None = None,
        source_table: str | None = None,
        sql: str | None = None,
        style_qml: str | None = None,
    ) -> bool:
        """Carga un GeoJSON guardado (cápsula de historial) como capa OGR."""
        if not os.path.isfile(path):
            return False
        if not self.has_base_layers():
            QMessageBox.warning(
                self.iface.mainWindow(),
                "MTD-NLQ — Capa en mapa",
                BASE_LAYER_REQUIRED_MSG,
            )
            return False

        self._layer_counter += 1
        short = (label or "consulta")[:40]
        layer_name = f"{HISTORY_LAYER_PREFIX}: {short}"

        layer = QgsVectorLayer(path, layer_name, "ogr")
        if not layer.isValid():
            return False

        source_crs = self._source_crs()
        if not layer.crs().isValid():
            layer.setCrs(source_crs)

        self._apply_layer_style(
            layer,
            scale=scale,
            source_schema=source_schema,
            source_table=source_table,
            sql=sql,
            style_qml=style_qml,
        )
        QgsProject.instance().addMapLayer(layer)

        extent = self._extent_for_canvas(layer)
        if extent is None:
            return True

        canvas = self.iface.mapCanvas()
        canvas.setExtent(extent)
        canvas.refresh()
        QApplication.processEvents()
        return True
