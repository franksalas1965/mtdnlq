# GeoNLQ — Cómo ejecutar y mantener el servicio activo

**Versión:** 1.1  
**Última actualización:** 2026-08-09

Esta guía describe **dos formas** de levantar GeoNLQ en Linux (incluido WSL en Windows 10/11).

**Guía paso a paso consolidada (recomendada):** [GUIA_PASOS_DESPLIEGUE.md](./GUIA_PASOS_DESPLIEGUE.md).

Para despliegue en producción (Nginx, firewall, usuario de BD de solo lectura), ver [DESPLIEGUE_PRODUCCION.md](./DESPLIEGUE_PRODUCCION.md).

---

## Índice

1. [Elegir variante](#1-elegir-variante)
2. [Variante A — Python en el host (venv + uvicorn)](#2-variante-a--python-en-el-host-venv--uvicorn)
3. [Variante B — Docker Compose](#3-variante-b--docker-compose)
   - [B1 — PostGIS incluido en Compose (demo/desarrollo)](#31-b1--postgis-incluido-en-compose-demodesarrollo)
   - [B2 — Solo API en Docker; PostGIS en el servidor (recomendado en destino)](#32-b2--solo-api-en-docker-postgis-en-el-servidor-recomendado-en-destino)
   - [Ollama con Docker Compose (B1 y B2)](#34-ollama-con-docker-compose-b1-y-b2)
   - [Actualizar producción (tablas nuevas y fine-tuning)](#actualizar-producción-b2-tablas-nuevas-y-fine-tuning)
4. [Mantener el servicio activo tras reinicio](#4-mantener-el-servicio-activo-tras-reinicio)
5. [Cuándo hace falta rebuild de Docker](#5-cuándo-hace-falta-rebuild-de-docker)
6. [Problemas frecuentes](#6-problemas-frecuentes)
7. [Resumen rápido](#7-resumen-rápido)

---

## 1. Elegir variante

| | **Variante A** — venv + uvicorn | **Variante B** — Docker Compose |
|---|---|---|
| **API GeoNLQ** | Proceso Python en WSL/servidor | Contenedor `geonlq_api` |
| **PostgreSQL/PostGIS** | Contenedor o servidor **aparte** (ej. puerto 5434) | Contenedor `geonlq_postgis` (puerto **5432** por defecto) |
| **Ollama** | En el host: `http://localhost:11434` | En el host; desde el contenedor ver [§3.4](#34-ollama-con-docker-compose-en-wsl) |
| **Cambios en código** | `--reload` sin rebuild | Volumen `./src` + `--reload` en compose (sin rebuild) |
| **Ideal para** | Desarrollo WSL, BD ya existente, producción con systemd | Servidor **sin Python** instalado; ver [B2](#32-b2--solo-api-en-docker-postgis-en-el-servidor-recomendado-en-destino) |
| **Build Docker de la API** | No aplica | Solo la **primera vez** o si cambia `Dockerfile` / `requirements.txt` |

**Variante B tiene dos modos:** **B1** (`docker-compose.yml`) levanta PostGIS en contenedor; **B2** (`docker-compose.external-db.yml`) solo la API y usa el PostgreSQL/PostGIS **ya instalado** en el servidor (parámetros en `.env.docker.example`).

No mezcles puertos: si la API usa `DATABASE_URL=...:5434` pero solo tienes PostGIS de Compose en **5432**, el health fallará con `Connection refused`.

---

## 2. Variante A — Python en el host (venv + uvicorn)

Flujo recomendado en **WSL + Ollama + PostgreSQL en Docker** (entorno Smartgeo con contenedor `postgres14-3.3` en el puerto **5434**). La API **no** se containeriza; no hay `docker build` de GeoNLQ.

### 2.1 Requisitos

- WSL Ubuntu (o Linux) con Python 3.11+
- Docker con PostgreSQL/PostGIS accesible en un puerto (ej. **5434**)
- Ollama en el host (opcional si usas OpenAI/Anthropic en `.env`)

### 2.2 Instalación (solo la primera vez)

```bash
# Copiar proyecto (ejemplo desde disco Windows)
cp -r "/mnt/d/ruta/al/proyecto/geonlq" ~/geonlq
cd ~/geonlq

sudo apt install -y python3.12-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Editar .env — ejemplo con Postgres en 5434:
# DATABASE_URL=postgresql+psycopg2://postgres:TU_PASSWORD@localhost:5434/geonlq
# LLM_PROVIDER=ollama
# LLM_MODEL=qwen2.5-coder:1.5b
# OLLAMA_BASE_URL=http://localhost:11434
```

Esquema en la BD (solo la primera vez en esa base):

```bash
docker start postgres14-3.3   # o el nombre de tu contenedor
docker cp ~/geonlq/docs/schema/001_initial_schema.sql postgres14-3.3:/tmp/schema.sql
docker exec -e PGPASSWORD='TU_PASSWORD' postgres14-3.3 \
  psql -U postgres -d geonlq -f /tmp/schema.sql
```

### 2.3 Arrancar el servicio (cada sesión de trabajo)

**1. Dependencias:**

```bash
curl -s http://localhost:11434          # Ollama (si LLM_PROVIDER=ollama)
docker ps | grep postgres               # Postgres en marcha
docker start postgres14-3.3             # si está parado
```

**2. API:**

```bash
cd ~/geonlq
source venv/bin/activate
python3 -m uvicorn src.geonlq.main:app --host 0.0.0.0 --port 8000 --reload
```

URL: `http://localhost:8000` — documentación OpenAPI en `/docs`.

### 2.4 Parar el servicio

- En la terminal de uvicorn: `Ctrl+C`
- O desde otra terminal:

```bash
pkill -f "uvicorn src.geonlq"
```

PostgreSQL y Ollama pueden seguir corriendo.

### 2.5 Verificación

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
curl -s http://localhost:8000/api/v1/schema | python3 -m json.tool
```

---

## 3. Variante B — Docker Compose

No hace falta instalar Python en el servidor destino: la API corre dentro de la imagen Docker. Elige **B1** (BD en contenedor) o **B2** (BD del servidor).

### 3.1 B1 — PostGIS incluido en Compose (demo/desarrollo)

Un solo `docker-compose.yml` levanta **PostGIS** (`geonlq_postgis`, puerto **5432**) y la **API** (`geonlq_api`, puerto **8000**). El init del volumen ejecuta los SQL en `docs/schema/` la primera vez que se crea el volumen `postgis_data`.

#### Instalación (solo la primera vez)

```bash
cd ~/geonlq   # o la ruta del proyecto
cp .env.example .env
```

Editar `.env`. Para Compose, la API dentro de la red Docker usa la URL del servicio `postgis` (ya definida en `docker-compose.yml` como `DATABASE_URL` de entorno). Para **Ollama en el host WSL**, configura en `.env`:

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

En Linux/WSL puede ser necesario añadir en `docker-compose.yml` bajo el servicio `geonlq`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Primera construcción y arranque (puede tardar en descargar la imagen base de Python):

```bash
docker-compose build    # opcional: compose también construye en el primer up
docker-compose up -d
docker-compose ps
```

#### Arrancar sin rebuild (uso habitual)

Si la imagen ya existe y no cambiaste `Dockerfile` ni `requirements.txt`:

```bash
cd ~/geonlq
docker compose up -d          # NO uses --build salvo que quieras reconstruir
# o, si los contenedores ya existen:
docker compose start
```

#### Parar

```bash
docker compose stop           # conserva contenedores, red y volúmenes
# Evitar en desarrollo con datos que quieras conservar:
# docker compose down -v      # borra el volumen postgis_data → BD vacía otra vez
```

#### Verificación (B1)

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
docker compose logs -f geonlq
```

---

### 3.2 B2 — Solo API en Docker; PostGIS en el servidor (recomendado en destino)

Archivos:

| Archivo | Función |
|---------|---------|
| `docker-compose.external-db.yml` | Solo servicio `geonlq_api`, `restart: unless-stopped`, sin `--reload` |
| `.env.docker.example` | Plantilla de parámetros (BD, LLM, puerto, workers) |

En el servidor destino **no se instala Python**; solo Docker y PostgreSQL/PostGIS (ya operativos).

#### Requisitos en el servidor destino

- Docker Engine + plugin Compose (`docker compose version`)
- PostgreSQL 14+ con PostGIS 3.x (`SELECT PostGIS_Version();`)
- Usuario de BD con permiso **SELECT** sobre las tablas que consultará GeoNLQ (ver [DESPLIEGUE_PRODUCCION.md §3.2](./DESPLIEGUE_PRODUCCION.md#32-crear-usuario-de-solo-lectura-recomendado-para-producción))
- (Opcional) Ollama en el host si `LLM_PROVIDER=ollama`

#### Parámetros configurables (`.env`)

Copiar la plantilla y editar:

```bash
cd /opt/geonlq   # ruta de despliegue
cp .env.docker.example .env
chmod 600 .env
nano .env
```

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `POSTGRES_HOST` | Host visto **desde el contenedor** | `host.docker.internal` (Postgres en el mismo Linux) o IP/FQDN remoto |
| `POSTGRES_PORT` | Puerto PostgreSQL | `5432` (en WSL con Postgres en Docker del host, a menudo **`5434`**) |
| `POSTGRES_DB` | Nombre de la base | `catastro`, `geonlq` |
| `POSTGRES_USER` | Usuario | `geonlq_reader` |
| `POSTGRES_PASSWORD` | Contraseña | *(segura)* |
| `GEONLQ_HOST_PORT` | Puerto HTTP en el host | `8000` |
| `UVICORN_WORKERS` | Procesos worker | `2` |
| `LLM_PROVIDER` / `LLM_MODEL` | Proveedor LLM | `ollama`, `qwen2.5-coder:1.5b` |
| `OLLAMA_BASE_URL` | Ollama desde el contenedor | `http://host.docker.internal:11434` (ver [§3.4](#34-ollama-con-docker-compose-b1-y-b2)) |
| `OLLAMA_TIMEOUT_SECONDS` | Timeout HTTP al LLM (CPU lenta) | `180` (opcional; default en código) |
| `CORS_ORIGINS` | Frontends permitidos | dominios reales, no `*` en prod |

La URL de conexión se arma en Compose:

`postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}`

Si la contraseña tiene caracteres especiales (`@`, `#`, `%`), codifícalos en URL o define solo `DATABASE_URL` en `.env` y **elimina** el bloque `environment: DATABASE_URL` de `docker-compose.external-db.yml`.

**Postgres en el mismo servidor:** deja `POSTGRES_HOST=host.docker.internal`. El compose ya incluye `extra_hosts: host.docker.internal:host-gateway` (Docker 20.10+ en Linux).

**Postgres en otro host:** pon `POSTGRES_HOST=192.168.x.x` y asegura `listen_addresses` y `pg_hba.conf` para la IP del servidor Docker.

Comprobar desde el host (antes de levantar la API):

```bash
psql "postgresql://geonlq_reader:PASSWORD@localhost:5432/NOMBRE_BD" -c "SELECT PostGIS_Version();"
```

#### Despliegue (primera vez)

```bash
cd /opt/geonlq
docker compose -f docker-compose.external-db.yml build
docker compose -f docker-compose.external-db.yml up -d
docker compose -f docker-compose.external-db.yml ps
docker compose -f docker-compose.external-db.yml logs -f geonlq
```

#### Arrancar / parar (día a día, sin rebuild)

```bash
cd /opt/geonlq
docker compose -f docker-compose.external-db.yml up -d
docker compose -f docker-compose.external-db.yml stop
docker compose -f docker-compose.external-db.yml restart geonlq
```

Rebuild solo si cambia `requirements.txt` o `Dockerfile`:

```bash
docker compose -f docker-compose.external-db.yml build geonlq
docker compose -f docker-compose.external-db.yml up -d
```

#### Ollama y servicios en el host (B1 y B2)

Resumen: [§3.4](#34-ollama-con-docker-compose-b1-y-b2) (checklist completo).

- Ollama en el **host**: `curl http://localhost:11434`
- En `.env` del contenedor: **`OLLAMA_BASE_URL=http://host.docker.internal:11434`**
- Ollama debe escuchar en **`*:11434`** (`OLLAMA_HOST=0.0.0.0:11434`), no solo `127.0.0.1`

### 3.4 Ollama con Docker Compose (B1 y B2)

Cuando la **API corre en contenedor** y **Ollama en el host** (systemd o manual), hay **dos condiciones** obligatorias. Si fallan, verás `422` con `detail` tipo *«El proveedor LLM ollama no está disponible»* o `Connection refused` al probar desde el contenedor.

##### A) URL en `.env` (vista desde el contenedor)

En **`~/geonlq/.env`** o **`/opt/geonlq/.env`** (según [`.env.docker.example`](../.env.docker.example)):

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

- **No uses** `http://localhost:11434` en `.env` del contenedor: `localhost` dentro del contenedor **no** es el host WSL/Linux.
- `docker-compose.external-db.yml` ya incluye `extra_hosts: host.docker.internal:host-gateway` (Docker 20.10+ en Linux/WSL).

##### B) Ollama debe escuchar fuera de `127.0.0.1`

Por defecto Ollama suele enlazar solo **`127.0.0.1:11434`**. El contenedor llega al host por otra IP → **`Connection refused`** aunque en el host `curl http://127.0.0.1:11434` funcione.

Comprobar en el **host**:

```bash
ss -tlnp | grep 11434
```

| Salida | Significado |
|--------|-------------|
| `127.0.0.1:11434` | Solo loopback → **hay que configurar `OLLAMA_HOST`** (paso siguiente) |
| `*:11434` o `0.0.0.0:11434` | Correcto para Docker |

**Con systemd (recomendado en producción):**

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '%s\n' '[Service]' 'Environment="OLLAMA_HOST=0.0.0.0:11434"' \
  | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
ss -tlnp | grep 11434
```

> **Seguridad:** `0.0.0.0:11434` expone Ollama en todas las interfaces del servidor. En producción, restringe con firewall (solo localhost + red Docker) o coloca Ollama en red interna. En laptop de desarrollo suele ser aceptable.

##### C) Verificar desde el contenedor `geonlq_api`

La imagen incluye **`curl`** tras rebuild del `Dockerfile`. Si aún no reconstruiste:

```bash
docker exec geonlq_api python -c "
import urllib.request
print(urllib.request.urlopen('http://host.docker.internal:11434', timeout=5).read().decode())
"
```

Debe imprimir **`Ollama is running`**.

Si falla con `host.docker.internal` pero Ollama escucha en `0.0.0.0:11434`, prueba la IP del gateway Docker:

```bash
GW=$(docker exec geonlq_api ip route | awk '/default/ {print $3}')
echo "Gateway: $GW"
docker exec geonlq_api python -c "
import urllib.request
print(urllib.request.urlopen('http://${GW}:11434', timeout=5).read().decode())
"
```

Si solo funciona con `$GW`, pon en `.env`: `OLLAMA_BASE_URL=http://<GW>:11434` y `docker compose -f docker-compose.external-db.yml up -d --force-recreate`.

##### D) Verificar Postgres desde el contenedor (B2)

Mismo patrón: `POSTGRES_HOST=host.docker.internal` y el puerto real del host (ej. **5434** en entorno Smartgeo WSL):

```bash
docker exec geonlq_api python -c "
import socket
s = socket.create_connection(('host.docker.internal', 5434), timeout=5)
print('OK: Postgres alcanzable en 5434')
s.close()
"
```

##### E) Consulta de prueba (API)

Cuerpo JSON válido (`QueryRequest` — **no** existe `include_geometry`; usa `output_format`):

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Dame los puentes con carga maxima de al menos 20 toneladas con el nombre de la via","output_format":"table","max_results":100}' \
  | python3 -m json.tool
```

Errores frecuentes en la respuesta:

| HTTP / `detail.error` | Causa |
|----------------------|--------|
| `422` `sql_generation_failed`, `detail.detail` menciona Ollama | Pasos A–C incompletos |
| `422` tras varios minutos | Modelo pequeño en CPU; revisar logs `Validación SQL falló`; ver [§6](#6-problemas-frecuentes) |
| `500` BD | `POSTGRES_*` incorrecto o pg_hba / firewall |

##### F) Health y esquema (B2)

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
curl -s http://localhost:8000/api/v1/schema | python3 -m json.tool
```

#### Actualizar producción (B2): tablas nuevas y fine-tuning

Sí, en la variante B2 puedes ampliar tablas y desplegar un modelo fine-tuneado **sin reinstalar Python** en el servidor. Lo que cambia y dónde vive cada pieza:

| Cambio | Dónde se aplica | ¿Rebuild imagen GeoNLQ? |
|--------|-----------------|-------------------------|
| Nuevas tablas / columnas en PostGIS | Base de datos del servidor (SQL + permisos) | **No** |
| Comentarios en columnas (mejor SQL del LLM) | `COMMENT ON` en PostgreSQL | **No** |
| Nuevo modelo Ollama (`geonlq-sql`, etc.) | **Host** (Ollama), no dentro del contenedor API | **No** |
| Cambiar modelo en uso | `.env` → `LLM_MODEL=...` + reinicio contenedor | **No** |
| Cambios en código Python o `requirements.txt` | Proyecto en `/opt/geonlq` | **Sí** (`build` + `up -d`) |
| Regenerar datos / entrenar QLoRA | Máquina de desarrollo o Colab ([FINE_TUNING.md](./FINE_TUNING.md)) | **No** en el servidor de prod |

GeoNLQ **no lleva el modelo LLM dentro de la imagen Docker**: el contenedor solo llama a Ollama (u OpenAI/Anthropic) según `.env`. El fine-tuning produce un artefacto para **Ollama en el host**.

##### Ampliar tablas disponibles para el servicio

1. **En PostgreSQL** (como siempre en tu servidor destino):
   - Ejecutar migraciones DDL (`CREATE TABLE`, `ALTER`, índices espaciales, etc.).
   - Conceder **SELECT** al usuario que usa GeoNLQ (`geonlq_reader` o el de tu `.env`).
   - Opcional pero recomendado: `COMMENT ON TABLE/COLUMN` para que el prompt del LLM sea más claro ([DESPLIEGUE_PRODUCCION.md §13](./DESPLIEGUE_PRODUCCION.md#13-optimizar-el-esquema-para-el-llm)).

2. **En GeoNLQ** el esquema se **lee en vivo** desde PostGIS (`schema_inspector`); no hace falta copiar SQL de esquema al contenedor salvo que uses B1 con init de volumen.

3. **Refrescar la caché** del esquema en memoria:
   - Esperar `SCHEMA_CACHE_TTL` (por defecto 300 s en `.env`), **o**
   - Forzar recarga: `curl -s "http://localhost:8000/api/v1/schema?refresh=true"`, **o**
   - Con varios workers (`UVICORN_WORKERS>1`), lo más fiable:  
     `docker compose -f docker-compose.external-db.yml restart geonlq`

4. Comprobar: `curl -s http://localhost:8000/api/v1/schema | python3 -m json.tool` (deben aparecer las tablas nuevas).

5. Si además quieres **mejor precisión** con tablas nuevas, en desarrollo regenera datos y re-entrena ([FINE_TUNING.md](./FINE_TUNING.md), [ESCALADO.md](./ESCALADO.md)); el despliegue del modelo es el paso siguiente.

##### Desplegar un modelo fine-tuneado (Ollama en el host)

Entrenamiento y export GGUF: en tu PC/WSL/Colab, no es obligatorio en el servidor de producción.

En el **servidor de producción**:

```bash
# 1. Copiar el GGUF (ejemplo)
scp modelo/geonlq-sql.gguf usuario@servidor:/tmp/

# 2. Crear o actualizar el modelo en Ollama (en el host)
cd /opt/geonlq/modelos_locales/ollama   # o donde tengas el Modelfile
# Ajustar Modelfile para apuntar al .gguf en /tmp o ruta definitiva
ollama create geonlq-sql -f Modelfile
ollama list | grep geonlq-sql

# 3. Apuntar GeoNLQ al nuevo modelo
nano /opt/geonlq/.env
# LLM_MODEL=geonlq-sql
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://host.docker.internal:11434

# 4. Reiniciar solo la API (sin rebuild)
cd /opt/geonlq
docker compose -f docker-compose.external-db.yml restart geonlq
```

Verificación: consultas de prueba en [FINE_TUNING.md §8](./FINE_TUNING.md#8-paso-6--verificar-el-modelo-entrenado).

##### Actualizar el código de la API GeoNLQ

```bash
cd /opt/geonlq
git pull   # o rsync/scp de src/ desde tu entorno de desarrollo
docker compose -f docker-compose.external-db.yml build geonlq
docker compose -f docker-compose.external-db.yml up -d
```

**Paquete offline sin rebuild en producción:** carpeta [`dist/`](../dist/) con imagen `geonlq-latest.tar.gz`, `docker-compose.yml` y `install.sh` (generar en WSL con `scripts/build-dist.sh`).

##### Ficheros que suele tener sentido sincronizar al servidor

| Fichero / carpeta | Cuándo |
|-------------------|--------|
| `.env` | Credenciales, `LLM_MODEL`, CORS, TTL |
| `src/` (vía rebuild) | Correcciones o features de la API |
| `modelos_locales/ollama/Modelfile` | Crear/actualizar modelo Ollama |
| `*.gguf` (Ollama) | Tras fine-tuning; no va dentro de la imagen Docker |
| `docs/schema/*.sql` | Referencia/migraciones manuales en el **Postgres del host**, no en el contenedor API |

No es necesario copiar datasets de entrenamiento ni scripts de Colab al servidor de producción salvo que quieras entrenar allí (no recomendado sin GPU).

#### systemd — arranque automático (B2)

```ini
# /etc/systemd/system/geonlq-docker.service
[Unit]
Description=GeoNLQ API (Docker, PostGIS externo)
After=docker.service network-online.target postgresql.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/geonlq
ExecStart=/usr/bin/docker compose -f docker-compose.external-db.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.external-db.yml stop
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable geonlq-docker
sudo systemctl start geonlq-docker
```

Coloca Nginx delante según [DESPLIEGUE_PRODUCCION.md §9](./DESPLIEGUE_PRODUCCION.md#9-proxy-inverso-con-nginx).

---

## 4. Mantener el servicio activo tras reinicio

### Variante A — desarrollo en WSL

| Componente | Arranque manual típico |
|---|---|
| Ollama | `systemctl start ollama` o servicio instalado por el instalador oficial |
| Postgres Docker | `docker start postgres14-3.3` (o `--restart unless-stopped` al crear el contenedor) |
| GeoNLQ | Terminal con uvicorn, o unidad systemd (ver abajo) |

**Opcional — systemd en Linux/WSL2** (ruta de ejemplo `~/geonlq` o `/opt/geonlq`):

```ini
# /etc/systemd/system/geonlq-dev.service (ejemplo; ajustar User y rutas)
[Unit]
Description=GeoNLQ (venv)
After=network.target docker.service

[Service]
Type=simple
User=frank
WorkingDirectory=/home/frank/geonlq
EnvironmentFile=/home/frank/geonlq/.env
ExecStart=/home/frank/geonlq/venv/bin/python3 -m uvicorn src.geonlq.main:app \
    --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable geonlq-dev
sudo systemctl start geonlq-dev
```

En **producción** usa la unidad completa de [DESPLIEGUE_PRODUCCION.md §8](./DESPLIEGUE_PRODUCCION.md#8-ejecutar-el-servicio-con-systemd) (`User=geonlq`, `--workers 2`, sin `--reload`).

### Variante B — Docker Compose

**B2 (servidor destino):** `restart: unless-stopped` ya está en `docker-compose.external-db.yml`, o usa la unidad `geonlq-docker.service` de [§3.2](#systemd--arranque-automático-b2).

**B1:** añadir `restart: unless-stopped` en `docker-compose.yml` si lo deseas.

Tras reinicio del host:

```bash
cd /opt/geonlq && docker compose -f docker-compose.external-db.yml up -d
# B1: docker compose up -d
```

Docker Desktop / servicio `docker` debe estar habilitado al inicio del sistema.

---

## 5. Cuándo hace falta rebuild de Docker

Solo aplica a **Variante B**.

| Acción | ¿Rebuild? |
|---|---|
| `docker-compose up -d` (imagen ya construida) | No |
| Cambios solo en `src/` (compose monta `./src` y usa `--reload`) | No |
| Cambio en `requirements.txt` o `Dockerfile` | Sí: `docker-compose build geonlq && docker-compose up -d` |
| `docker-compose up --build` | Sí (forzado) |
| `docker system prune -a` o borrar imágenes | Sí (próximo up construye de nuevo) |
| Primer despliegue en máquina nueva | Sí (una vez) |

Mensajes como `Creating network "geonlq_default"` y `Creating volume "geonlq_postgis_data"` indican **primer arranque** de ese proyecto Compose en esa máquina, no un rebuild diario.

---

## 6. Problemas frecuentes

### `Connection refused` en puerto 5434

- La API (Variante A) apunta a `localhost:5434` pero Postgres no está levantado o usa otro puerto.
- Comprobar: `docker ps`, `ss -tlnp | grep 543`
- Solución: `docker start <contenedor>` **o** cambiar `DATABASE_URL` al puerto correcto (5432 si usas Compose).

### Health devuelve error 500 con traceback de SQLAlchemy

- Misma causa: BD inaccesible. El endpoint `/health` intenta cargar el esquema; sin conexión falla.
- Arreglar Postgres y `DATABASE_URL`; reiniciar uvicorn o `docker-compose restart geonlq`.

### Compose reconstruye siempre

- Comprobar: `docker images | grep geonlq`
- No usar `--build` en el día a día.
- No ejecutar `docker-compose down -v` si quieres conservar datos y evitar sensación de “instalación nueva”.

### Conflicto de puertos

- Compose expone PostGIS en **5432**. Si ya tienes otro Postgres en 5432, cambia en `docker-compose.yml` por ejemplo `"5433:5432"` y ajusta `DATABASE_URL` en el servicio `geonlq`.

### Ollama: `Connection refused` desde el contenedor GeoNLQ

- **Síntoma:** `docker exec geonlq_api … host.docker.internal:11434` → `Connection refused`; o API `422` con *Ollama no está disponible*.
- **Causa 1:** `OLLAMA_BASE_URL=http://localhost:11434` en `.env` → corregir a `host.docker.internal` ([§3.4](#34-ollama-con-docker-compose-b1-y-b2)).
- **Causa 2:** Ollama solo en `127.0.0.1:11434` (`ss -tlnp | grep 11434`) → override systemd `OLLAMA_HOST=0.0.0.0:11434` y `systemctl restart ollama`.

### Ollama: el host responde pero la API devuelve `sql_generation_failed`

- **Causa:** el LLM no generó SQL válido en 3 intentos (modelo pequeño en CPU, pregunta ambigua).
- **Acción:** revisar logs del contenedor (`docker compose logs geonlq`); respuesta 422 incluye `detail.detail` si está configurado; probar pregunta alineada con ejemplos del prompt; considerar modelo mayor o `OLLAMA_TIMEOUT_SECONDS=180`.
- **Nota:** errores de **ejecución** en PostGIS (columna inexistente) son HTTP **500** `db_error`, no reintentos automáticos de SQL.

### Campo JSON `include_geometry` en `/api/v1/query`

- **No existe** en la API. Usar `output_format`: `"geojson"` | `"table"`, y opcionalmente `max_results`, `explain` (ver `src/geonlq/api/schemas.py`).

---

## 7. Resumen rápido

**Variante A — activar todo (WSL, desarrollo):**

```bash
docker start postgres14-3.3
curl -s http://localhost:11434 >/dev/null && echo "Ollama OK"
cd ~/geonlq && source venv/bin/activate
python3 -m uvicorn src.geonlq.main:app --host 0.0.0.0 --port 8000 --reload
```

**Variante B2 — servidor destino (PostGIS ya instalado, sin Python en el host):**

```bash
cd /opt/geonlq
cp .env.docker.example .env   # y editar POSTGRES_* / LLM
docker compose -f docker-compose.external-db.yml up -d
curl -s http://localhost:8000/api/v1/health
```

**Variante B1 — demo con PostGIS en contenedor:**

```bash
curl -s http://localhost:11434 >/dev/null && echo "Ollama OK"
cd ~/geonlq && docker compose up -d
curl -s http://localhost:8000/api/v1/health
```

**Documentos relacionados**

- [README.md](../README.md) — inicio rápido WSL y Docker Compose
- [DESPLIEGUE_PRODUCCION.md](./DESPLIEGUE_PRODUCCION.md) — producción con systemd, Nginx y seguridad
