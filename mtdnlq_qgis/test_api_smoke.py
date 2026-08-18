# Smoke test del cliente API (ejecutar con Python de QGIS o cualquier Python 3)
import sys
import os

plugin_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, plugin_dir)

from api_client import MtdnlqClient

client = MtdnlqClient("http://localhost:8001", timeout_seconds=10)
health = client.health()
print("OK health:", health.get("status"), "| BD:", health.get("database"), "| modelo:", health.get("llm_model"))
