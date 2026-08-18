# Arquitectura multi-escala — un servicio, muchos clientes

## Resumen

**No hace falta un puerto distinto por escala.** Eso era solo una convención de despliegue antigua.

Una instancia de MTD-NLQ en `http://servidor:8001` puede atender:

- PC 1 consultando escala **1:10 000** (`scale: 10000` → BD `mtd10`)
- PC 2 consultando escala **1:25 000** (`scale: 25000` → BD `mtd25`)
- …en **paralelo**, porque cada petición HTTP es independiente.

## Cómo funciona

```
Cliente QGIS / Web
    POST /api/v1/query  { "question": "...", "scale": 10000 }
              │
              ▼
         MTD-NLQ (FastAPI, 1 proceso)
              │
    ┌─────────┴─────────┐
    ▼                   ▼
  mtd10              mtd25
  (10_*)             (25_*)
  PostgreSQL         PostgreSQL
  mismo servidor     mismo servidor
```

Por petición:

1. Se valida que `scale` esté en `MTD_ENABLED_SCALES`.
2. Se conecta a la BD `mtd{N}` (`10000` → `mtd10`).
3. Se carga el esquema cacheado **de esa escala**.
4. El LLM genera SQL con prefijo `{N}_`.
5. Se ejecuta el SQL en esa BD.

## Configuración del servidor

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/mtd10
MTD_ENABLED_SCALES=10000,25000,100000
OLLAMA_TIMEOUT_SECONDS=180
MAX_LLM_RETRIES=2
```

- `DATABASE_URL` define host, puerto y credenciales; el nombre `mtd10` es la BD por defecto al arrancar.
- Para otras escalas se cambia solo el nombre: `mtd25`, `mtd100`, etc.
- Todas las BDs deben existir en el mismo PostgreSQL (o accesibles con las mismas credenciales).

## Clientes (plugin QGIS)

- **Una URL** para todas las escalas: `http://localhost:8001`
- La escala se elige en el panel y se envía como `"scale": 10000` en el JSON.
- **Timeout recomendado:** ≥ 600 s con LLM local pequeño (3 intentos × 180 s).
- Durante una consulta la escala queda **bloqueada** hasta recibir respuesta.

Comprobar escalas habilitadas:

```http
GET /api/v1/health
```

Respuesta incluye `enabled_scales` y `recommended_client_timeout_seconds`.

## Cola asíncrona (recomendado para producción)

Evita mantener HTTP abierto 10 minutos. Flujo:

```
1. POST /api/v1/query/async   → 202 { "job_id": "...", "poll_url": "..." }
2. GET  /api/v1/jobs/{job_id} → { "status": "queued|running|completed|failed", ... }
3. Repetir paso 2 cada 2–5 s hasta completed o failed
```

### Encolar consulta

```http
POST /api/v1/query/async
Content-Type: application/json

{
  "question": "cantidad de rios que hay",
  "scale": 10000,
  "output_format": "table"
}
```

Respuesta **202**:

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "queued",
  "scale": 10000,
  "poll_url": "/api/v1/jobs/a1b2c3d4-..."
}
```

### Consultar estado

```http
GET /api/v1/jobs/a1b2c3d4-...
```

Mientras espera:

```json
{
  "status": "queued",
  "queue_position": 2
}
```

En ejecución:

```json
{ "status": "running" }
```

Terminado:

```json
{
  "status": "completed",
  "result": { "...": "QueryResponse completo" }
}
```

### Concurrencia en el servidor

```env
MAX_CONCURRENT_LLM_JOBS=1   # cuántas inferencias LLM a la vez (Ollama CPU → 1)
MAX_QUEUED_JOBS=100         # máximo en cola + ejecución
```

- Usuario A (escala 10000) y usuario B (escala 50000) comparten **la misma cola LLM**.
- PostgreSQL atiende en paralelo (pools por escala).
- El semáforo evita saturar Ollama con N inferencias simultáneas.

Estadísticas: `GET /api/v1/queue/stats` y campo `queue` en `/health`.

El plugin QGIS usa este modo **por defecto** (`use_async_queries=true`).

---

## Cuándo usar varios puertos

Solo si quieres **aislar** instancias (distinto LLM, distinto hardware, distinto equipo):

| Puerto | Uso |
|--------|-----|
| 8001 | Producción mtd10 |
| 8002 | Pruebas mtd25 |

No es requisito técnico; es organización operativa.

## Error de timeout (180 s)

El plugin cortaba la conexión HTTP a los **180 s**, pero el servidor puede tardar hasta **3 × 180 s** (reintentos del LLM). Solución:

- Plugin: timeout **600 s** por defecto.
- Servidor: `OLLAMA_TIMEOUT_SECONDS=180`, `MAX_LLM_RETRIES=2`.
- Mejor aún: modelo `qwen2.5-coder:7b` o API cloud.

Ver también [MEJORAR_CALIDAD_SQL.md](MEJORAR_CALIDAD_SQL.md).
