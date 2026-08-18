# GeoNLQ — Guía paso a paso (WSL, Docker y producción)

**Versión:** 1.0 · **2026-08-09**

Mapa único de **qué hacer en cada entorno**, con enlaces al detalle. Si sigues los números en orden, no necesitas reconstruir Docker sin motivo ni levantar un segundo PostGIS en producción.

---

## Índice

1. [¿Qué camino elijo?](#1-qué-camino-elijo)
2. [WSL — desarrollo con venv (Variante A)](#2-wsl--desarrollo-con-venv-variante-a)
3. [WSL — Docker + Postgres ya existente (B2, ~/geonlq)](#3-wsl--docker--postgres-ya-existente-b2-geonlq)
4. [Generar paquete dist/ (imagen + src)](#4-generar-paquete-dist-imagen--src)
5. [Servidor de producción — Postgres ya instalado (dist/)](#5-servidor-de-producción--postgres-ya-instalado-dist)
6. [Demo local — PostGIS en contenedor (B1)](#6-demo-local--postgis-en-contenedor-b1)
7. [Comandos del día a día](#7-comandos-del-día-a-día)
8. [Actualizar sin rebuild](#8-actualizar-sin-rebuild)
9. [Problemas frecuentes](#9-problemas-frecuentes)
10. [Otros documentos](#10-otros-documentos)

---

## 1. ¿Qué camino elijo?

| Situación | Sigue la sección |
|-----------|------------------|
| WSL, Smartgeo, Postgres en `postgres14-3.3:5434`, editas código a mano | [§2 Variante A](#2-wsl--desarrollo-con-venv-variante-a) |
| WSL, mismo Postgres, API en Docker con volumen `src/` | [§3 B2 en ~/geonlq](#3-wsl--docker--postgres-ya-existente-b2-geonlq) |
| Servidor Linux con PostGIS **ya instalado**, sin Python en el SO | [§4](#4-generar-paquete-dist-imagen--src) + [§5](#5-servidor-de-producción--postgres-ya-instalado-dist) |
| PC sin Postgres — quieres BD de prueba en Docker | [§6 B1](#6-demo-local--postgis-en-contenedor-b1) |
| Producción enterprise (systemd, Nginx, sin Docker) | [DESPLIEGUE_PRODUCCION.md](./DESPLIEGUE_PRODUCCION.md) |

**Regla:** si Postgres **ya corre** en el servidor, **no** uses el `docker-compose.yml` de la raíz (servicio `postgis`).

---

## 2. WSL — desarrollo con venv (Variante A)

### Paso 1 — Requisitos

- WSL Ubuntu, Python 3.12, Ollama, Docker con contenedor Postgres (ej. `postgres14-3.3` en puerto **5434**).

### Paso 2 — Proyecto (solo la primera vez)

```bash
cp -r "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/geonlq" ~/geonlq
cd ~/geonlq
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Paso 3 — `.env` (solo la primera vez)

```bash
cp .env.example .env
nano .env
```

Ejemplo Smartgeo:

```env
DATABASE_URL=postgresql+psycopg2://postgres:TU_PASSWORD@localhost:5434/geonlq
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://localhost:11434
UVICORN_LOG_LEVEL=info
```

### Paso 4 — Esquema en BD (solo la primera vez)

```bash
docker start postgres14-3.3
docker cp ~/geonlq/docs/schema/001_initial_schema.sql postgres14-3.3:/tmp/schema.sql
docker exec -e PGPASSWORD='TU_PASSWORD' postgres14-3.3 \
  psql -U postgres -d geonlq -f /tmp/schema.sql
```

### Paso 5 — Arrancar API (cada sesión)

```bash
curl -s http://localhost:11434    # Ollama
docker start postgres14-3.3
cd ~/geonlq && source venv/bin/activate
python3 -m uvicorn src.geonlq.main:app --host 0.0.0.0 --port 8000 --reload
```

### Paso 6 — Verificar

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

Detalle: [EJECUCION_SERVICIO.md §2](./EJECUCION_SERVICIO.md#2-variante-a--python-en-el-host-venv--uvicorn).

---

## 3. WSL — Docker + Postgres ya existente (B2, ~/geonlq)

Misma BD que §2, pero la API va en contenedor con **`src/` montado**.

### Paso 1 — Sincronizar proyecto (cuando cambies algo en Windows)

```bash
rsync -av --exclude venv --exclude __pycache__ \
  "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/geonlq/" ~/geonlq/
```

### Paso 2 — `.env` para Docker

```bash
cd ~/geonlq
cp .env.docker.example .env
nano .env
```

Imprescindible (copiar de [`.env.docker.example`](../.env.docker.example)):

```env
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5434
POSTGRES_DB=geonlq
POSTGRES_USER=postgres
POSTGRES_PASSWORD=TU_PASSWORD

LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_TIMEOUT_SECONDS=180

UVICORN_LOG_LEVEL=info
```

(`LOG_LEVEL=INFO` es para la app; **uvicorn** usa `UVICORN_LOG_LEVEL=info` en minúsculas.)

**Ollama + Docker:** además del `.env`, Ollama en el host debe escuchar en `0.0.0.0:11434` (no solo `127.0.0.1`). Checklist completo: [EJECUCION_SERVICIO.md §3.4](./EJECUCION_SERVICIO.md#34-ollama-con-docker-compose-b1-y-b2).

### Paso 3 — Build (solo primera vez o si cambia `requirements.txt` / `Dockerfile`)

```bash
docker compose -f docker-compose.external-db.yml build
```

### Paso 4 — Arrancar

```bash
docker compose -f docker-compose.external-db.yml up -d
# Tras cambiar compose o .env:
docker compose -f docker-compose.external-db.yml up -d --force-recreate
```

### Paso 5 — Verificar

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
docker compose -f docker-compose.external-db.yml logs -f geonlq
```

**Ollama desde el contenedor** (después de [§3.4](./EJECUCION_SERVICIO.md#34-ollama-con-docker-compose-b1-y-b2)):

```bash
docker exec geonlq_api python -c "
import urllib.request
print(urllib.request.urlopen('http://host.docker.internal:11434', timeout=5).read().decode())
"
```

Editas código en **`~/geonlq/src/`** → `--reload` en el compose.

Detalle: [EJECUCION_SERVICIO.md §3.2 B2](./EJECUCION_SERVICIO.md#32-b2--solo-api-en-docker-postgis-en-el-servidor-recomendado-en-destino).

---

## 4. Generar paquete dist/ (imagen + src)

En tu máquina de desarrollo (WSL), **antes de copiar al servidor de producción**.

### Paso 1 — Construir imagen (si no existe o cambió requirements)

```bash
cd ~/geonlq
docker compose -f docker-compose.external-db.yml build
```

### Paso 2 — Generar `dist/`

```bash
bash scripts/build-dist.sh
```

Queda en el repo (también en D: si trabajas desde Windows):

- `dist/geonlq-latest.tar.gz`
- `dist/src/`
- `dist/docker-compose.yml` (volumen + reload)
- `dist/docker-compose.prod.yml` (volumen + workers)
- `dist/env.docker.example`, `install.sh`, `README.md`

### Paso 3 — Copia local de trabajo (opcional)

```bash
rsync -av --delete ~/geonlq/dist/ ~/geonlq-dist/
```

---

## 5. Servidor de producción — Postgres ya instalado (dist/)

### Paso 1 — Copiar paquete al servidor

Desde WSL (ajusta usuario, host y ruta):

```bash
rsync -av --delete \
  "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/geonlq/dist/" \
  usuario@servidor:/opt/geonlq/
```

O desde `~/geonlq-dist/` si ya lo generaste ahí.

**No copies `.env` con secretos** desde tu PC si no es necesario.

### Paso 2 — Configurar entorno en el servidor

```bash
ssh usuario@servidor
cd /opt/geonlq
cp env.docker.example .env
nano .env
chmod 600 .env
```

Producción típica (Postgres en el **mismo** servidor):

```env
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5432
POSTGRES_DB=nombre_bd
POSTGRES_USER=geonlq_reader
POSTGRES_PASSWORD=...
OLLAMA_BASE_URL=http://host.docker.internal:11434
UVICORN_LOG_LEVEL=info
CORS_ORIGINS=https://tu-frontend.cu
```

Usuario de BD con permiso **SELECT**. Ver [DESPLIEGUE_PRODUCCION.md §3.2](./DESPLIEGUE_PRODUCCION.md#32-crear-usuario-de-solo-lectura-recomendado-para-producción).

### Paso 3 — Instalar

```bash
chmod +x install.sh
./install.sh
```

Equivalente manual:

```bash
docker load -i geonlq-latest.tar.gz
docker compose up -d
```

Varios workers (sin `--reload`):

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Paso 4 — Verificar

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
curl -s "http://localhost:8000/api/v1/schema?refresh=true" | python3 -m json.tool
```

### Paso 5 — Arranque automático (opcional)

Unidad systemd en [EJECUCION_SERVICIO.md §3.2](./EJECUCION_SERVICIO.md#systemd--arranque-automático-b2) (`WorkingDirectory=/opt/geonlq`, `docker compose -f docker-compose.yml up -d`).

Más detalle del paquete: [dist/README.md](../dist/README.md).

---

## 6. Demo local — PostGIS en contenedor (B1)

Solo si **no** tienes Postgres. Levanta PostGIS + API:

```bash
cd ~/geonlq
cp .env.example .env
docker compose up -d          # sin --build en el día a día
curl -s http://localhost:8000/api/v1/health
```

**No uses esto en producción** si ya hay PostGIS en el servidor (conflicto puerto 5432).

---

## 7. Comandos del día a día

| Acción | Comando |
|--------|---------|
| Parar API Docker | `docker compose -f docker-compose.external-db.yml stop` o en `dist/`: `docker compose stop` |
| Reiniciar API | `docker compose ... restart geonlq` |
| Ver logs | `docker compose ... logs -f geonlq` |
| Probar dist en WSL | `cd ~/geonlq/dist && docker compose up -d --force-recreate` |
| Sincronizar repo → WSL | `rsync ... "/mnt/d/.../geonlq/" ~/geonlq/` |
| Regenerar dist | `bash ~/geonlq/scripts/build-dist.sh` |

---

## 8. Actualizar sin rebuild

| Qué cambió | Qué hacer |
|------------|-----------|
| Solo Python en `src/` | Editar y guardar (reload) o `docker compose restart` con `prod` |
| `.env` | `nano .env` + `docker compose up -d --force-recreate` |
| Tablas en PostGIS | DDL + GRANT en BD; `curl .../schema?refresh=true` o reiniciar contenedor |
| Modelo Ollama fine-tuneado | `ollama create ...` en el **host**; cambiar `LLM_MODEL` en `.env`; restart API |
| `requirements.txt` | `build` + nuevo `build-dist.sh` + `docker load` en producción |

Detalle: [EJECUCION_SERVICIO.md §3.3](./EJECUCION_SERVICIO.md#33-actualizar-producción-b2-tablas-nuevas-y-fine-tuning).

---

## 9. Problemas frecuentes

| Síntoma | Causa habitual | Solución |
|---------|----------------|----------|
| Contenedor reinicia en bucle | `LOG_LEVEL=INFO` en uvicorn | `UVICORN_LOG_LEVEL=info` en `.env` |
| `Connection refused` 5434/5432 | Postgres parado o `.env` incorrecto | `docker start ...` / revisar `POSTGRES_*` |
| Health no JSON / 500 BD | Credenciales o host mal | `host.docker.internal`, usuario/contraseña |
| Compose reconstruye siempre | Sin imagen local / `--build` | `docker load` o build una vez; evitar `--build` |
| `dist/` sin cambios en servidor | Copia antigua | `build-dist.sh` + `rsync dist/` otra vez |
| Ollama no responde desde contenedor | `localhost` en `.env` o Ollama solo en `127.0.0.1:11434` | [§3.4](./EJECUCION_SERVICIO.md#34-ollama-con-docker-compose-b1-y-b2): `OLLAMA_BASE_URL=host.docker.internal` + `OLLAMA_HOST=0.0.0.0:11434` |
| `422` Ollama no disponible | Mismo caso | Verificar con `docker exec geonlq_api python -c "…11434…"` |
| `include_geometry` ignorado / confusión API | Campo no existe en `QueryRequest` | Usar `output_format`: `geojson` \| `table` |
| `sql_generation_failed` con Ollama OK | Modelo 1.5b en CPU, SQL inválido | Logs GeoNLQ; reformular pregunta; modelo mayor; `OLLAMA_TIMEOUT_SECONDS` |

Más: [EJECUCION_SERVICIO.md §6](./EJECUCION_SERVICIO.md#6-problemas-frecuentes).

---

## 10. Otros documentos

| Documento | Contenido |
|-----------|-----------|
| [README.md](../README.md) | Inicio rápido WSL venv + enlaces |
| [EJECUCION_SERVICIO.md](./EJECUCION_SERVICIO.md) | Variantes A / B1 / B2, systemd, rebuild |
| [dist/README.md](../dist/README.md) | Paquete offline, contenido de `dist/` |
| [DESPLIEGUE_PRODUCCION.md](./DESPLIEGUE_PRODUCCION.md) | Nginx, firewall, systemd sin Docker |
| [FINE_TUNING.md](./FINE_TUNING.md) | Modelo Ollama entrenado |
| [ESCALADO.md](./ESCALADO.md) | Nuevas tablas y prompt |
