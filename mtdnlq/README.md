# MTD-NLQ — Consultas en Lenguaje Natural sobre Mapa Topográfico Digital

**MTD-NLQ** (*Mapa Topográfico Digital — Natural Language Query*): servicio Python (FastAPI) que traduce
preguntas en español a SQL geoespacial sobre bases PostGIS del MTD.

Los resultados se devuelven como **GeoJSON** o tabla, listos para consumir desde
aplicaciones web o plugins de **QGIS**.

## Ejemplo de uso

**Pregunta:** "Dame los ríos que cruzan la provincia de Pinar del Río"

**Respuesta:** GeoJSON con geometrías + metadatos (`display_mode: "map"`) para pintar
directamente en un visor web o en QGIS.

---

## Base de datos de referencia (MTD 1:10 000)

| Parámetro | Valor |
|-----------|-------|
| Servidor | `localhost` |
| Puerto | `5433` |
| Base de datos | `mtd10` |
| Usuario | `postgres` |
| Contraseña | `postgres` |
| Esquemas | Prefijo **`10_`** = escala 1:10 000 — 11 esquemas, 138 tablas ([convención](docs/CONVENCION_ESCALAS.md), [detalle](docs/ESQUEMA_MTD10.md)) |
| SRID | **4267** (NAD27) |
| Volcado referencia | `docs/schema/mtd10.sql` |

En pgAdmin verás 11 esquemas temáticos bajo `mtd10` (hidrografía, red vial, relieve,
puntos poblados, etc.). El volcado de ejemplo está en `docs/schema/mtd10.sql`.

---

## Inicio rápido

### Requisitos

- PostgreSQL 12+ con PostGIS (servidor en puerto **5433** con la BD `mtd10`)
- Python 3.11+ **o** Docker
- Ollama (recomendado, modelo local) u OpenAI/Anthropic

### Opción A — Docker (recomendado)

```bash
cd mtdnlq
cp .env.docker.example .env
# Revisar POSTGRES_* y ALLOWED_SCHEMAS en .env

docker compose -f docker-compose.external-db.yml up -d --build
curl http://localhost:8001/api/v1/health
```

El servicio queda en **`http://localhost:8001`** (puerto 8001 para no chocar con GeoNLQ en 8000).

### Opción B — Python local (WSL o Linux)

```bash
cd mtdnlq
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Editar .env si cambian credenciales

python3 -m uvicorn mtdnlq.main:app --host 0.0.0.0 --port 8001 --reload
```

Documentación interactiva: `http://localhost:8001/docs`

### Verificación

```bash
# Estado del servicio
curl http://localhost:8001/api/v1/health

# Tablas MTD detectadas
curl -s http://localhost:8001/api/v1/schema | python3 -m json.tool

# Consulta de prueba
curl -s -X POST http://localhost:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Cuántos ríos y arroyos hay en el MTD?"}' \
  | python3 -m json.tool
```

> Con Ollama en CPU la primera consulta puede tardar 1–2 minutos.

---

## Otras escalas del MTD

El **prefijo numérico** del esquema indica la escala: `10_` = 1:10 000, `25_` = 1:25 000,
`100_` = 1:100 000, etc. Detalle en [docs/CONVENCION_ESCALAS.md](docs/CONVENCION_ESCALAS.md).

| Escala | Base de datos | Prefijo esquemas | Puerto API sugerido |
|--------|---------------|------------------|---------------------|
| 1:10 000 | `mtd10` | `10_*` | 8001 |
| 1:25 000 | `mtd25` | `25_*` | 8002 |
| 1:50 000 | `mtd50` | `50_*` | 8003 |
| 1:100 000 | `mtd100` | `100_*` | 8004 |
| 1:250 000 | `mtd250` | `250_*` | 8005 |

Para otra escala: copia `.env`, cambia `POSTGRES_DB`, `ALLOWED_SCHEMAS` y el puerto.
Puedes levantar **una instancia MTD-NLQ por escala** en paralelo.

---

## API principal

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/v1/query` | Pregunta en lenguaje natural → SQL → resultados |
| `GET` | `/api/v1/schema` | Tablas y columnas disponibles |
| `GET` | `/api/v1/health` | Estado del servicio y conexión BD |
| `GET` | `/docs` | Swagger UI |

### Ejemplo `POST /api/v1/query`

```bash
curl -X POST http://localhost:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Lista los puntos poblados de La Habana",
    "output_format": "geojson",
    "max_results": 100,
    "explain": true
  }'
```

Campos útiles de la respuesta para clientes web/QGIS:

- `display_mode`: `"map"` | `"table"` | `"summary"`
- `results`: GeoJSON `FeatureCollection` (si hay geometría)
- `has_geometry`: indica si se puede dibujar en mapa
- `sql`: SQL generado (útil para depuración)

---

## Documentación

Índice completo: [docs/README.md](docs/README.md)

| Documento | Contenido |
|-----------|-----------|
| [docs/GUIA_USO_SERVICIO.md](docs/GUIA_USO_SERVICIO.md) | Instalación y configuración |
| [docs/PRUEBAS_INICIALES.md](docs/PRUEBAS_INICIALES.md) | **Probar el servicio** (health, consultas, pytest) |
| [docs/CONVENCION_ESCALAS.md](docs/CONVENCION_ESCALAS.md) | Prefijos `10_`, `25_`, `100_`… y su escala |
| [docs/ESQUEMA_MTD10.md](docs/ESQUEMA_MTD10.md) | Esquema detallado mtd10 (1:10 000) |
| [docs/INTEGRACION_WEB_QGIS.md](docs/INTEGRACION_WEB_QGIS.md) | Consumir la API desde web y QGIS |
| [docs/EJECUCION_SERVICIO.md](docs/EJECUCION_SERVICIO.md) | Arranque, parada y mantenimiento |
| [docs/DESPLIEGUE_PRODUCCION.md](docs/DESPLIEGUE_PRODUCCION.md) | Producción con Nginx y seguridad |

---

## Relación con GeoNLQ

- **GeoNLQ** (`../geonlq`): consultas NL sobre datos de infraestructura vial (puentes, viales).
- **MTD-NLQ** (`mtdnlq`): consultas NL sobre **Mapa Topográfico Digital** por escala.

Comparten la misma arquitectura (FastAPI + LLM + PostGIS); difieren en la base de datos,
esquemas y ejemplos del prompt.

---

## Estructura del proyecto

```
mtdnlq/
├── docs/              → Guías de uso, integración web/QGIS, despliegue
├── src/mtdnlq/        → Código FastAPI (api, db, llm, nlq, services)
├── .env.example       → Plantilla para mtd10 en localhost:5433
├── docker-compose.external-db.yml
├── Dockerfile
└── requirements.txt
```
