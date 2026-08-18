# MTD-NLQ — Ejecución y mantenimiento del servicio

**Servicio:** Consultas en lenguaje natural sobre Mapa Topográfico Digital  
**Base de datos:** `mtd10` (escala 1:10 000) en PostgreSQL puerto **5433**  
**Puerto API:** **8001** (para no chocar con GeoNLQ en 8000)

Guía de arranque diario. Para la primera instalación, ver [GUIA_USO_SERVICIO.md](GUIA_USO_SERVICIO.md).

---

## Índice

1. [Variantes de ejecución](#1-variantes-de-ejecución)
2. [Variante A — Python en el host](#2-variante-a--python-en-el-host)
3. [Variante B — Docker (BD externa)](#3-variante-b--docker-bd-externa)
4. [Ollama desde Docker](#4-ollama-desde-docker)
5. [Arranque automático tras reinicio](#5-arranque-automático-tras-reinicio)
6. [Cuándo rebuild de Docker](#6-cuándo-rebuild-de-docker)
7. [Problemas frecuentes](#7-problemas-frecuentes)

---

## 1. Variantes de ejecución

| | **A — venv + uvicorn** | **B — Docker Compose** |
|---|---|---|
| API | Proceso Python en WSL/Linux | Contenedor `mtdnlq_api` |
| PostgreSQL | **mtd10** ya existente en `:5433` | Igual (BD en el host) |
| Ollama | `http://localhost:11434` | `http://host.docker.internal:11434` |
| Cambios en `src/` | `--reload` automático | Volumen montado + `--reload` |
| Ideal para | Desarrollo WSL | Servidor sin Python instalado |

MTD-NLQ **no levanta PostgreSQL**: usa la BD `mtd10` que ya tengas cargada.

---

## 2. Variante A — Python en el host

### Arrancar (cada sesión)

```bash
# 1. Verificar dependencias
curl -s http://localhost:11434          # Ollama
docker ps | grep postgres               # o servicio PostgreSQL en :5433

# 2. API
cd ~/mtdnlq
source venv/bin/activate
python3 -m uvicorn mtdnlq.main:app --host 0.0.0.0 --port 8001 --reload
```

URLs: `http://localhost:8001` · Swagger: `/docs`

### Parar

- `Ctrl+C` en la terminal de uvicorn, o:
  ```bash
  pkill -f "uvicorn mtdnlq.main"
  ```

### Verificación

```bash
curl -s http://localhost:8001/api/v1/health | python3 -m json.tool
curl -s "http://localhost:8001/api/v1/schema?refresh=true" | python3 -m json.tool
```

---

## 3. Variante B — Docker (BD externa)

Archivo: `docker-compose.external-db.yml` — solo contenedor `mtdnlq_api`.

### Arrancar

```bash
cd ~/mtdnlq
docker compose -f docker-compose.external-db.yml up -d
```

### Parar / reiniciar

```bash
docker compose -f docker-compose.external-db.yml stop
docker compose -f docker-compose.external-db.yml up -d
docker compose -f docker-compose.external-db.yml restart mtdnlq
```

### Logs

```bash
docker compose -f docker-compose.external-db.yml logs -f mtdnlq
```

### Variables clave en `.env`

```env
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5433
POSTGRES_DB=mtd10
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
MTDNLQ_HOST_PORT=8001
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Lista completa de esquemas: [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md).

---

## 4. Ollama desde Docker

Dos condiciones obligatorias cuando la API corre en contenedor:

**A)** En `.env` del contenedor:
```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```
No uses `localhost` dentro del contenedor.

**B)** Ollama debe escuchar en `0.0.0.0:11434` (no solo `127.0.0.1`):

```bash
ss -tlnp | grep 11434
# Debe mostrar *:11434 o 0.0.0.0:11434
```

Con systemd:
```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '%s\n' '[Service]' 'Environment="OLLAMA_HOST=0.0.0.0:11434"' \
  | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

Verificar desde el contenedor:
```bash
docker exec mtdnlq_api python -c "
import urllib.request
print(urllib.request.urlopen('http://host.docker.internal:11434', timeout=5).read().decode())
"
```

---

## 5. Arranque automático tras reinicio

### Docker (recomendado en servidor)

El compose ya incluye `restart: unless-stopped`. Opcional — unidad systemd:

```ini
# /etc/systemd/system/mtdnlq-docker.service
[Unit]
Description=MTD-NLQ API (Docker, mtd10 externo)
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/mtdnlq
ExecStart=/usr/bin/docker compose -f docker-compose.external-db.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.external-db.yml stop

[Install]
WantedBy=multi-user.target
```

### venv (desarrollo)

```ini
# /etc/systemd/system/mtdnlq-dev.service
[Unit]
Description=MTD-NLQ (venv, mtd10)
After=network.target

[Service]
Type=simple
User=frank
WorkingDirectory=/home/frank/mtdnlq
EnvironmentFile=/home/frank/mtdnlq/.env
ExecStart=/home/frank/mtdnlq/venv/bin/python3 -m uvicorn mtdnlq.main:app \
    --host 0.0.0.0 --port 8001
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## 6. Cuándo rebuild de Docker

| Acción | ¿Rebuild? |
|--------|-----------|
| `docker compose up -d` (imagen ya existe) | No |
| Cambios solo en `src/` | No |
| Cambio en `requirements.txt` o `Dockerfile` | Sí |
| Primer despliegue en máquina nueva | Sí |

```bash
docker compose -f docker-compose.external-db.yml build mtdnlq
docker compose -f docker-compose.external-db.yml up -d
```

---

## 7. Problemas frecuentes

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Health 500 | Postgres no accesible en 5433 | Verificar pgAdmin / `docker start` del contenedor PG |
| 0 tablas en `/schema` | `ALLOWED_SCHEMAS` incompleto | Ver [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md) |
| 422 Ollama no disponible | URL o binding incorrecto | §4 de esta guía |
| 500 `db_error` | Tabla/columna inexistente | Revisar `sql` en respuesta; consultar `/api/v1/schema` |
| Timeout ~2 min | Modelo en CPU | Normal; `OLLAMA_TIMEOUT_SECONDS=180` |
| CORS en navegador | Origen no permitido | `CORS_ORIGINS` o proxy backend (ver [INTEGRACION_WEB_QGIS.md](INTEGRACION_WEB_QGIS.md)) |

---

## Referencias

- [GUIA_USO_SERVICIO.md](GUIA_USO_SERVICIO.md) — instalación inicial
- [DESPLIEGUE_PRODUCCION.md](DESPLIEGUE_PRODUCCION.md) — Nginx, seguridad, producción
- [INTEGRACION_WEB_QGIS.md](INTEGRACION_WEB_QGIS.md) — clientes web y QGIS
