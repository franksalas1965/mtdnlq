# Análisis en lenguaje natural — MTD

Consultas en español sobre el **Mapa Topográfico Digital (MTD)** usando lenguaje natural → SQL → PostGIS.

## Componentes

| Carpeta | Descripción |
|---------|-------------|
| [`mtdnlq/`](mtdnlq/) | Backend FastAPI (NL → SQL, Ollama, PostGIS) |
| [`mtdnlq_qgis/`](mtdnlq_qgis/) | Plugin QGIS 3.40 para consultar el servicio |

## Inicio rápido (backend)

```powershell
cd mtdnlq
copy .env.example .env
# Editar .env (DATABASE_URL, OLLAMA_API_KEY, etc.)

$env:PYTHONPATH = "src"
.\.venv\Scripts\python -m uvicorn mtdnlq.main:app --host 0.0.0.0 --port 8001 --reload
```

Health: http://localhost:8001/api/v1/health · Docs: http://localhost:8001/docs

## Plugin QGIS

Ver [`mtdnlq_qgis/README.md`](mtdnlq_qgis/README.md).

## Requisitos

- PostgreSQL + PostGIS (`mtd10`, puerto 5433)
- Python 3.11+
- Ollama (local o cloud) u OpenAI/Anthropic
