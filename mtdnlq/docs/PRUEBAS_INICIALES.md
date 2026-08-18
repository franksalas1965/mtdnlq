# MTD-NLQ — Pruebas iniciales del servicio

Guía rápida para comprobar que MTD-NLQ funciona después de arrancarlo.
Asume el servicio en **`http://localhost:8001`** (Windows local o WSL/Docker).

---

## Antes de probar

1. **PostgreSQL** `mtd10` accesible (Windows: `localhost:5433`).
2. **Ollama** corriendo (`http://localhost:11434` → *Ollama is running*).
3. **MTD-NLQ** levantado:

```powershell
cd "D:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python -m uvicorn mtdnlq.main:app --host 0.0.0.0 --port 8001
```

Si el puerto 8001 está ocupado (`WinError 10048`), ya hay otra instancia corriendo — usa esa o libera el puerto:

```powershell
netstat -ano | findstr ":8001"
Stop-Process -Id <PID> -Force
```

---

## Paso 1 — Health check

Comprueba que la API y la BD responden.

### Navegador

Abre: **http://localhost:8001/api/v1/health**

Respuesta esperada:

```json
{
  "status": "healthy",
  "database": "connected",
  "llm_provider": "ollama",
  "llm_model": "qwen2.5-coder:1.5b"
}
```

### PowerShell

```powershell
Invoke-RestMethod http://localhost:8001/api/v1/health | ConvertTo-Json
```

---

## Paso 2 — Ver tablas MTD detectadas

Comprueba que `ALLOWED_SCHEMAS` incluye los esquemas `10_*` (escala 1:10 000).

### PowerShell

```powershell
$r = Invoke-RestMethod "http://localhost:8001/api/v1/schema?refresh=true"
"Tablas detectadas: $($r.tables.Count)"
$r.tables | Select-Object -First 5 | ForEach-Object { "$($_.schema).$($_.name)" }
```

Deberías ver **~133 tablas** con prefijos como `10_hidrografia`, `10_red_vial`, etc.

Referencia: [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md) · [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md)

---

## Paso 3 — Swagger UI (recomendado para la primera consulta NL)

1. Abre **http://localhost:8001/docs**
2. Expande **`POST /api/v1/query`** → **Try it out**
3. Pega el cuerpo JSON:

```json
{
  "question": "Cuantos rios y arroyos hay",
  "output_format": "table",
  "explain": true,
  "max_results": 10
}
```

4. **Execute**
5. Espera **1–3 minutos** (Ollama en CPU es lento con 133 tablas en el esquema)

---

## Paso 4 — Consulta NL desde PowerShell

Usa archivos JSON de ejemplo (evita problemas de codificación con tildes en PowerShell):

| Archivo | Uso |
|---------|-----|
| [ejemplos/consulta_conteo.json](ejemplos/consulta_conteo.json) | Contar ríos y arroyos |
| [ejemplos/consulta_geojson.json](ejemplos/consulta_geojson.json) | Límites estatales con geometría |

Desde la carpeta `mtdnlq`:

```powershell
cd "D:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq"

curl.exe -s -X POST "http://localhost:8001/api/v1/query" `
  -H "Content-Type: application/json" `
  --data-binary "@docs/ejemplos/consulta_conteo.json"
```

Consulta con GeoJSON (para mapa / QGIS):

```powershell
curl.exe -s -X POST "http://localhost:8001/api/v1/query" `
  -H "Content-Type: application/json" `
  --data-binary "@docs/ejemplos/consulta_geojson.json"
```

---

## Paso 5 — Interpretar la respuesta

### Respuesta exitosa (HTTP 200)

```json
{
  "question": "Cuantos rios y arroyos hay",
  "sql": "SELECT COUNT(*) AS total FROM \"10_hidrografia\".rios_y_arroyos_lineal",
  "results": [{ "total": 1234 }],
  "total": 1,
  "time_ms": 95000,
  "display_mode": "summary",
  "has_geometry": false,
  "explain": "..."
}
```

| Campo | Significado |
|-------|-------------|
| `sql` | SQL generado — revísalo en pgAdmin si hay dudas |
| `results` | Filas o GeoJSON |
| `display_mode` | `map` → dibujar en mapa; `table` / `summary` → tabla o número |
| `has_geometry` | `true` si el cliente puede pintar en QGIS/web |
| `time_ms` | Tiempo total (ms) |

### Error común (HTTP 422)

```json
{
  "detail": {
    "error": "sql_generation_failed",
    "message": "No se pudo generar SQL válido..."
  }
}
```

**Qué hacer:** ver la guía completa [MEJORAR_CALIDAD_SQL.md](MEJORAR_CALIDAD_SQL.md). Resumen:

1. Añadir `COMMENT ON TABLE/COLUMN` en PostgreSQL (MTD-NLQ los incluye en el prompt).
2. Refrescar esquema: `GET /api/v1/schema?refresh=true`.
3. Reformular la pregunta o usar las [preguntas sugeridas](#preguntas-de-prueba-sugeridas).
4. Cambiar a un modelo mayor en `.env`:

```env
LLM_MODEL=qwen2.5-coder:7b
```

Script SQL de ejemplo: [sql/comentarios_mtd10_ejemplo.sql](sql/comentarios_mtd10_ejemplo.sql).

---

## Preguntas de prueba sugeridas

Alineadas con el esquema real `mtd10` (prefijo `10_` = escala 1:10 000):

| Pregunta | Tabla esperada |
|----------|----------------|
| *Cuantos rios y arroyos hay* | `10_hidrografia.rios_y_arroyos_lineal` |
| *Cuantos puntos de apoyo topografico hay* | `10_puntos_de_apoyo.puntos_de_apoyo_puntual` |
| *Dame los limites estatales* | `10_limites_estatales.limites_estatales_lineal` |
| *Lista las vias de comunicacion* | `10_red_vial.vias_de_comunicacion_lineal` |
| *Curvas de nivel del relieve* | `10_relieve.curvas_lineal` |

Para conteos use `"output_format": "table"`. Para dibujar en mapa use `"output_format": "geojson"`.

---

## Paso 6 — Tests unitarios (sin BD ni Ollama)

Validan el validador SQL y el constructor de prompts:

```powershell
cd "D:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq"
$env:PYTHONPATH = "src"
.\.venv\Scripts\pip install pytest
.\.venv\Scripts\python -m pytest tests/unit -v
```

Resultado esperado: **16 passed**.

---

## Checklist rápido

| # | Prueba | OK si… |
|---|--------|--------|
| 1 | `GET /api/v1/health` | `"status": "healthy"` |
| 2 | `GET /api/v1/schema` | ~133 tablas `10_*` |
| 3 | `POST /api/v1/query` (conteo) | HTTP 200 + campo `sql` |
| 4 | `pytest tests/unit` | 16 tests passed |

---

## Siguiente paso

- Integrar en web o QGIS: [INTEGRACION_WEB_QGIS.md](INTEGRACION_WEB_QGIS.md)
- Operación diaria: [EJECUCION_SERVICIO.md](EJECUCION_SERVICIO.md)
