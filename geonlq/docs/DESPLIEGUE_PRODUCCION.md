# GeoNLQ — Guía de Despliegue en Producción

**Versión:** 1.0  
**Servicio:** GeoNLQ FastAPI — Consultas en Lenguaje Natural sobre PostGIS  
**Última actualización:** 2026-08-09

---

## Índice

> Para desarrollo en WSL o Docker Compose (dos variantes de ejecución), ver [EJECUCION_SERVICIO.md](./EJECUCION_SERVICIO.md).

1. [Requisitos del servidor](#1-requisitos-del-servidor)
2. [Instalación de dependencias del sistema](#2-instalación-de-dependencias-del-sistema)
3. [Configuración de la base de datos](#3-configuración-de-la-base-de-datos)
4. [Instalación del servicio](#4-instalación-del-servicio)
5. [Variables de entorno (.env)](#5-variables-de-entorno-env)
6. [Configuración de Ollama (LLM local)](#6-configuración-de-ollama-llm-local)
7. [Alternativa: OpenAI o Anthropic (API en la nube)](#7-alternativa-openai-o-anthropic-api-en-la-nube)
8. [Ejecutar el servicio con systemd](#8-ejecutar-el-servicio-con-systemd)
9. [Proxy inverso con Nginx](#9-proxy-inverso-con-nginx)
10. [Verificación del servicio](#10-verificación-del-servicio)
11. [Seguridad en producción](#11-seguridad-en-producción)
12. [Mantenimiento y actualizaciones](#12-mantenimiento-y-actualizaciones)
13. [Optimizar el esquema para el LLM](#13-optimizar-el-esquema-para-el-llm)

---

## 1. Requisitos del servidor

| Componente | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 núcleos | 8+ núcleos |
| RAM | 8 GB | 16 GB (con Ollama local) |
| Disco | 20 GB | 50 GB |
| SO | Ubuntu 22.04 LTS | Ubuntu 22.04 / 24.04 LTS |
| Python | 3.11+ | 3.12 |
| PostgreSQL | 14+ con PostGIS 3.x | 16 + PostGIS 3.4 |
| GPU (Ollama) | Opcional | NVIDIA con CUDA (reduce tiempos 10×) |

> **Nota sobre GPU:** Sin GPU, el modelo `qwen2.5-coder:1.5b` tarda 20–90 segundos por consulta en CPU. Con una GPU NVIDIA modesta (RTX 3060 o similar) baja a 2–5 segundos.

---

## 2. Instalación de dependencias del sistema

```bash
# Actualizar el sistema
sudo apt update && sudo apt upgrade -y

# Python 3.12 y herramientas
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
    build-essential libpq-dev git curl nginx

# Verificar
python3.12 --version   # Python 3.12.x
psql --version         # psql (PostgreSQL) 14.x o superior
```

---

## 3. Configuración de la base de datos

### 3.1 PostgreSQL + PostGIS (si no está instalado)

```bash
# Instalar PostgreSQL 16 + PostGIS
sudo apt install -y postgresql-16 postgresql-16-postgis-3

# Iniciar el servicio
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### 3.2 Crear usuario de solo lectura (recomendado para producción)

```bash
sudo -u postgres psql <<'SQL'
-- Crear usuario de solo lectura
CREATE USER geonlq_reader WITH PASSWORD 'contraseña_segura_aqui';

-- Conceder acceso a la base de datos de producción
GRANT CONNECT ON DATABASE nombre_base_datos TO geonlq_reader;
GRANT USAGE ON SCHEMA public TO geonlq_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO geonlq_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO geonlq_reader;
SQL
```

> **Importante:** El usuario de producción debe tener solo permisos SELECT. GeoNLQ genera SQL dinámicamente; usar el superusuario `postgres` en producción es un riesgo de seguridad.

### 3.3 Verificar que PostGIS está habilitado

```bash
sudo -u postgres psql -d nombre_base_datos -c "SELECT PostGIS_Version();"
# Debe retornar: 3.x.x
```

---

## 4. Instalación del servicio

```bash
# 1. Crear usuario del sistema para el servicio
sudo useradd -r -s /bin/false -d /opt/geonlq geonlq

# 2. Crear directorio de instalación
sudo mkdir -p /opt/geonlq
sudo chown geonlq:geonlq /opt/geonlq

# 3. Clonar el repositorio (o copiar los archivos)
sudo -u geonlq git clone https://tu-repositorio/geonlq.git /opt/geonlq
# O copiar manualmente:
# sudo cp -r /ruta/local/geonlq/* /opt/geonlq/

# 4. Crear entorno virtual e instalar dependencias
cd /opt/geonlq
sudo -u geonlq python3.12 -m venv venv
sudo -u geonlq venv/bin/pip install --upgrade pip
sudo -u geonlq venv/bin/pip install -r requirements.txt

# 5. Verificar instalación
sudo -u geonlq venv/bin/python -c "import fastapi, sqlalchemy, shapely; print('OK')"
```

---

## 5. Variables de entorno (.env)

> **API en Docker (variante B2):** use la plantilla [`.env.docker.example`](../.env.docker.example) en lugar del ejemplo systemd de abajo: `POSTGRES_HOST=host.docker.internal`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `OLLAMA_TIMEOUT_SECONDS`, y checklist Ollama en [§6.2.1](#621-ollama-accesible-desde-contenedor-docker-variante-b2) / [EJECUCION_SERVICIO §3.4](./EJECUCION_SERVICIO.md#34-ollama-con-docker-compose-b1-y-b2).

Crear el archivo `/opt/geonlq/.env` con los valores de producción:

```bash
sudo -u geonlq nano /opt/geonlq/.env
```

Contenido del archivo `.env`:

```env
# ─── Base de datos ───────────────────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg2://geonlq_reader:contraseña_segura@localhost:5432/nombre_base_datos

# ─── Proveedor LLM ───────────────────────────────────────────────────────────
# Opciones: "ollama" (local), "openai", "anthropic"
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b

# ─── Ollama (solo si LLM_PROVIDER=ollama) ────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
# Opcional en CPU lenta: OLLAMA_TIMEOUT_SECONDS=180

# ─── API Keys (solo si LLM_PROVIDER=openai o anthropic) ─────────────────────
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...

# ─── CORS: dominios permitidos del cliente web ───────────────────────────────
# Usar el dominio real del frontend en producción, nunca "*"
CORS_ORIGINS=https://mi-aplicacion.dominio.cu,https://ide.dominio.cu

# ─── Límites ─────────────────────────────────────────────────────────────────
MAX_RESULTS=100
SQL_TIMEOUT=30

# ─── Seguridad ───────────────────────────────────────────────────────────────
# Esquemas a los que el servicio tiene acceso
ALLOWED_SCHEMAS=public

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
DEBUG=false

# ─── API ─────────────────────────────────────────────────────────────────────
API_TITLE=GeoNLQ — Consultas en Lenguaje Natural sobre PostGIS
API_VERSION=1.0.0
```

```bash
# Proteger el archivo (solo lectura para el usuario del servicio)
sudo chmod 600 /opt/geonlq/.env
sudo chown geonlq:geonlq /opt/geonlq/.env
```

---

## 6. Configuración de Ollama (LLM local)

### 6.1 Instalar Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 6.2 Configurar Ollama como servicio del sistema

```bash
sudo systemctl enable ollama
sudo systemctl start ollama

# Verificar
systemctl status ollama
```

### 6.2.1 Ollama accesible desde contenedor Docker (variante B2)

Si GeoNLQ corre en **Docker** y Ollama en el **host** (este documento asume systemd en el host):

1. En `.env` del proyecto GeoNLQ: `OLLAMA_BASE_URL=http://host.docker.internal:11434` (plantilla [`.env.docker.example`](../.env.docker.example)).
2. Ollama no debe escuchar **solo** en loopback. Comprobar: `ss -tlnp | grep 11434`. Si aparece `127.0.0.1:11434`:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '%s\n' '[Service]' 'Environment="OLLAMA_HOST=0.0.0.0:11434"' \
  | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

3. Verificar desde el contenedor `geonlq_api` (ver [EJECUCION_SERVICIO.md §3.4](./EJECUCION_SERVICIO.md#34-ollama-con-docker-compose-b1-y-b2)).

En producción, limita el puerto **11434** con firewall a redes de confianza.

### 6.3 Descargar el modelo

```bash
ollama pull qwen2.5-coder:1.5b

# Verificar que el modelo está disponible
ollama list
```

### 6.4 Ajuste de timeout del cliente Ollama

Variable opcional en `.env`: **`OLLAMA_TIMEOUT_SECONDS=180`** (CPU sin GPU).

En código, el timeout se lee desde configuración (`ollama_provider.py`). Valores orientativos:

| Entorno | `OLLAMA_TIMEOUT_SECONDS` |
|---|---|
| CPU sin GPU, modelo 1.5b | 120–180 |
| GPU NVIDIA | 30–60 |

Tras cambiar `.env`, reiniciar el contenedor o el servicio systemd según la variante.

### 6.5 Modelos alternativos (mayor precisión)

| Modelo | Tamaño | Velocidad CPU | Calidad SQL |
|---|---|---|---|
| `qwen2.5-coder:1.5b` | 1 GB | ~30s | Buena |
| `qwen2.5-coder:7b` | 4.7 GB | ~120s | Muy buena |
| `qwen2.5-coder:14b` | 9 GB | ~240s | Excelente |
| `codellama:7b` | 3.8 GB | ~100s | Buena |

> Con GPU, todos los modelos responden en menos de 10 segundos.

---

## 7. Alternativa: OpenAI o Anthropic (API en la nube)

Si el servidor no tiene capacidad para ejecutar Ollama localmente, se puede usar un proveedor externo de LLM. Esta opción ofrece mejor calidad y velocidad a cambio de un costo por consulta.

```env
# En el .env:
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini     # económico y muy preciso para SQL
OPENAI_API_KEY=sk-...

# O con Anthropic:
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-haiku-20241022
ANTHROPIC_API_KEY=sk-ant-...
```

> **Costo estimado:** GPT-4o-mini cobra ~$0.00015 por consulta de usuario. Con 1.000 consultas diarias el costo es aproximadamente $4,50/mes.

---

## 8. Ejecutar el servicio con systemd

Crear la unidad systemd para que GeoNLQ arranque automáticamente y se reinicie ante fallos:

```bash
sudo nano /etc/systemd/system/geonlq.service
```

Contenido:

```ini
[Unit]
Description=GeoNLQ — Consultas NL sobre PostGIS
After=network.target postgresql.service ollama.service
Requires=postgresql.service

[Service]
Type=simple
User=geonlq
Group=geonlq
WorkingDirectory=/opt/geonlq
EnvironmentFile=/opt/geonlq/.env
ExecStart=/opt/geonlq/venv/bin/uvicorn src.geonlq.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --log-level info
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=geonlq

# Límites de seguridad
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/geonlq

[Install]
WantedBy=multi-user.target
```

```bash
# Activar e iniciar el servicio
sudo systemctl daemon-reload
sudo systemctl enable geonlq
sudo systemctl start geonlq

# Verificar estado
sudo systemctl status geonlq

# Ver logs en tiempo real
sudo journalctl -u geonlq -f
```

---

## 9. Proxy inverso con Nginx

Nginx actúa como punto de entrada público, maneja HTTPS, y redirige las peticiones a GeoNLQ (puerto 8000) que solo escucha en localhost.

```bash
sudo nano /etc/nginx/sites-available/geonlq
```

Contenido (HTTP simple para red interna):

```nginx
server {
    listen 80;
    server_name geonlq.dominio.cu;   # cambiar por el dominio real

    # Aumentar timeout para consultas NL (el LLM puede tardar hasta 90s en CPU)
    proxy_read_timeout 120s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 30s;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # Documentación Swagger (opcional: bloquear en producción)
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        # Para restringir acceso a la red interna:
        # allow 192.168.0.0/16;
        # deny all;
    }
}
```

```bash
# Activar el sitio
sudo ln -s /etc/nginx/sites-available/geonlq /etc/nginx/sites-enabled/
sudo nginx -t          # verificar configuración
sudo systemctl reload nginx
```

### 9.1 HTTPS con certificado autofirmado (red interna)

```bash
# Generar certificado autofirmado (válido 10 años)
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/ssl/private/geonlq.key \
    -out /etc/ssl/certs/geonlq.crt \
    -subj "/C=CU/ST=LaHabana/O=MINFAR/CN=geonlq.dominio.cu"

# Añadir bloque HTTPS al archivo de nginx
```

---

## 10. Verificación del servicio

Ejecutar estas comprobaciones después del despliegue:

```bash
# 1. Estado del servicio
sudo systemctl status geonlq ollama postgresql nginx

# 2. Health check
curl http://localhost:8000/api/v1/health

# Respuesta esperada:
# {"status":"ok","database":"connected","llm_provider":"ollama",...}

# 3. Consulta de prueba (tardará 20-90s en CPU la primera vez)
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"¿Cuántas tablas hay en la base de datos?","max_results":5}' \
  | python3 -m json.tool

# 4. Verificar que CORS está configurado para el frontend
curl -I -X OPTIONS http://localhost:8000/api/v1/query \
  -H "Origin: https://mi-aplicacion.dominio.cu" \
  -H "Access-Control-Request-Method: POST"
# Debe retornar: Access-Control-Allow-Origin: https://mi-aplicacion.dominio.cu

# 5. Verificar geometría en respuesta
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Dame 1 puente con su ubicación"}' \
  | python3 -c "
import sys, json
r = json.load(sys.stdin)
f = r['results']['features'][0]
print('display_mode:', r['display_mode'])
print('has_geometry:', r['has_geometry'])
print('geometry type:', f['geometry']['type'] if f['geometry'] else 'NONE — ERROR')
"
```

---

## 11. Seguridad en producción

### Lista de verificación

- **Base de datos:** el servicio usa un usuario de solo lectura (`SELECT`), nunca el superusuario
- **CORS:** configurar dominios específicos en `CORS_ORIGINS`, nunca `"*"` en producción
- **Firewall:** el puerto 8000 solo debe ser accesible desde localhost (Nginx lo expone hacia afuera)
- **Secretos:** el archivo `.env` tiene permisos `600` y no está en el repositorio git
- **SQL Injection:** GeoNLQ solo ejecuta SELECT; el validador bloquea UPDATE, DELETE, DROP, etc.
- **Timeout:** `SQL_TIMEOUT=30` evita que consultas largas bloqueen la base de datos
- **Allowed Schemas:** `ALLOWED_SCHEMAS=public` restringe el acceso a un solo esquema
- **Debug:** `DEBUG=false` en producción (no expone stack traces en errores HTTP)

### Firewall (ufw)

```bash
# Permitir solo SSH, HTTP y HTTPS
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# NO abrir el puerto 8000 (GeoNLQ solo escucha en localhost)
sudo ufw enable
sudo ufw status
```

---

## 12. Mantenimiento y actualizaciones

### Actualizar el código

```bash
cd /opt/geonlq
sudo -u geonlq git pull origin main
sudo -u geonlq venv/bin/pip install -r requirements.txt
sudo systemctl restart geonlq
sudo systemctl status geonlq
```

### Ver logs de consultas

```bash
# Últimas 100 líneas de log
sudo journalctl -u geonlq -n 100

# Logs en tiempo real
sudo journalctl -u geonlq -f

# Consultar el historial de queries guardado en la BD
psql -U geonlq_reader -d nombre_base_datos -c \
  "SELECT question, status, execution_ms, created_at
   FROM query_history ORDER BY created_at DESC LIMIT 20;"
```

### Reemplazar el modelo LLM

```bash
# Descargar nuevo modelo
ollama pull qwen2.5-coder:7b

# Actualizar .env
sudo -u geonlq sed -i 's/LLM_MODEL=.*/LLM_MODEL=qwen2.5-coder:7b/' /opt/geonlq/.env

# Reiniciar el servicio
sudo systemctl restart geonlq
```

### Vaciar la caché del esquema

Si se modifican las tablas de la base de datos (nuevas columnas, tablas, etc.), la caché del esquema se actualiza automáticamente cada 5 minutos (`SCHEMA_CACHE_TTL=300`). Para forzar la actualización de inmediato:

```bash
sudo systemctl restart geonlq
```

---

## 13. Optimizar el esquema para el LLM

El LLM traduce lenguaje natural a SQL guiándose por los **nombres y comentarios de las columnas** que el `schema_inspector` le envía en cada prompt. Si los nombres de campo son abreviaturas o códigos poco descriptivos, el modelo puede usar la columna equivocada o fallar en la traducción.

### El problema concreto

Supón que la tabla `viales` tiene el campo `nom` en lugar de `nombre`. Cuando el usuario pregunta:

> "Dame los puentes en la Carretera Central"

El LLM ve `nom` en el esquema y puede que no lo asocie al nombre de la vía, generando un SQL incorrecto o sin resultados.

### Solución: comentarios de columna en PostgreSQL

PostgreSQL permite documentar cada columna con `COMMENT ON COLUMN`. El `schema_inspector` de GeoNLQ recoge esos comentarios y los incluye en el prompt, dándole al LLM el contexto que necesita sin modificar nada en el código.

```sql
-- Conectarse a la base de datos de producción
psql -U postgres -d nombre_base_datos
```

#### Tabla `viales`

```sql
COMMENT ON COLUMN viales.nom        IS 'Nombre oficial de la vía (ej: Carretera Central, Autopista Nacional)';
COMMENT ON COLUMN viales.cat        IS 'Categoría de la vía: primaria, secundaria, local, rural';
COMMENT ON COLUMN viales.long_km    IS 'Longitud total de la vía en kilómetros';
COMMENT ON COLUMN viales.est        IS 'Estado de conservación: bueno, regular, malo';
COMMENT ON COLUMN viales.cod        IS 'Código identificador único de la vía';
COMMENT ON COLUMN viales.geom       IS 'Geometría de la vía (MULTILINESTRING, SRID 4326)';
```

#### Tabla `puentes`

```sql
COMMENT ON COLUMN puentes.cod       IS 'Código único del puente (ej: PTE-CC-001)';
COMMENT ON COLUMN puentes.nom       IS 'Nombre del puente o río que cruza';
COMMENT ON COLUMN puentes.cap_tn    IS 'Carga máxima permitida en toneladas';
COMMENT ON COLUMN puentes.long_m    IS 'Longitud del puente en metros';
COMMENT ON COLUMN puentes.anch_m    IS 'Ancho del tablero en metros';
COMMENT ON COLUMN puentes.alt_m     IS 'Altura libre bajo el puente en metros';
COMMENT ON COLUMN puentes.carr      IS 'Número de carriles del puente';
COMMENT ON COLUMN puentes.est       IS 'Estado de conservación: bueno, regular, malo';
COMMENT ON COLUMN puentes.tip_est   IS 'Tipo de estructura: hormigon, metalico, mixto, madera';
COMMENT ON COLUMN puentes.anio_con  IS 'Año de construcción del puente';
COMMENT ON COLUMN puentes.insp      IS 'Fecha de la última inspección técnica';
COMMENT ON COLUMN puentes.pk        IS 'Punto kilométrico de la vía donde se ubica el puente';
COMMENT ON COLUMN puentes.rio       IS 'Nombre del río o cauce que cruza el puente';
COMMENT ON COLUMN puentes.geom      IS 'Ubicación del puente (POINT, SRID 4326)';
```

#### Tabla `municipios`

```sql
COMMENT ON COLUMN municipios.nom    IS 'Nombre del municipio';
COMMENT ON COLUMN municipios.prov   IS 'Nombre de la provincia a la que pertenece';
COMMENT ON COLUMN municipios.cod    IS 'Código oficial del municipio';
COMMENT ON COLUMN municipios.geom   IS 'Límite territorial del municipio (MULTIPOLYGON, SRID 4326)';
```

### Cómo ve el LLM el esquema después de añadir comentarios

Antes (sin comentarios):
```
Tabla: viales
  - nom (character varying)
  - cat (character varying)
  - cap_tn (numeric)
```

Después (con comentarios):
```
Tabla: viales
  - nom (character varying) — Nombre oficial de la vía (ej: Carretera Central, Autopista Nacional)
  - cat (character varying) — Categoría de la vía: primaria, secundaria, local, rural
  - cap_tn (numeric) — Capacidad de carga máxima en toneladas
```

Con esa información, el LLM genera correctamente:
```sql
WHERE v.nom ILIKE '%carretera central%'
```
en lugar de dejar el filtro vacío o usar una columna incorrecta.

### Verificar que los comentarios se recogen

Después de añadir los comentarios, reiniciar GeoNLQ para refrescar la caché del esquema y luego consultarlo:

```bash
sudo systemctl restart geonlq

# Ver el esquema tal como lo ve el LLM
curl -s http://localhost:8000/api/v1/schema | python3 -m json.tool
```

Los comentarios deben aparecer en el campo `comment` de cada columna.

### Reglas generales para nombrar campos

Si puedes modificar el esquema, sigue estas convenciones para que el LLM interprete los campos sin necesitar comentarios:

| En lugar de... | Usar... | Por qué |
|---|---|---|
| `nom`, `name`, `n` | `nombre` | El LLM reconoce "nombre" en preguntas en español |
| `est`, `status` | `estado` | Asociado a "estado" en preguntas naturales |
| `cap_tn`, `cap` | `carga_maxima_tn` | Incluye la unidad — evita ambigüedad |
| `long_m` | `longitud_m` | Claro y con unidad |
| `anio`, `yr` | `año_construccion` | Descripción completa |
| `tp_via`, `cat` | `tipo_via` | Sin abreviaturas |
| `geom`, `shape` | `geom` | `geom` es el estándar PostGIS — mantener |

> **Nota:** Si el esquema no se puede modificar (tablas heredadas, vistas de terceros), los comentarios de columna son la única solución sin tocar el código de GeoNLQ.

---

## Resumen rápido de comandos

| Acción | Comando |
|---|---|
| Iniciar servicio | `sudo systemctl start geonlq` |
| Detener servicio | `sudo systemctl stop geonlq` |
| Reiniciar servicio | `sudo systemctl restart geonlq` |
| Ver estado | `sudo systemctl status geonlq` |
| Ver logs | `sudo journalctl -u geonlq -f` |
| Health check | `curl http://localhost:8000/api/v1/health` |
| Ver esquema detectado | `curl http://localhost:8000/api/v1/schema` |
| Ver historial | `curl http://localhost:8000/api/v1/history` |
