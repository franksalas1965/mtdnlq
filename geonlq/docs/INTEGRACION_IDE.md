# GeoNLQ — Guía de Integración con ide-minfar

**Versión:** 1.0  
**Stack cliente:** Next.js 14 · TypeScript · MapLibre GL · MUI · Axios  
**Servicio:** GeoNLQ FastAPI en `http://localhost:8000`

---

## Índice

1. [Arquitectura de la integración](#1-arquitectura-de-la-integración)
2. [Tipos TypeScript](#2-tipos-typescript)
3. [Proxy API Route en Next.js](#3-proxy-api-route-en-nextjs)
4. [Hook useNLQuery](#4-hook-usnlquery)
5. [Componente NLQueryPanel](#5-componente-nlquerypanel)
6. [Visualización en mapa (MapLibre)](#6-visualización-en-mapa-maplibre)
7. [Visualización como tabla (MUI)](#7-visualización-como-tabla-mui)
8. [Visualización como resumen](#8-visualización-como-resumen)
9. [Configuración CORS y .env](#9-configuración-cors-y-env)
10. [Añadir al menú de ide-minfar](#10-añadir-al-menú-de-ide-minfar)
11. [Cómo el LLM entiende los campos de las tablas](#11-cómo-el-llm-entiende-los-campos-de-las-tablas)

---

## 1. Arquitectura de la integración

```
Usuario escribe pregunta
        ↓
  NLQueryPanel (React)
        ↓  fetch POST
  /api/nlq (Next.js proxy)       ← evita CORS y oculta la URL interna
        ↓  axios POST
  GeoNLQ :8000/api/v1/query
        ↓
  Ollama (LLM local) → SQL → PostGIS
        ↓
  GeoJSON + display_mode
        ↓
  NLQueryPanel decide:
    display_mode = "map"     → añade source/layer a MapLibre
    display_mode = "table"   → MUI DataGrid
    display_mode = "summary" → MUI Card con métricas
```

**Por qué un proxy Next.js:** la app corre en `localhost:300` y GeoNLQ en `localhost:8000`.
En lugar de configurar CORS en el servicio, el proxy de Next.js hace la llamada
servidor-a-servidor, evitando el problema completamente y ocultando la URL interna
al navegador.

---

## 2. Tipos TypeScript

Crea el archivo `src/types/geonlq.ts`:

```typescript
// src/types/geonlq.ts

export type GeoNLQDisplayMode = "map" | "table" | "summary";

export interface GeoNLQRequest {
  question: string;
  output_format?: "geojson" | "table";
  max_results?: number;
  explain?: boolean;
}

export interface GeoNLQFeature {
  type: "Feature";
  geometry: GeoJSON.Geometry | null;
  properties: Record<string, string | number | boolean | null>;
}

export interface GeoNLQFeatureCollection {
  type: "FeatureCollection";
  features: GeoNLQFeature[];
}

export interface GeoNLQResponse {
  question: string;
  sql: string;
  results: GeoNLQFeatureCollection | Record<string, unknown>[];
  total: number;
  time_ms: number;
  explanation: string | null;
  /** Cómo debe visualizarse el resultado */
  display_mode: GeoNLQDisplayMode;
  /** Nombres de columnas (sin geometría) */
  columns: string[];
  /** True si algún feature tiene geometría */
  has_geometry: boolean;
}

export interface GeoNLQError {
  error: string;
  message: string;
}
```

---

## 3. Proxy API Route en Next.js

Crea el archivo `src/app/api/nlq/route.ts`:

```typescript
// src/app/api/nlq/route.ts
import { NextRequest, NextResponse } from "next/server";

const GEONLQ_URL = process.env.GEONLQ_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const response = await fetch(`${GEONLQ_URL}/api/v1/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // Sin timeout de Next.js — el modelo tarda hasta 120s en CPU
      signal: AbortSignal.timeout(150_000),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Error de conexión con GeoNLQ";
    return NextResponse.json(
      { error: "geonlq_unavailable", message },
      { status: 503 }
    );
  }
}

export async function GET() {
  try {
    const response = await fetch(`${GEONLQ_URL}/api/v1/health`, {
      signal: AbortSignal.timeout(5_000),
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  }
}
```

Añade en `.env.local`:
```env
GEONLQ_URL=http://localhost:8000
```

---

## 4. Hook useNLQuery

Crea `src/hooks/useNLQuery.ts`:

```typescript
// src/hooks/useNLQuery.ts
"use client";
import { useState, useCallback } from "react";
import type { GeoNLQRequest, GeoNLQResponse, GeoNLQError } from "@/types/geonlq";

interface UseNLQueryResult {
  query: (question: string, opts?: Partial<GeoNLQRequest>) => Promise<void>;
  data: GeoNLQResponse | null;
  loading: boolean;
  error: string | null;
  reset: () => void;
}

export function useNLQuery(): UseNLQueryResult {
  const [data, setData] = useState<GeoNLQResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useCallback(async (
    question: string,
    opts: Partial<GeoNLQRequest> = {}
  ) => {
    setLoading(true);
    setError(null);
    setData(null);

    try {
      const res = await fetch("/api/nlq", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, output_format: "geojson", ...opts }),
      });

      const json = await res.json();

      if (!res.ok) {
        const err = json as GeoNLQError;
        setError(err.message ?? "Error desconocido");
        return;
      }

      setData(json as GeoNLQResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de red");
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
  }, []);

  return { query, data, loading, error, reset };
}
```

---

## 5. Componente NLQueryPanel

Crea `src/components/NLQuery/NLQueryPanel.tsx`:

```typescript
// src/components/NLQuery/NLQueryPanel.tsx
"use client";
import React, { useState } from "react";
import {
  Box, TextField, Button, Typography, CircularProgress,
  Alert, Chip, Divider, Paper,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import MapIcon from "@mui/icons-material/Map";
import TableChartIcon from "@mui/icons-material/TableChart";
import SummarizeIcon from "@mui/icons-material/Summarize";
import { useNLQuery } from "@/hooks/useNLQuery";
import type { GeoNLQResponse } from "@/types/geonlq";
import { NLQueryTable } from "./NLQueryTable";
import { NLQuerySummary } from "./NLQuerySummary";

interface NLQueryPanelProps {
  /** Mapa MapLibre activo — para añadir capas cuando display_mode = "map" */
  map?: import("maplibre-gl").Map | null;
  /** Callback opcional cuando hay resultados nuevos */
  onResult?: (response: GeoNLQResponse) => void;
}

const MODE_ICONS = {
  map:     <MapIcon fontSize="small" />,
  table:   <TableChartIcon fontSize="small" />,
  summary: <SummarizeIcon fontSize="small" />,
};

const MODE_LABELS = {
  map:     "Mapa",
  table:   "Tabla",
  summary: "Resumen",
};

export const NLQueryPanel: React.FC<NLQueryPanelProps> = ({ map, onResult }) => {
  const [input, setInput] = useState("");
  const { query, data, loading, error, reset } = useNLQuery();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    const result = await query(input.trim());
    if (data) onResult?.(data);
  };

  // Cuando llegan resultados con geometría, añadirlos al mapa
  React.useEffect(() => {
    if (!data || !map || data.display_mode !== "map") return;

    const sourceId  = "geonlq-results";
    const layerId   = "geonlq-layer";
    const fc = data.results as { type: string; features: unknown[] };

    // Eliminar capas anteriores
    if (map.getLayer(layerId))  map.removeLayer(layerId);
    if (map.getSource(sourceId)) map.removeSource(sourceId);

    map.addSource(sourceId, { type: "geojson", data: fc as GeoJSON.FeatureCollection });

    // Detectar tipo de geometría por el primer feature
    const firstGeom = (fc.features[0] as { geometry?: { type: string } })?.geometry;
    const geomType  = firstGeom?.type ?? "";

    if (geomType.includes("Point")) {
      map.addLayer({
        id: layerId, type: "circle", source: sourceId,
        paint: { "circle-radius": 8, "circle-color": "#E53935", "circle-opacity": 0.85 },
      });
    } else if (geomType.includes("LineString")) {
      map.addLayer({
        id: layerId, type: "line", source: sourceId,
        paint: { "line-color": "#1565C0", "line-width": 3 },
      });
    } else {
      map.addLayer({
        id: layerId, type: "fill", source: sourceId,
        paint: { "fill-color": "#43A047", "fill-opacity": 0.5 },
      });
    }

    // Centrar el mapa en los resultados
    if (fc.features.length > 0) {
      const bounds = computeBounds(fc as GeoJSON.FeatureCollection);
      if (bounds) map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
    }

    onResult?.(data);
  }, [data, map]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, p: 2, height: "100%" }}>
      {/* Barra de búsqueda */}
      <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", gap: 1 }}>
        <TextField
          fullWidth
          size="small"
          placeholder='Ej: "Dame los puentes en mal estado"'
          value={input}
          onChange={(e) => { setInput(e.target.value); reset(); }}
          disabled={loading}
          InputProps={{ sx: { fontSize: 14 } }}
        />
        <Button
          type="submit"
          variant="contained"
          disabled={loading || !input.trim()}
          startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <SearchIcon />}
          sx={{ whiteSpace: "nowrap", minWidth: 100 }}
        >
          {loading ? "Consultando…" : "Consultar"}
        </Button>
      </Box>

      {/* Tiempo de espera */}
      {loading && (
        <Alert severity="info" sx={{ py: 0.5 }}>
          El modelo tarda entre 20 y 90 segundos en responder (CPU local). Por favor espere…
        </Alert>
      )}

      {/* Error */}
      {error && <Alert severity="error">{error}</Alert>}

      {/* Resultado */}
      {data && (
        <Box sx={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 1 }}>
          {/* Cabecera del resultado */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Chip
              icon={MODE_ICONS[data.display_mode]}
              label={MODE_LABELS[data.display_mode]}
              color="primary"
              size="small"
            />
            <Chip label={`${data.total} resultados`} size="small" variant="outlined" />
            <Chip label={`${(data.time_ms / 1000).toFixed(1)}s`} size="small" variant="outlined" />
          </Box>

          {/* SQL generado (colapsable) */}
          <Paper variant="outlined" sx={{ p: 1, bgcolor: "#f5f5f5" }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
              {data.sql}
            </Typography>
          </Paper>

          <Divider />

          {/* Resultado según modo */}
          {data.display_mode === "map" && (
            <Alert severity="success">
              {data.total} elementos añadidos al mapa como capa "geonlq-results".
            </Alert>
          )}

          {data.display_mode === "table" && (
            <NLQueryTable columns={data.columns} results={data.results} />
          )}

          {data.display_mode === "summary" && (
            <NLQuerySummary columns={data.columns} results={data.results} />
          )}
        </Box>
      )}
    </Box>
  );
};

/** Calcula el bounding box de una FeatureCollection para fitBounds. */
function computeBounds(
  fc: GeoJSON.FeatureCollection
): [[number, number], [number, number]] | null {
  let minLng = Infinity, minLat = Infinity;
  let maxLng = -Infinity, maxLat = -Infinity;
  let found = false;

  for (const feature of fc.features) {
    if (!feature.geometry) continue;
    const coords = extractCoords(feature.geometry);
    for (const [lng, lat] of coords) {
      minLng = Math.min(minLng, lng); maxLng = Math.max(maxLng, lng);
      minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
      found = true;
    }
  }

  return found ? [[minLng, minLat], [maxLng, maxLat]] : null;
}

function extractCoords(geom: GeoJSON.Geometry): [number, number][] {
  if (geom.type === "Point") return [[geom.coordinates[0], geom.coordinates[1]]];
  if (geom.type === "LineString" || geom.type === "MultiPoint")
    return geom.coordinates.map(c => [c[0], c[1]]);
  if (geom.type === "Polygon" || geom.type === "MultiLineString")
    return geom.coordinates.flat().map(c => [c[0], c[1]]);
  if (geom.type === "MultiPolygon")
    return geom.coordinates.flat(2).map(c => [c[0], c[1]]);
  return [];
}
```

---

## 6. Visualización en mapa (MapLibre)

El código del efecto en `NLQueryPanel` ya gestiona la capa. La lógica es:

```typescript
// Detección automática por tipo de geometría del primer feature:
// Point / MultiPoint   → "circle" layer
// LineString           → "line" layer
// Polygon              → "fill" layer

// Para personalizar estilos, modifica paint en el addLayer correspondiente.
// Para nombrar la capa de forma dinámica, usa data.question como parte del ID.
```

Para **mostrar el popup con propiedades** al hacer clic:

```typescript
map.on("click", "geonlq-layer", (e) => {
  const props = e.features?.[0]?.properties ?? {};
  new maplibregl.Popup()
    .setLngLat(e.lngLat)
    .setHTML(
      Object.entries(props)
        .map(([k, v]) => `<b>${k}:</b> ${v}`)
        .join("<br>")
    )
    .addTo(map);
});
```

---

## 7. Visualización como tabla (MUI)

Crea `src/components/NLQuery/NLQueryTable.tsx`:

```typescript
// src/components/NLQuery/NLQueryTable.tsx
"use client";
import React from "react";
import {
  Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Typography,
} from "@mui/material";

interface Props {
  columns: string[];
  results: unknown;
}

export const NLQueryTable: React.FC<Props> = ({ columns, results }) => {
  const fc = results as { features?: { properties: Record<string, unknown> }[] };
  const rows = fc?.features?.map(f => f.properties) ?? (results as Record<string, unknown>[]);

  if (!rows?.length) {
    return <Typography color="text.secondary">Sin resultados.</Typography>;
  }

  const cols = columns.length > 0 ? columns : Object.keys(rows[0]);

  return (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 400 }}>
      <Table stickyHeader size="small">
        <TableHead>
          <TableRow>
            {cols.map(col => (
              <TableCell key={col} sx={{ fontWeight: "bold", bgcolor: "#1565C0", color: "#fff" }}>
                {col}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={i} hover>
              {cols.map(col => (
                <TableCell key={col}>{String(row[col] ?? "")}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};
```

---

## 8. Visualización como resumen

Crea `src/components/NLQuery/NLQuerySummary.tsx`:

```typescript
// src/components/NLQuery/NLQuerySummary.tsx
"use client";
import React from "react";
import { Box, Paper, Typography } from "@mui/material";

interface Props {
  columns: string[];
  results: unknown;
}

export const NLQuerySummary: React.FC<Props> = ({ columns, results }) => {
  const fc = results as { features?: { properties: Record<string, unknown> }[] };
  const rows = fc?.features?.map(f => f.properties) ?? (results as Record<string, unknown>[]);
  const cols = columns.length > 0 ? columns : Object.keys(rows?.[0] ?? {});

  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
      {rows.map((row, ri) =>
        cols.map(col => (
          <Paper
            key={`${ri}-${col}`}
            variant="outlined"
            sx={{ p: 2, minWidth: 140, textAlign: "center" }}
          >
            <Typography variant="h5" color="primary" fontWeight="bold">
              {String(row[col] ?? "—")}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {col.replace(/_/g, " ")}
            </Typography>
          </Paper>
        ))
      )}
    </Box>
  );
};
```

---

## 9. Configuración CORS y .env

### En GeoNLQ (`.env` en WSL `~/geonlq/.env`)

```env
# Orígenes permitidos — separados por coma
# Desarrollo local:
CORS_ORIGINS=http://localhost:300,http://localhost:3000

# Producción (ejemplo):
# CORS_ORIGINS=https://ide.minfar.cu
```

### En ide-minfar (`.env.local`)

```env
# URL interna del servicio GeoNLQ
GEONLQ_URL=http://localhost:8000
```

> **Nota:** Con el proxy en `/api/nlq` el navegador nunca llega a contactar con
> `localhost:8000` directamente, por lo que CORS no es estrictamente necesario.
> El `CORS_ORIGINS` en GeoNLQ es útil si en algún momento se llama al servicio
> directamente desde el cliente (QGIS, Postman, otra app).

Añade en `.env.local` (opcional; preferir `config/runtime.json` en producción):
```env
GEONLQ_URL=http://localhost:8000
```

En producción / Docker, copie `runtime.example.json` → `config/runtime.json` y use el bloque `geonlq.baseUrl` (alcanzable desde Node, no desde el navegador). Timeout recomendado en CPU: `geonlq.timeoutMs` **600000** (ver `ide-minfar/docs/operaciones-configuracion.md`).

### GeoNLQ en Docker (B2) + IDE

| Componente | Dónde corre | Config clave |
|------------|-------------|--------------|
| IDE Next.js | Host o contenedor | `GEONLQ_URL` / `geonlq.baseUrl` → `http://host.docker.internal:8000` (o IP/puerto publicado) |
| GeoNLQ API | Contenedor `geonlq_api` | `.env`: `POSTGRES_*`, `OLLAMA_BASE_URL=http://host.docker.internal:11434` |
| Ollama | Host (systemd) | `OLLAMA_HOST=0.0.0.0:11434` si la API está en Docker |
| PostGIS | Host / servidor | Puerto publicado (p. ej. **5434**) y `pg_hba` para red Docker |

Checklist y pruebas (`docker exec … curl`): [EJECUCION_SERVICIO.md §3.4](./EJECUCION_SERVICIO.md#34-ollama-con-docker-compose-b1-y-b2). Sincronizar código del contenedor con el repo (`~/geonlq/src`) tras cambios en Windows.

---

## 10. Integración en ide-minfar (implementado)

La IDE integra GeoNLQ desde la **barra horizontal inferior** (`tools.nlquery` en `mapToolbar.json`), no desde `DynamicArea`.

| Artefacto IDE | Ruta |
|---------------|------|
| Proxy | `src/app/api/nlq/route.ts` |
| Diálogo | `src/components/nlQuery/NLQueryDialog.tsx` |
| Overlay mapa | `src/lib/geonlq/geonlqMapOverlay.ts` |
| SDD cliente | `ide-minfar/docs/geonlq-integration-architecture.md` |

Configuración runtime:

- **Servidor:** `runtime.json` → `geonlq.baseUrl` o env `GEONLQ_URL`
- **Cliente:** `public/config/geonlq.json` → `enabled`, textos UI

Flujo: botón NLQ → diálogo → `POST /api/nlq` → según `display_mode`, tabla/resumen en el diálogo o capa temporal en MapLibre.

### Alternativa (no usada por defecto)

Opcionalmente se puede exponer el mismo panel en `DynamicArea` con tipo `nlQuery`; la guía original de componentes (`NLQueryPanel`) sigue siendo válida como referencia de UI embebida.

---

## 11. Cómo el LLM entiende los campos de las tablas

El modelo traduce lenguaje natural a SQL usando los **nombres y comentarios de columna** que recibe del esquema de la base de datos. Si los campos tienen nombres poco descriptivos (abreviaturas, códigos), el modelo puede no asociarlos correctamente al significado que expresa el usuario.

### Ejemplo del problema

El usuario escribe en el panel NLQ: *"Dame los puentes en la Carretera Central"*

Si el campo de nombre de la vía se llama `nom` en lugar de `nombre`, el LLM puede no reconocerlo y generar un SQL sin filtro o con la columna incorrecta, devolviendo resultados erróneos o vacíos.

### Solución: comentarios de columna en PostgreSQL

GeoNLQ incluye automáticamente los comentarios de columna en el prompt que envía al LLM. Basta con documentar los campos ambiguos directamente en la base de datos, sin tocar ningún código:

```sql
-- Conectarse a la base de datos
psql -U postgres -d nombre_base_datos

-- Documentar campos con nombres abreviados o poco claros
COMMENT ON COLUMN viales.nom      IS 'Nombre oficial de la vía (ej: Carretera Central, Autopista Nacional)';
COMMENT ON COLUMN viales.est      IS 'Estado de conservación de la vía: bueno, regular, malo';
COMMENT ON COLUMN viales.cat      IS 'Categoría de la vía: primaria, secundaria, local, rural';
COMMENT ON COLUMN puentes.cap_tn  IS 'Carga máxima permitida en toneladas';
COMMENT ON COLUMN puentes.tip_est IS 'Tipo de estructura: hormigon, metalico, mixto, madera';
COMMENT ON COLUMN puentes.est     IS 'Estado de conservación: bueno, regular, malo';
COMMENT ON COLUMN puentes.pk      IS 'Punto kilométrico de la vía donde se ubica el puente';
```

Después de añadir los comentarios, reiniciar GeoNLQ para que recargue el esquema:

```bash
# Producción
sudo systemctl restart geonlq

# Desarrollo (WSL)
kill $(lsof -ti:8000) 2>/dev/null; fuser -k 8000/tcp 2>/dev/null
python3 -m uvicorn src.geonlq.main:app --host 0.0.0.0 --port 8000
```

El LLM pasa de ver esto:
```
- nom (character varying)
- cap_tn (numeric)
```
A ver esto:
```
- nom (character varying) — Nombre oficial de la vía (ej: Carretera Central, Autopista Nacional)
- cap_tn (numeric) — Carga máxima permitida en toneladas
```

Y genera correctamente `WHERE v.nom ILIKE '%carretera central%'` en lugar de dejar el filtro vacío.

> Para la guía completa de comentarios (todas las tablas, reglas de nomenclatura, verificación del esquema) ver `docs/DESPLIEGUE_PRODUCCION.md` sección 13.

---

## Flujo completo de una consulta

```
1. Usuario escribe: "Dame los puentes en mal estado en Pinar del Río"
2. NLQueryPanel → POST /api/nlq → GeoNLQ
3. GeoNLQ: LLM genera SQL → PostGIS lo ejecuta
4. Respuesta llega con display_mode = "map" (hay geometría)
5. NLQueryPanel añade source + layer al mapa MapLibre activo
6. Mapa centra en los puentes encontrados
7. Usuario hace clic en un punto → popup con propiedades
```

---

*Smartgeo — Agosto 2026*
