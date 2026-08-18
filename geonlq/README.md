# GeoNLQ — Consultas en Lenguaje Natural sobre PostGIS

Servicio Python que traduce preguntas en lenguaje natural a SQL geoespacial
y las ejecuta contra una base de datos PostGIS.

## Ejemplo de uso

**Pregunta:** "Dame un listado de puentes que están en la Carretera Central de Pinar del Río a La Habana y que soporten camiones con un peso de 10 toneladas"

**SQL generado automáticamente:**
```sql
SELECT p.codigo, p.nombre, p.carga_maxima_tn, p.longitud_m, p.estado, p.pk_vial,
       ST_AsGeoJSON(p.geom)::json AS geometry
FROM puentes p
JOIN viales v ON p.vial_id = v.id
JOIN municipios m ON p.municipio_id = m.id
WHERE v.nombre ILIKE '%carretera central%'
  AND p.carga_maxima_tn >= 10
  AND m.provincia ILIKE '%pinar%' OR m.provincia ILIKE '%habana%'
ORDER BY p.pk_vial
LIMIT 100;
```

---

## Inicio rápido — WSL + Ollama + Docker (entorno local Smartgeo)

Este entorno usa WSL Ubuntu, Ollama para el modelo local y un contenedor Docker
con PostGIS en el puerto 5434.

### Requisitos previos

- WSL Ubuntu con Python 3.12
- Docker corriendo con el contenedor `postgres14-3.3` (puerto 5434)
- Ollama instalado en WSL

### 1. Verificar que Ollama está corriendo

```bash
curl http://localhost:11434
# Debe responder: Ollama is running
```

Si no está corriendo:
```bash
ollama serve &
```

Si el modelo no está descargado aún:
```bash
ollama pull qwen2.5-coder:1.5b
```

### 2. Verificar que el contenedor PostgreSQL está activo

```bash
docker ps | grep postgres14-3.3
```

Si aparece como detenido:
```bash
docker start postgres14-3.3
```

### 3. Copiar el proyecto a WSL (solo la primera vez)

```bash
cp -r "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/geonlq" ~/geonlq
```

### 4. Crear entorno virtual e instalar dependencias (solo la primera vez)

```bash
cd ~/geonlq
sudo apt install python3.12-venv -y   # si no está instalado
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Configurar el archivo .env (solo la primera vez)

```bash
cat > ~/geonlq/.env << 'EOF'
DATABASE_URL=postgresql+psycopg2://postgres:Gispostgres123!@localhost:5434/geonlq

LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:1.5b
OLLAMA_BASE_URL=http://localhost:11434

MAX_RESULTS=100
SQL_TIMEOUT=30
LOG_LEVEL=INFO
DEBUG=true
EOF
```

### 6. Crear las tablas en la base de datos (solo la primera vez)

```bash
docker cp ~/geonlq/docs/schema/001_initial_schema.sql postgres14-3.3:/tmp/schema.sql
docker exec -e PGPASSWORD='Gispostgres123!' postgres14-3.3 \
  psql -U postgres -d geonlq -f /tmp/schema.sql
```

### 7. Iniciar el servicio

```bash
cd ~/geonlq
source venv/bin/activate
python3 -m uvicorn src.geonlq.main:app --host 0.0.0.0 --port 8000 --reload
```

El servicio queda disponible en `http://localhost:8000`.

### 8. Detener el servicio

Presiona `Ctrl+C` en la terminal donde corre, o desde otra terminal:
```bash
pkill -f "uvicorn src.geonlq"
```

### 9. Verificar que todo funciona

```bash
# Estado del servicio
curl http://localhost:8000/api/v1/health

# Tablas detectadas
curl -s http://localhost:8000/api/v1/schema | python3 -m json.tool

# Primera consulta de prueba (tarda ~60-90s en CPU)
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Dame todos los puentes"}' | python3 -m json.tool
```

> **Nota:** El modelo corre en CPU (WSL no tiene acceso a GPU). El tiempo de
> respuesta es de 60–120 segundos por consulta con `qwen2.5-coder:1.5b`.
> Después del fine-tuning el SQL será más preciso pero la velocidad es similar.

---

## Instalación rápida

Guía detallada para **arrancar, parar y mantener el servicio activo** (venv vs Docker Compose, WSL, sin rebuild innecesario): [docs/EJECUCION_SERVICIO.md](docs/EJECUCION_SERVICIO.md).

**Guía única paso a paso (WSL → dist → producción):** [docs/GUIA_PASOS_DESPLIEGUE.md](docs/GUIA_PASOS_DESPLIEGUE.md).

### Opción 1 — Docker Compose

**Servidor destino con PostgreSQL/PostGIS ya instalado (sin Python en el host):**

```bash
cp .env.docker.example .env    # editar POSTGRES_* , LLM, puerto
docker compose -f docker-compose.external-db.yml up -d --build
curl http://localhost:8000/api/v1/health
```

Detalle: [docs/EJECUCION_SERVICIO.md](docs/EJECUCION_SERVICIO.md) § B2.

**Demo / desarrollo (PostGIS + API en contenedores):**

```bash
cp .env.example .env
docker compose up -d
curl http://localhost:8000/api/v1/health
```

### Opción 2 — Entorno local

```bash
# 1. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 4. Crear base de datos y esquema
psql -U postgres -c "CREATE DATABASE geonlq;"
psql -U postgres -d geonlq -f docs/schema/001_initial_schema.sql
psql -U postgres -d geonlq -f docs/schema/002_sample_data.sql

# 5. Iniciar el servicio
cd src
uvicorn geonlq.main:app --reload
```

---

## Configuración del LLM

### OpenAI GPT-4o (por defecto)
```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

### Anthropic Claude
```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...
```

### Ollama (local, sin costos)
```bash
# Instalar Ollama: https://ollama.com
ollama pull llama3.1  # o mistral, qwen2.5-coder
```
```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
```

---

## API Reference

### `POST /api/v1/query`

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Cuántos puentes hay en mal estado en Pinar del Río?",
    "output_format": "table",
    "explain": true
  }'
```

### `GET /api/v1/schema` — Ver tablas disponibles
### `GET /api/v1/history` — Historial de consultas
### `GET /api/v1/health` — Estado del servicio
### `GET /docs` — Documentación Swagger interactiva

---

## Estructura del proyecto

```
geonlq/
├── docs/           → SDD, API Reference, esquema SQL
├── src/geonlq/
│   ├── api/        → FastAPI routes y schemas Pydantic
│   ├── core/       → Config, excepciones, logging
│   ├── db/         → Conexión, inspector de esquema, ejecutor SQL
│   ├── llm/        → Proveedores LLM (OpenAI, Anthropic, Ollama)
│   ├── nlq/        → Prompt builder, validador SQL, traductor NL→SQL
│   └── services/   → Orquestador del flujo completo
├── tests/          → Tests unitarios e integración
├── .env.example    → Plantilla de configuración
├── docker-compose.yml
└── requirements.txt
```

---

## Documentación completa

Ver `docs/SDD.md` para el Software Design Document completo.
