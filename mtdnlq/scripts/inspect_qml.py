from mtdnlq.services.layer_style_service import fetch_layer_style_qml
import re

qml, name = fetch_layer_style_qml("10_hidrografia", "rios_y_arroyos_lineal", 10000, "i")
print("name", name, "len", len(qml or ""))
if qml:
    i = qml.find("renderer-v2")
    print(qml[i : i + 150])
    rules = re.findall(r'filter="([^"]+)"', qml)
    print("rules count", len(rules))
    print("sample rules", rules[:8])
