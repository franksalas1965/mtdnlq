# Ejecutar en consola Python de QGIS para probar simbología MTD
# Complementos → Consola Python → pegar

import json
import urllib.request
from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType, QVariant

# Ajuste la ruta del plugin en desarrollo
import sys
sys.path.insert(0, r"D:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq_qgis")

from mtd_style_loader import apply_qml_to_layer

url = "http://localhost:8001/api/v1/layer-style?source_schema=10_hidrografia&source_table=rios_y_arroyos_lineal&scale=10000&style_mode=i"
with urllib.request.urlopen(url, timeout=30) as resp:
    data = json.loads(resp.read().decode())

qml = data.get("style_qml")
print("QML len:", len(qml or ""), "found:", data.get("found"))

layer = QgsVectorLayer("LineString?crs=EPSG:4267", "test_mtd_style", "memory")
fields = QgsFields()
fields.append(QgsField("geocodigo", QMetaType.Type.QString))
fields.append(QgsField("nombre", QMetaType.Type.QString))
layer.dataProvider().addAttributes(fields.toList())
layer.updateFields()

feat = QgsFeature(fields)
feat.setGeometry(QgsGeometry.fromWkt("LINESTRING(500000 200000, 501000 201000)"))
feat.setAttributes(["30400012", "Carrascal"])
layer.dataProvider().addFeature(feat)
layer.updateExtents()

props = {"geocodigo": "30400012", "nombre": "Carrascal"}
ok = apply_qml_to_layer(layer, qml, feature_props=props)
print("apply ok:", ok, "renderer:", type(layer.renderer()).__name__)
QgsProject.instance().addMapLayer(layer)
