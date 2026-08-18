# Pegar en la consola Python de QGIS (Complementos → Consola Python)
# Prueba rápida de carga del plugin MTD-NLQ

from qgis.utils import plugins, available_plugins, loadPlugin, startPlugin

name = "mtdnlq_qgis"
print("Disponible:", name in available_plugins)

if name not in plugins:
    ok = loadPlugin(name)
    print("loadPlugin:", ok)
    if ok:
        startPlugin(name)
        print("startPlugin: OK")
else:
    print("Plugin ya cargado")

if name in plugins:
    p = plugins[name]
    print("Instancia:", type(p).__name__)
    print("Dock visible:", p.dock.isVisible() if p.dock else "sin dock")
else:
    print("ERROR: no se pudo cargar. Revise Complementos → Instalados.")
