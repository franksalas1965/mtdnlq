# MTD-NLQ — Guía de uso del servicio (Mapa Topográfico Digital)

**Versión:** 1.0  
**Servicio:** Consultas en lenguaje natural sobre Mapa Topográfico Digital  
**Base de datos inicial:** `mtd10` (escala 1:10 000) en PostgreSQL 12

Esta guía describe **qué hacer paso a paso** para levantar MTD-NLQ y consultar
el MTD desde aplicaciones web o QGIS.

Índice general de documentación: [README.md](README.md).

---

## Índice

1. [Qué hace el servicio](#1-qué-hace-el-servicio)
2. [Requisitos previos](#2-requisitos-previos)
3. [Verificar la base de datos mtd10](#3-verificar-la-base-de-datos-mtd10)
4. [Configurar ALLOWED_SCHEMAS](#4-configurar-allowed_schemas)
5. [Instalar y arrancar MTD-NLQ](#5-instalar-y-arrancar-mtd-nlq)
6. [Probar el servicio](#6-probar-el-servicio)
7. [Consultar otra escala del MTD](#7-consultar-otra-escala-del-mtd)
8. [Detener y reiniciar](#8-detener-y-reiniciar)
9. [Problemas frecuentes](#9-problemas-frecuentes)

---

## 1. Qué hace el servicio

MTD-NLQ expone una **API REST** que:

1. Recibe una pregunta en español (ej.: *"Muéstrame la hidrografía de Villa Clara"*).
2. Usa un LLM (Ollama local u OpenAI) para generar SQL PostGIS.
3. Ejecuta el SQL contra la BD `mtd10` (solo lectura, solo `SELECT`).
4. Devuelve resultados en **GeoJSON** o tabla, con indicación de cómo mostrarlos (`display_mode`).

Los clientes (visor web, plugin QGIS) consumen `POST /api/v1/query` y dibujan el GeoJSON
en el mapa o lo muestran en una tabla.

```
Usuario → Web / QGIS plugin → MTD-NLQ :8001 → Ollama → SQL → mtd10 (PostGIS)
                                    ↓
                              GeoJSON + metadatos
```

---

## 2. Requisitos previos

| Componente | Detalle |
|------------|---------|
| PostgreSQL 12 | Corriendo en **localhost:5433** (como en tu pgAdmin) |
| PostGIS | Extensión activa en la BD `mtd10` |
| Base `mtd10` | Mapa topográfico **1:10 000** — esquemas con prefijo **`10_`** |
| Ollama (opcional) | `http://localhost:11434` con modelo `qwen2.5-coder:1.5b` o similar |
| Docker (opcional) | Para levantar la API sin instalar Python en el host |

**Credenciales por defecto en esta guía:**

```
Host:     localhost
Puerto:   5433
BD:       mtd10
Usuario:  postgres
Password: postgres
```

### PostgreSQL en Windows (no en WSL)

En tu caso, **PostgreSQL corre en Windows** (pgAdmin → `localhost:5433`). MTD-NLQ puede
correr en WSL/Docker, pero la conexión a la BD depende de dónde ejecutes la API:

| Dónde corre MTD-NLQ | Host PostgreSQL | Archivo `.env` |
|---------------------|-----------------|----------------|
| **Docker en WSL** (recomendado) | `host.docker.internal:5433` | `.env.docker.example` |
| Python en **Windows** | `localhost:5433` | `.env.example` |
| venv en **WSL** (sin Docker) | IP de Windows* | ver nota abajo |

\* Desde WSL, `localhost:5433` **no** apunta al PostgreSQL de Windows. Obtén la IP:

```bash
grep nameserver /etc/resolv.conf | awk '{print $2}'
# Ejemplo DATABASE_URL:
# postgresql+psycopg2://postgres:postgres@172.x.x.1:5433/mtd10
```

Asegúrate en Windows de que PostgreSQL escucha en todas las interfaces o en la IP
que WSL pueda alcanzar (`postgresql.conf`: `listen_addresses = '*'` o incluir la IP;
`pg_hba.conf`: permitir la subred de WSL).

---

## 3. Verificar la base de datos mtd10

Antes de arrancar MTD-NLQ, confirma que PostgreSQL responde y que PostGIS está instalado.

### Desde pgAdmin

1. Conecta al servidor **PostgreSQL 12** (puerto 5433).
2. Expande la base **`mtd10`** → **Schemas**.
3. Deberías ver **11 esquemas** con prefijo **`10_`** (el `10` = escala 1:10 000):

   > Para otras escalas el prefijo cambia: `25_` = 1:25 000, `100_` = 1:100 000.
   > Ver [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md).

   Referencia detallada: [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md)

   | Esquema | Tablas | Contenido |
   |---------|--------|-----------|
   | `10_hidrografia` | 36 | Ríos, embalses, canales, costas |
   | `10_red_vial` | 22 | Vías, caminos, ferrocarril, puentes |
   | `10_objetivos_economicos` | 28 | Industrias, minas, iglesias, aeropuertos |
   | `10_areas_verdes_y_terrenos` | 20 | Vegetación, rocas, zonas bajas |
   | `10_relieve` | 14 | Curvas de nivel, formas de relieve |
   | `10_puntos_poblados` | 7 | Ciudades, construcciones aisladas |
   | `10_hidrografia_presas` | 2 | Presas |
   | `10_provincias_y_cercas` | 2 | Límites areales, cercas |
   | `10_limites_estatales` | 1 | Límites territoriales lineales |
   | `10_puntos_de_apoyo` | 1 | Puntos de apoyo topográfico |
   | `10_configuraciones` | 5 | Sistema interno (no consultar en NL) |

   El volcado de referencia está en `docs/schema/mtd10.sql` (formato `pg_dump` custom).

### Desde línea de comandos (WSL o Linux)

```bash
psql -h localhost -p 5433 -U postgres -d mtd10 -c "SELECT PostGIS_Version();"
```

### Listar todos los esquemas MTD

```sql
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name LIKE '10\_%' ESCAPE '\'
ORDER BY schema_name;
```

Guarda esta lista: la necesitarás para `ALLOWED_SCHEMAS` en el `.env`.

---

## 4. Configurar ALLOWED_SCHEMAS

MTD-NLQ solo consulta esquemas listados explícitamente en la variable `ALLOWED_SCHEMAS`
(separados por coma, sin espacios extra).

Ejemplo para mtd10 (10 esquemas temáticos, **sin** `10_configuraciones`):

```env
ALLOWED_SCHEMAS=10_areas_verdes_y_terrenos,10_hidrografia,10_hidrografia_presas,10_limites_estatales,10_objetivos_economicos,10_provincias_y_cercas,10_puntos_de_apoyo,10_puntos_poblados,10_red_vial,10_relieve
```

Lista completa de tablas y columnas: [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md).

> Si falta un esquema en esta lista, el LLM no podrá generar SQL sobre sus tablas aunque existan en la BD.

**Recomendación:** añade `COMMENT ON TABLE/COLUMN` en PostgreSQL para mejorar la calidad
del SQL generado. MTD-NLQ incluye esos comentarios en el prompt del LLM.
Guía detallada: [MEJORAR_CALIDAD_SQL.md](MEJORAR_CALIDAD_SQL.md).

---

## 5. Instalar y arrancar MTD-NLQ

Elige **una** de las variantes (para tu entorno: **B — Windows nativo**).

### Variante A — Docker en WSL (recomendada con PostgreSQL en Windows)

**Paso 1.** Copiar el proyecto a WSL (si trabajas desde Windows):

```bash
cp -r "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/mtdnlq" ~/mtdnlq
cd ~/mtdnlq
```

**Paso 2.** Crear el archivo de configuración:

```bash
cp .env.docker.example .env
chmod 600 .env
nano .env
```

Valores para **PostgreSQL en Windows, puerto 5433**:

```env
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5433
POSTGRES_DB=mtd10
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

MTDNLQ_HOST_PORT=8001

LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://host.docker.internal:11434

ALLOWED_SCHEMAS=10_hidrografia,10_puntos_poblados,10_limites_estatales,...
CORS_ORIGINS=*
```

**Paso 3.** Verificar Ollama en el host:

```bash
curl http://localhost:11434
# Debe responder: Ollama is running

ollama pull qwen2.5-coder:1.5b   # si no lo tienes
```

Si Ollama solo escucha en `127.0.0.1`, configura `OLLAMA_HOST=0.0.0.0:11434`
(ver [EJECUCION_SERVICIO.md](EJECUCION_SERVICIO.md)).

**Paso 4.** Levantar la API:

```bash
docker compose -f docker-compose.external-db.yml up -d --build
docker compose -f docker-compose.external-db.yml logs -f mtdnlq
```

**Paso 5.** Comprobar:

```bash
curl -s http://localhost:8001/api/v1/health | python3 -m json.tool
```

---

### Variante B — Windows nativo (PostgreSQL y pruebas en Windows, Ollama en WSL)

**Sí es posible:** PostgreSQL en Windows (`localhost:5433`) y Ollama en WSL (`localhost:11434`
accesible desde Windows vía reenvío de puertos de WSL2).

**Paso 1.** En PowerShell, desde la carpeta del proyecto:

```powershell
cd "d:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq"
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

**Paso 2.** Verificar `.env` (valores para Windows):

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/mtd10
OLLAMA_BASE_URL=http://localhost:11434
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
```

**Paso 3.** Arrancar la API:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python -m uvicorn mtdnlq.main:app --host 0.0.0.0 --port 8001
```

**Paso 4.** Probar en otra terminal:

```powershell
Invoke-RestMethod http://localhost:8001/api/v1/health
# Swagger: http://localhost:8001/docs
```

Consulta NL (puede tardar varios minutos en CPU):

```powershell
curl.exe -s -X POST http://localhost:8001/api/v1/query `
  -H "Content-Type: application/json" `
  --data-binary "@test_query.json"
```

---

### Variante C — Python en WSL (venv + uvicorn)

**Paso 1.** Entorno virtual e dependencias:

```bash
cd ~/mtdnlq
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Paso 2.** Configuración:

```bash
cp .env.example .env
```

Contenido mínimo de `.env`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/mtd10

LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT_SECONDS=180

ALLOWED_SCHEMAS=10_hidrografia,10_puntos_poblados,10_limites_estatales,...
MAX_RESULTS=100
CORS_ORIGINS=*
```

**Paso 3.** Arrancar:

```bash
cd ~/mtdnlq
source venv/bin/activate
python3 -m uvicorn mtdnlq.main:app --host 0.0.0.0 --port 8001 --reload
```

URL del servicio: **`http://localhost:8001`**  
Swagger: **`http://localhost:8001/docs`**

---

## 6. Probar el servicio

> **Guía completa con ejemplos:** [PRUEBAS_INICIALES.md](PRUEBAS_INICIALES.md)  
> (health, schema, Swagger, PowerShell, JSON de ejemplo, pytest)

### 6.1 Health check

```bash
curl http://localhost:8001/api/v1/health
```

Respuesta esperada: `"status": "ok"` y número de tablas detectadas > 0.

### 6.2 Ver esquema detectado

```bash
curl -s "http://localhost:8001/api/v1/schema?refresh=true" | python3 -m json.tool
```

Comprueba que aparecen tablas de esquemas `10_*`. Si la lista está vacía, revisa
`ALLOWED_SCHEMAS` y la conexión a `mtd10`.

### 6.3 Primera consulta en lenguaje natural

```bash
curl -s -X POST http://localhost:8001/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Dame los límites estatales del MTD",
    "output_format": "geojson",
    "max_results": 50,
    "explain": true
  }' | python3 -m json.tool
```

Interpretación de la respuesta:

| Campo | Uso |
|-------|-----|
| `sql` | SQL generado (revisar en pgAdmin si hay dudas) |
| `results` | GeoJSON o filas tabulares |
| `display_mode` | `"map"` → dibujar en mapa; `"table"` → grid; `"summary"` → conteos |
| `has_geometry` | `true` si el cliente debe activar capa vectorial |
| `total` | Número de registros devueltos |
| `time_ms` | Tiempo total de la consulta |

### 6.4 Ejemplos de preguntas útiles

Basadas en el esquema real de `mtd10.sql`:

- *"¿Cuántos ríos y arroyos hay?"* → `10_hidrografia.rios_y_arroyos_lineal`
- *"Ciudades con más de 20000 habitantes"* → `10_puntos_poblados.ciudad_puntual`
- *"Muéstrame las presas"* → `10_hidrografia_presas.presas_areal`
- *"Dame los límites estatales"* → `10_limites_estatales.limites_estatales_lineal`
- *"Vías de comunicación"* → `10_red_vial.vias_de_comunicacion_lineal`
- *"Curvas de nivel"* → `10_relieve.curvas_lineal`
- *"Puntos de apoyo topográfico"* → `10_puntos_de_apoyo.puntos_de_apoyo_puntual`

> Referencia completa: [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md) o `GET /api/v1/schema`.

---

## 7. Consultar otra escala del MTD

El prefijo del esquema **es el denominador de la escala**:

| Prefijo | Escala | Base de datos |
|---------|--------|---------------|
| `10_` | 1:10 000 | `mtd10` |
| `25_` | 1:25 000 | `mtd25` |
| `50_` | 1:50 000 | `mtd50` |
| `100_` | 1:100 000 | `mtd100` |

Guía completa: [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md).

Para escala **1:25 000**, por ejemplo:

1. Base de datos `mtd25`, esquemas `25_hidrografia`, `25_red_vial`, etc.
2. Segunda instancia con otro `.env`:
   ```env
   POSTGRES_DB=mtd25
   MTDNLQ_HOST_PORT=8002
   ALLOWED_SCHEMAS=25_hidrografia,25_red_vial,25_relieve,25_puntos_poblados,...
   ```
3. Levanta en el puerto 8002.
4. En web o QGIS, URL base `http://localhost:8002`.

Puedes tener **GeoNLQ** (puerto 8000), **MTD-NLQ mtd10** (8001) y **MTD-NLQ mtd25** (8002)
corriendo a la vez, cada uno con su `.env`.

---

## 8. Detener y reiniciar

### Docker

```bash
cd ~/mtdnlq
docker compose -f docker-compose.external-db.yml stop
docker compose -f docker-compose.external-db.yml up -d
docker compose -f docker-compose.external-db.yml restart mtdnlq
```

### venv

- Parar: `Ctrl+C` en la terminal de uvicorn.
- Arrancar de nuevo: repetir el comando uvicorn del paso 5B.

### Refrescar esquema tras cambios en la BD

```bash
curl -s "http://localhost:8001/api/v1/schema?refresh=true"
```

---

## 9. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| Health 500 / error de conexión | Postgres no accesible en 5433 | Verificar pgAdmin; iniciar servicio PostgreSQL |
| Health OK pero 0 tablas | `ALLOWED_SCHEMAS` incorrecto | Listar esquemas con SQL del §3 y actualizar `.env` |
| 422 `sql_generation_failed` | Ollama no alcanzable o modelo lento | Verificar `OLLAMA_BASE_URL`; usar `host.docker.internal` desde Docker |
| 500 `db_error` | Tabla/columna inexistente en el SQL | Revisar `sql` en la respuesta; consultar `/api/v1/schema` |
| Timeout en consulta | Modelo en CPU | Normal 60–120 s; aumentar `OLLAMA_TIMEOUT_SECONDS=180` |
| CORS en navegador | Frontend en otro origen | Añadir dominio en `CORS_ORIGINS` o usar proxy en Next.js |

---

## Siguiente paso

Para integrar en **aplicación web** o **plugin QGIS**:

→ [INTEGRACION_WEB_QGIS.md](INTEGRACION_WEB_QGIS.md)

Para operación diaria y producción:

→ [EJECUCION_SERVICIO.md](EJECUCION_SERVICIO.md)
