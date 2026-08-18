# MTD-NLQ — Integración con aplicaciones web y QGIS

**Versión:** 1.0  
**API base:** `http://localhost:8001` (MTD 1:10 000 — `mtd10`)

Esta guía explica cómo consumir los endpoints de MTD-NLQ desde un **visor web**
y desde un **plugin de QGIS**, para mostrar los resultados en mapa o en tabla.

---

## Índice

1. [Contrato de la API](#1-contrato-de-la-api)
2. [Integración en aplicación web](#2-integración-en-aplicación-web)
3. [Integración en plugin QGIS](#3-integración-en-plugin-qgis)
4. [Visualización según display_mode](#4-visualización-según-display_mode)
5. [Configuración CORS y URLs](#5-configuración-cors-y-urls)
6. [Manejo de errores y tiempos de espera](#6-manejo-de-errores-y-tiempos-de-espera)

---

## 1. Contrato de la API

### Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Estado del servicio |
| `GET` | `/api/v1/schema` | Tablas/columnas MTD disponibles |
| `POST` | `/api/v1/query` | Consulta en lenguaje natural |

### Cuerpo de `POST /api/v1/query`

```json
{
  "question": "Lista los puntos poblados de La Habana",
  "output_format": "geojson",
  "max_results": 100,
  "explain": false
}
```

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `question` | string | *(requerido)* | Pregunta en español |
| `output_format` | `"geojson"` \| `"table"` | `"geojson"` | Formato de `results` |
| `max_results` | int | 100 | Límite de filas |
| `explain` | bool | false | Incluir explicación del SQL |

### Respuesta exitosa (200)

```json
{
  "question": "Lista los puntos poblados de La Habana",
  "sql": "SELECT ... ST_AsGeoJSON(geom)::json AS geometry ...",
  "results": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Point", "coordinates": [-82.3, 23.1] },
        "properties": { "nombre": "...", "tipo": "..." }
      }
    ]
  },
  "total": 42,
  "time_ms": 85432,
  "explanation": null,
  "display_mode": "map",
  "columns": ["nombre", "tipo", "poblacion"],
  "has_geometry": true
}
```

---

## 2. Integración en aplicación web

### Arquitectura recomendada

```
Navegador → Next.js / React (panel NLQ)
                ↓ POST /api/mtd-query  (proxy interno)
            MTD-NLQ :8001/api/v1/query
                ↓
            GeoJSON → MapLibre / Leaflet / OpenLayers
```

Usa un **proxy en el backend** del frontend para evitar CORS y ocultar la URL interna.

### Variable de entorno

```env
MTD-NLQ_URL=http://localhost:8001
```

### Proxy Next.js (App Router)

```typescript
// app/api/mtd-query/route.ts
import { NextRequest, NextResponse } from "next/server";

const MTD-NLQ_URL = process.env.MTD-NLQ_URL ?? "http://localhost:8001";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const response = await fetch(`${MTD-NLQ_URL}/api/v1/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(180_000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "MTD-NLQ no disponible";
    return NextResponse.json({ error: "MTD-NLQ_unavailable", message }, { status: 503 });
  }
}
```

### Añadir resultados al mapa (MapLibre GL)

```typescript
function addMTD-NLQResults(map: maplibregl.Map, data: MTD-NLQResponse) {
  if (data.display_mode !== "map" || !data.has_geometry) return;

  const fc = data.results as GeoJSON.FeatureCollection;
  const sourceId = "MTD-NLQ-mtd-results";
  const layerId = "MTD-NLQ-mtd-layer";

  if (map.getSource(sourceId)) {
    (map.getSource(sourceId) as maplibregl.GeoJSONSource).setData(fc);
  } else {
    map.addSource(sourceId, { type: "geojson", data: fc });
    map.addLayer({
      id: layerId,
      type: "circle",
      source: sourceId,
      paint: {
        "circle-radius": 6,
        "circle-color": "#2563eb",
      },
    });
  }
}
```

---

## 3. Integración en plugin QGIS

### Plugin incluido en este repositorio

El plugin **`mtdnlq_qgis`** (carpeta hermana `../mtdnlq_qgis/`) implementa la integración
completa para QGIS 3.40.x:

- Panel acoplable con consultas en lenguaje natural
- Configuración portable (URL, timeout, CRS, estilos)
- Tabla de resultados con botón **localizar** por registro (no carga todo el GeoJSON)
- Modos `table`, `summary` y panel de explicación

Instalación: [mtdnlq_qgis/README.md](../../mtdnlq_qgis/README.md).

### Flujo general

```
Usuario escribe pregunta en el plugin
        ↓
Plugin Python → requests.post → MTD-NLQ /api/v1/query
        ↓
Parsea GeoJSON de results
        ↓
QgsVectorLayer en memoria → añade al proyecto QGIS
```

### Ejemplo mínimo (Python 3, QGIS 3.x)

```python
import json
import requests
from qgis.core import QgsVectorLayer, QgsProject
from qgis.PyQt.QtWidgets import QMessageBox

MTD-NLQ_URL = "http://localhost:8001"

def query_mtd(question: str) -> dict:
    resp = requests.post(
        f"{MTD-NLQ_URL}/api/v1/query",
        json={"question": question, "output_format": "geojson", "max_results": 500},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()

def add_geojson_to_qgis(geojson_dict: dict, layer_name: str = "MTD-NLQ MTD"):
    geojson_str = json.dumps(geojson_dict)
    layer = QgsVectorLayer(
        f"GeoJSON?crs=EPSG:4326&string={geojson_str}",
        layer_name,
        "ogr",
    )
    if not layer.isValid():
        raise RuntimeError("No se pudo crear la capa desde GeoJSON")
    QgsProject.instance().addMapLayer(layer)
    return layer

def run_nl_query(question: str):
    data = query_mtd(question)
    if data.get("has_geometry") and data.get("display_mode") == "map":
        add_geojson_to_qgis(data["results"], f"MTD: {question[:40]}")
    else:
        QMessageBox.information(None, "MTD-NLQ", f"Resultado: {data.get('total')} filas")
```

### UI sugerida del plugin

1. Campo de texto para la pregunta.
2. Botón "Consultar" con indicador de carga (1–2 min en CPU).
3. Panel opcional con el SQL generado.
4. Selector de escala/URL — el prefijo indica la escala (`10`=1:10 000, `25`=1:25 000…).
   Ver [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md).

### Probar desde la consola Python de QGIS

```python
import requests
print(requests.get("http://localhost:8001/api/v1/health", timeout=5).json())
```

---

## 4. Visualización según display_mode

| `display_mode` | Cliente web | QGIS |
|----------------|-------------|------|
| `"map"` | Capa GeoJSON en el visor | `QgsVectorLayer` |
| `"table"` | DataGrid / tabla HTML | Tabla de atributos |
| `"summary"` | Tarjeta con métricas | Diálogo con números |

Comprueba siempre `has_geometry` antes de dibujar en mapa.

---

## 5. Configuración CORS y URLs

Desarrollo: `CORS_ORIGINS=*` en `.env` de MTD-NLQ.

Producción: lista de dominios o proxy backend únicamente.

| Instancia | Escala | URL API | Base de datos | Prefijo esquemas |
|-----------|--------|---------|---------------|------------------|
| MTD 1:10 000 | 1:10 000 | `http://servidor:8001` | `mtd10` | `10_*` |
| MTD 1:25 000 | 1:25 000 | `http://servidor:8002` | `mtd25` | `25_*` |
| MTD 1:100 000 | 1:100 000 | `http://servidor:8004` | `mtd100` | `100_*` |

---

## 6. Manejo de errores y tiempos de espera

| Código | Acción en el cliente |
|--------|----------------------|
| 200 | Procesar `results` según `display_mode` |
| 422 | Reformular la pregunta |
| 500 | Revisar SQL en modo depuración |
| 503 / timeout | MTD-NLQ u Ollama no disponible |

**Timeout recomendado:** 180 segundos.

---

## Referencias

- [GUIA_USO_SERVICIO.md](GUIA_USO_SERVICIO.md) — instalación y arranque
- [EJECUCION_SERVICIO.md](EJECUCION_SERVICIO.md) — mantenimiento
- Swagger: `http://localhost:8001/docs`
