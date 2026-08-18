# Software Design Document (SDD)
## GeoNLQ — Servicio de Consultas en Lenguaje Natural sobre PostGIS

**Versión:** 1.0.0  
**Fecha:** 2026-08-07  
**Autor:** Smartgeo  
**Estado:** Borrador inicial  

---

## Historial de revisiones

| Versión | Fecha      | Descripción                        | Autor      |
|---------|------------|------------------------------------|------------|
| 1.0.0   | 2026-08-07 | Versión inicial del SDD            | Smartgeo   |
| 1.0.1   | 2026-08-07 | Integración con ide-minfar (barra NLQ, proxy `/api/nlq`) | Smartgeo   |

---

## Tabla de contenido

1. [Introducción](#1-introducción)
2. [Descripción del Sistema](#2-descripción-del-sistema)
3. [Consideraciones de Diseño](#3-consideraciones-de-diseño)
4. [Arquitectura del Sistema](#4-arquitectura-del-sistema)
5. [Diseño de Componentes](#5-diseño-de-componentes)
6. [Diseño de Datos](#6-diseño-de-datos)
7. [Diseño de Interfaces](#7-diseño-de-interfaces)
8. [Manejo de Errores y Seguridad](#8-manejo-de-errores-y-seguridad)
9. [Plan de Implementación](#9-plan-de-implementación)
10. [Glosario](#10-glosario)

---

## 1. Introducción

### 1.1 Propósito

Este documento describe el diseño completo del sistema **GeoNLQ** (*Geospatial Natural Language Query*), un servicio local en Python que permite a usuarios no técnicos realizar consultas geoespaciales complejas sobre una base de datos PostGIS empleando lenguaje natural. El documento sirve como guía de referencia para el desarrollo, pruebas e integración del sistema.

### 1.2 Alcance

GeoNLQ expone una API REST (FastAPI) que recibe una pregunta en lenguaje natural como:

> *"Dame un listado de puentes que están en la carretera central de Pinar del Río a La Habana y que soporten camiones con un peso de 10 toneladas"*

…la traduce a una consulta SQL/PostGIS válida, la ejecuta contra la base de datos y retorna los resultados en formato JSON/GeoJSON.

### 1.3 Definiciones y Acrónimos

| Término     | Definición |
|-------------|------------|
| NLQ         | Natural Language Query — consulta en lenguaje natural |
| PostGIS     | Extensión espacial de PostgreSQL |
| LLM         | Large Language Model — modelo de lenguaje grande |
| SDD         | Software Design Document |
| GeoJSON     | Formato estándar JSON para datos geoespaciales (RFC 7946) |
| SQL         | Structured Query Language |
| REST        | Representational State Transfer |
| SRID        | Spatial Reference System Identifier |
| WGS84       | Sistema de referencia geodésico (EPSG:4326) |

### 1.4 Referencias

- PostgreSQL 15+ Documentation: https://www.postgresql.org/docs/
- PostGIS 3.x Reference: https://postgis.net/documentation/
- FastAPI Documentation: https://fastapi.tiangolo.com/
- LangChain SQL Agents: https://python.langchain.com/docs/
- OpenAI Function Calling: https://platform.openai.com/docs/

---

## 2. Descripción del Sistema

### 2.1 Contexto del Sistema

GeoNLQ actúa como una capa de inteligencia artificial entre el usuario y la base de datos geoespacial. El sistema se despliega localmente en la infraestructura del cliente (Smartgeo) y no requiere enviar datos sensibles a servicios externos (opcional con modelos locales vía Ollama).

```
┌─────────────────────────────────────────────────────────────┐
│                     USUARIO FINAL                           │
│          (Técnico GIS, Operador, Planificador)               │
└────────────────────────┬────────────────────────────────────┘
                         │ Pregunta en lenguaje natural
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   GeoNLQ SERVICE                            │
│  ┌─────────┐  ┌──────────────┐  ┌──────────┐  ┌────────┐  │
│  │ FastAPI │→ │ NLQ Translator│→ │ LLM Layer│  │DB Layer│  │
│  │   API   │  │ (Prompt Eng) │  │(OpenAI / │  │PostGIS │  │
│  └─────────┘  └──────────────┘  │ Ollama / │  │        │  │
│                                  │Anthropic)│  │        │  │
│                                  └──────────┘  └────────┘  │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼ GeoJSON / JSON
```

### 2.2 Funcionalidades Principales

1. **Procesamiento NLQ:** Traduce preguntas en español/inglés a SQL geoespacial válido.
2. **Introspección de esquema:** Descubre automáticamente las tablas, columnas y relaciones del esquema PostGIS para generar SQL contextual.
3. **Abstracción LLM:** Soporte intercambiable para OpenAI GPT-4o, Anthropic Claude, y modelos locales Ollama.
4. **Ejecución segura de SQL:** Valida y ejecuta únicamente sentencias SELECT; previene inyección SQL y operaciones destructivas.
5. **Resultados geoespaciales:** Retorna resultados como GeoJSON, tabular (JSON), o texto descriptivo.
6. **Historial de consultas:** Registro de consultas, SQL generado, tiempo de respuesta y resultado.

### 2.3 Restricciones del Sistema

- Sólo soporta consultas de **lectura** (SELECT). No se ejecutan INSERT, UPDATE, DELETE, DROP.
- Requiere PostgreSQL ≥ 14 con PostGIS ≥ 3.0.
- El LLM debe estar disponible (API key o servicio Ollama activo).
- SRID por defecto: EPSG:4326 (WGS84). Configurable.

---

## 3. Consideraciones de Diseño

### 3.1 Supuestos

- El esquema de base de datos es relativamente estable (no cambia en cada consulta).
- Los usuarios formulan preguntas en español; se acepta inglés.
- Las tablas PostGIS tienen geometrías válidas y los índices espaciales están activos.
- El LLM tiene capacidad para razonar sobre operaciones espaciales estándar (ST_Intersects, ST_DWithin, ST_Buffer, etc.).

### 3.2 Dependencias

| Dependencia          | Versión mínima | Propósito                         |
|----------------------|----------------|-----------------------------------|
| Python               | 3.11+          | Lenguaje base                     |
| FastAPI              | 0.111+         | Framework API REST                |
| SQLAlchemy           | 2.0+           | ORM y conexión a BD               |
| GeoAlchemy2          | 0.14+          | Soporte tipos geoespaciales       |
| psycopg2-binary      | 2.9+           | Driver PostgreSQL                 |
| langchain            | 0.2+           | Abstracción LLM y cadenas         |
| langchain-openai     | 0.1+           | Proveedor OpenAI                  |
| langchain-anthropic  | 0.1+           | Proveedor Anthropic               |
| ollama               | 0.2+           | Cliente Ollama local              |
| pydantic             | 2.0+           | Validación de modelos             |
| python-dotenv        | 1.0+           | Gestión de configuración          |
| uvicorn              | 0.29+          | Servidor ASGI                     |

### 3.3 Limitaciones Conocidas

- La calidad del SQL generado depende directamente de la capacidad del LLM elegido.
- Consultas muy complejas (múltiples joins + operaciones espaciales anidadas) pueden requerir prompt engineering adicional.
- El modelo LLM no tiene estado de sesión entre consultas (cada consulta es independiente por defecto).

---

## 4. Arquitectura del Sistema

### 4.1 Arquitectura en Capas

GeoNLQ sigue una arquitectura en capas (Layered Architecture) con separación clara de responsabilidades:

```
┌───────────────────────────────────────────────────┐
│              CAPA DE PRESENTACIÓN                  │
│         FastAPI — Endpoints REST                   │
│     /query  /schema  /history  /health             │
├───────────────────────────────────────────────────┤
│              CAPA DE APLICACIÓN                    │
│    NLQ Orchestrator — QueryService                 │
│    Gestiona el flujo: NL → SQL → Resultado         │
├───────────────────────────────────────────────────┤
│              CAPA DE DOMINIO                       │
│  ┌─────────────────┐    ┌────────────────────┐    │
│  │  NLQ Translator  │    │  Schema Inspector  │    │
│  │  Prompt Builder  │    │  (auto-discovery)  │    │
│  │  SQL Validator   │    │                    │    │
│  └─────────────────┘    └────────────────────┘    │
├───────────────────────────────────────────────────┤
│             CAPA DE INFRAESTRUCTURA                │
│  ┌──────────────────┐   ┌──────────────────────┐  │
│  │  LLM Providers   │   │   Database Layer      │  │
│  │  ┌────────────┐  │   │  ┌────────────────┐  │  │
│  │  │  OpenAI    │  │   │  │ SQLAlchemy+    │  │  │
│  │  │  Anthropic │  │   │  │ GeoAlchemy2    │  │  │
│  │  │  Ollama    │  │   │  │ PostGIS        │  │  │
│  │  └────────────┘  │   │  └────────────────┘  │  │
│  └──────────────────┘   └──────────────────────┘  │
└───────────────────────────────────────────────────┘
```

### 4.2 Estructura del Proyecto

```
geonlq/
├── docs/
│   ├── SDD.md                     ← Este documento
│   ├── API_REFERENCE.md           ← Documentación de endpoints
│   └── schema/
│       ├── 001_initial_schema.sql ← DDL completo PostGIS
│       └── 002_sample_data.sql    ← Datos de prueba
│
├── src/
│   └── geonlq/
│       ├── __init__.py
│       ├── main.py                ← Punto de entrada FastAPI
│       │
│       ├── api/                   ← Capa de presentación
│       │   ├── __init__.py
│       │   ├── routes.py          ← Definición de rutas
│       │   └── schemas.py         ← Modelos Pydantic (request/response)
│       │
│       ├── core/                  ← Configuración central
│       │   ├── __init__.py
│       │   ├── config.py          ← Settings (pydantic-settings)
│       │   ├── logging.py         ← Configuración de logs
│       │   └── exceptions.py      ← Excepciones personalizadas
│       │
│       ├── services/              ← Capa de aplicación
│       │   ├── __init__.py
│       │   └── query_service.py   ← Orquestador principal
│       │
│       ├── nlq/                   ← Traducción NL → SQL
│       │   ├── __init__.py
│       │   ├── translator.py      ← Orquesta la traducción
│       │   ├── prompt_builder.py  ← Construye prompts para el LLM
│       │   └── sql_validator.py   ← Valida y sanitiza SQL generado
│       │
│       ├── llm/                   ← Abstracción de proveedores LLM
│       │   ├── __init__.py
│       │   ├── base.py            ← Interfaz abstracta LLMProvider
│       │   ├── openai_provider.py
│       │   ├── anthropic_provider.py
│       │   ├── ollama_provider.py
│       │   └── factory.py         ← Crea el proveedor según config
│       │
│       ├── db/                    ← Capa de base de datos
│       │   ├── __init__.py
│       │   ├── connection.py      ← Pool de conexiones SQLAlchemy
│       │   ├── schema_inspector.py ← Introspección del esquema PostGIS
│       │   └── executor.py        ← Ejecuta SQL y formatea resultados
│       │
│       └── formatters/            ← Formateo de resultados
│           ├── __init__.py
│           ├── geojson_formatter.py
│           └── table_formatter.py
│
├── tests/
│   ├── unit/
│   │   ├── test_prompt_builder.py
│   │   ├── test_sql_validator.py
│   │   └── test_schema_inspector.py
│   └── integration/
│       ├── test_api_endpoints.py
│       └── test_query_pipeline.py
│
├── .env.example                   ← Plantilla de variables de entorno
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml             ← PostgreSQL+PostGIS + GeoNLQ (demo)
├── docker-compose.external-db.yml ← Solo API; PostGIS en el servidor
├── .env.docker.example            ← Plantilla .env para despliegue B2
├── Dockerfile
└── README.md
```

### 4.3 Flujo de Datos Principal

```
Usuario
  │
  │ POST /api/v1/query
  │ { "question": "Dame puentes en la carretera central..." }
  ▼
[FastAPI Route] routes.py
  │ Valida request (Pydantic)
  ▼
[QueryService] query_service.py
  │
  ├─→ [SchemaInspector] → Lee metadata de tablas/columnas PostGIS
  │                       (cacheada en memoria, TTL configurable)
  │
  ├─→ [PromptBuilder]  → Construye prompt con:
  │                       - Pregunta del usuario
  │                       - Esquema de tablas relevantes
  │                       - Ejemplos few-shot
  │                       - Instrucciones PostGIS
  │
  ├─→ [LLMProvider]    → Envía prompt al LLM (OpenAI/Anthropic/Ollama)
  │                       Recibe SQL geoespacial generado
  │
  ├─→ [SQLValidator]   → Verifica que el SQL es:
  │                       - Solo SELECT (no DDL/DML)
  │                       - Sintaxis válida
  │                       - Sin inyección SQL
  │
  ├─→ [DBExecutor]     → Ejecuta query en PostGIS
  │                       Obtiene filas resultado
  │
  └─→ [Formatter]      → Convierte a GeoJSON/JSON/texto
  │
  ▼
[FastAPI Response]
  │ { "sql": "...", "results": [...], "total": N, "time_ms": X }
  ▼
Usuario
```

---

## 5. Diseño de Componentes

### 5.1 `main.py` — Punto de Entrada

Inicializa la aplicación FastAPI, registra los routers, configura middleware (CORS, logging) y gestiona el ciclo de vida (startup/shutdown) para inicializar el pool de BD y cachear el esquema.

**Responsabilidades:**
- Crear instancia `FastAPI`
- Registrar router de API (`/api/v1`)
- Middleware: CORS, logging de requests
- Eventos startup: conectar BD, cachear schema
- Evento shutdown: cerrar pool conexiones

### 5.2 `api/routes.py` — Endpoints REST

Define los endpoints disponibles. Ver sección 7 para detalle completo.

### 5.3 `api/schemas.py` — Modelos Pydantic

```python
# Request
class QueryRequest(BaseModel):
    question: str          # Pregunta en lenguaje natural
    output_format: str     # "geojson" | "table" | "text"
    max_results: int       # Límite de filas (default: 100)
    explain: bool          # Incluir explicación del SQL (default: False)

# Response
class QueryResponse(BaseModel):
    question: str          # Pregunta original
    sql: str               # SQL generado por el LLM
    results: list          # Resultados (GeoJSON features o dicts)
    total: int             # Total de registros
    time_ms: float         # Tiempo de ejecución en ms
    explanation: str | None  # Explicación del SQL (si explain=True)
```

### 5.4 `core/config.py` — Configuración

Usa `pydantic-settings` para leer variables de entorno desde `.env`:

| Variable                | Default          | Descripción                             |
|-------------------------|------------------|-----------------------------------------|
| `DATABASE_URL`          | —                | URL completa de PostgreSQL+PostGIS      |
| `LLM_PROVIDER`          | `openai`         | `openai` \| `anthropic` \| `ollama`     |
| `LLM_MODEL`             | `gpt-4o`         | Nombre del modelo a usar                |
| `OPENAI_API_KEY`        | —                | API key de OpenAI                       |
| `ANTHROPIC_API_KEY`     | —                | API key de Anthropic                    |
| `OLLAMA_BASE_URL`       | `http://localhost:11434` | URL del servidor Ollama (en Docker B2: `http://host.docker.internal:11434`; ver [EJECUCION §3.4](./EJECUCION_SERVICIO.md#34-ollama-con-docker-compose-b1-y-b2)) |
| `OLLAMA_TIMEOUT_SECONDS`| `120`            | Timeout HTTP al generar SQL vía Ollama (subir en CPU) |
| `SCHEMA_CACHE_TTL`      | `300`            | TTL de caché de esquema (segundos)      |
| `MAX_RESULTS`           | `100`            | Límite máximo de filas por consulta     |
| `SQL_TIMEOUT`           | `30`             | Timeout para queries en segundos        |
| `LOG_LEVEL`             | `INFO`           | Nivel de logging                        |
| `ALLOWED_SCHEMAS`       | `public`         | Schemas de BD permitidos (separados por coma) |

### 5.5 `nlq/prompt_builder.py` — Constructor de Prompts

Este es el componente más crítico del sistema. Construye el prompt que recibe el LLM con toda la información necesaria para generar SQL geoespacial correcto.

**Estructura del prompt generado:**

```
SISTEMA:
Eres un experto en SQL geoespacial y PostGIS. Tu única tarea es traducir
preguntas en lenguaje natural a consultas SQL válidas para PostgreSQL con
PostGIS. SIEMPRE genera solo SELECT. NUNCA generes INSERT, UPDATE, DELETE.
Usa funciones PostGIS estándar (ST_Intersects, ST_Buffer, ST_DWithin, etc.).
El SRID de trabajo es EPSG:4326 (WGS84). Retorna SOLO el SQL, sin explicaciones.

ESQUEMA DE BASE DE DATOS:
[Descripción completa de tablas, columnas, tipos y relaciones]

EJEMPLOS:
Pregunta: "¿Cuántos puentes hay en La Habana?"
SQL: SELECT COUNT(*) as total FROM puentes p
     JOIN municipios m ON ST_Within(p.geom, m.geom)
     WHERE m.nombre ILIKE '%habana%';

Pregunta: "Dame los viales con más de 100km en Pinar del Río"
SQL: SELECT v.nombre, ST_Length(v.geom::geography)/1000 as km
     FROM viales v
     JOIN municipios m ON ST_Intersects(v.geom, m.geom)
     WHERE m.nombre ILIKE '%pinar%'
     AND ST_Length(v.geom::geography)/1000 > 100;

PREGUNTA DEL USUARIO:
{question}
```

### 5.6 `nlq/sql_validator.py` — Validador SQL

Valida el SQL generado antes de ejecutarlo:

1. **Prohibición de DDL/DML:** Rechaza cualquier SQL que contenga `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`.
2. **Validación de sintaxis:** Intenta parsear el SQL con `sqlparse`.
3. **Restricción de esquemas:** Verifica que las tablas referenciadas pertenecen a los schemas permitidos (`ALLOWED_SCHEMAS`).
4. **Normalización:** Añade `LIMIT` si no está presente (usa `MAX_RESULTS`).

### 5.7 `llm/base.py` — Interfaz Abstracta LLM

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def generate_sql(self, prompt: str) -> str:
        """Recibe el prompt completo y retorna SQL generado."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Verifica que el proveedor está disponible."""
        pass
```

Todos los proveedores (`OpenAIProvider`, `AnthropicProvider`, `OllamaProvider`) implementan esta interfaz. `llm/factory.py` devuelve la instancia correcta según `LLM_PROVIDER` en configuración.

### 5.8 `db/schema_inspector.py` — Inspector de Esquema

Consulta las vistas del sistema de PostgreSQL/PostGIS para construir una representación del esquema que se inyecta en el prompt:

```sql
-- Obtiene tablas con geometría (PostGIS)
SELECT f_table_name, f_geometry_column, type, srid
FROM geometry_columns
WHERE f_table_schema = 'public';

-- Obtiene columnas con sus tipos
SELECT column_name, data_type, col_description(...)
FROM information_schema.columns
WHERE table_schema = 'public';
```

El resultado se **cachea en memoria** (TTL configurable) para no relanzar esta consulta en cada petición.

### 5.9 `db/executor.py` — Ejecutor de Consultas

- Usa el pool de conexiones SQLAlchemy asíncrono.
- Ejecuta el SQL con timeout (`statement_timeout`).
- Si la query retorna columnas de tipo `geometry`, las serializa como WKT o GeoJSON usando `ST_AsGeoJSON()`.
- Detecta automáticamente si hay una columna de geometría para elegir el formateador adecuado.

---

## 6. Diseño de Datos

### 6.1 Esquema de Base de Datos PostGIS

El esquema contempla tres entidades principales con sus relaciones espaciales:

#### Tabla `municipios`

| Columna          | Tipo               | Descripción                              |
|------------------|--------------------|------------------------------------------|
| `id`             | SERIAL PRIMARY KEY |                                          |
| `codigo`         | VARCHAR(10)        | Código oficial del municipio             |
| `nombre`         | VARCHAR(100)       | Nombre del municipio                     |
| `provincia`      | VARCHAR(100)       | Nombre de la provincia                   |
| `codigo_prov`    | VARCHAR(5)         | Código de provincia                      |
| `area_km2`       | NUMERIC(10,2)      | Área en kilómetros cuadrados             |
| `poblacion`      | INTEGER            | Población (último censo)                 |
| `geom`           | GEOMETRY(MULTIPOLYGON, 4326) | Geometría del municipio    |
| `created_at`     | TIMESTAMP          | Fecha de creación del registro           |
| `updated_at`     | TIMESTAMP          | Fecha de última actualización            |

#### Tabla `viales`

| Columna              | Tipo               | Descripción                              |
|----------------------|--------------------|------------------------------------------|
| `id`                 | SERIAL PRIMARY KEY |                                          |
| `codigo`             | VARCHAR(20)        | Código oficial de la vía                 |
| `nombre`             | VARCHAR(200)       | Nombre de la vía                         |
| `tipo_via`           | VARCHAR(50)        | `autopista` \| `carretera` \| `camino`   |
| `categoria`          | VARCHAR(20)        | `nacional` \| `provincial` \| `local`    |
| `longitud_km`        | NUMERIC(10,3)      | Longitud total en km (calculada)         |
| `velocidad_max_kmh`  | INTEGER            | Velocidad máxima permitida               |
| `num_carriles`       | SMALLINT           | Número de carriles                       |
| `estado`             | VARCHAR(20)        | `bueno` \| `regular` \| `malo`           |
| `gestionado_por`     | VARCHAR(100)       | Organismo gestor                         |
| `geom`               | GEOMETRY(MULTILINESTRING, 4326) | Geometría de la vía      |
| `created_at`         | TIMESTAMP          |                                          |
| `updated_at`         | TIMESTAMP          |                                          |

#### Tabla `puentes`

| Columna                  | Tipo               | Descripción                              |
|--------------------------|--------------------|------------------------------------------|
| `id`                     | SERIAL PRIMARY KEY |                                          |
| `codigo`                 | VARCHAR(20)        | Código oficial del puente                |
| `nombre`                 | VARCHAR(200)       | Nombre del puente                        |
| `vial_id`                | INTEGER FK         | Vía a la que pertenece                   |
| `municipio_id`           | INTEGER FK         | Municipio donde está ubicado             |
| `longitud_m`             | NUMERIC(8,2)       | Longitud del puente en metros            |
| `ancho_m`                | NUMERIC(6,2)       | Ancho útil en metros                     |
| `altura_libre_m`         | NUMERIC(6,2)       | Gálibo (altura libre bajo el puente)     |
| `carga_maxima_tn`        | NUMERIC(8,2)       | Carga máxima admisible en toneladas      |
| `tipo_estructura`        | VARCHAR(50)        | `hormigon` \| `metal` \| `mixto`         |
| `año_construccion`       | SMALLINT           | Año de construcción                      |
| `estado`                 | VARCHAR(20)        | `bueno` \| `regular` \| `malo`           |
| `pk_vial`                | NUMERIC(8,3)       | Punto kilométrico en la vía              |
| `geom`                   | GEOMETRY(POINT, 4326) | Ubicación del puente                  |
| `created_at`             | TIMESTAMP          |                                          |
| `updated_at`             | TIMESTAMP          |                                          |

### 6.2 Relaciones entre Entidades

```
municipios ──< puentes >── viales
     │                        │
     └─── (spatial join) ─────┘
          ST_Within / ST_Intersects
```

- Un **puente** pertenece a una **vía** (FK `vial_id`) y a un **municipio** (FK `municipio_id`).
- Las relaciones espaciales entre **viales** y **municipios** se resuelven con funciones PostGIS en tiempo de consulta.

### 6.3 Índices

```sql
-- Índices espaciales (GIST) — obligatorios para performance
CREATE INDEX idx_municipios_geom ON municipios USING GIST (geom);
CREATE INDEX idx_viales_geom ON viales USING GIST (geom);
CREATE INDEX idx_puentes_geom ON puentes USING GIST (geom);

-- Índices en claves foráneas
CREATE INDEX idx_puentes_vial_id ON puentes (vial_id);
CREATE INDEX idx_puentes_municipio_id ON puentes (municipio_id);

-- Índices en campos de búsqueda frecuente
CREATE INDEX idx_municipios_nombre ON municipios USING gin (nombre gin_trgm_ops);
CREATE INDEX idx_viales_nombre ON viales USING gin (nombre gin_trgm_ops);
CREATE INDEX idx_puentes_nombre ON puentes USING gin (nombre gin_trgm_ops);
```

### 6.4 Tabla de Historial de Consultas

```sql
CREATE TABLE query_history (
    id          BIGSERIAL PRIMARY KEY,
    question    TEXT NOT NULL,
    sql_generated TEXT,
    llm_provider VARCHAR(50),
    llm_model   VARCHAR(100),
    result_count INTEGER,
    execution_ms NUMERIC(10,2),
    status      VARCHAR(20),  -- 'success' | 'error'
    error_msg   TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);
```

---

## 7. Diseño de Interfaces

### 7.1 API REST — Endpoints

#### `POST /api/v1/query` — Consulta en lenguaje natural

**Request:**
```json
{
  "question": "Dame un listado de puentes que están en la carretera central de Pinar del Río a La Habana y que soporten camiones con un peso de 10 toneladas",
  "output_format": "geojson",
  "max_results": 50,
  "explain": true
}
```

**Response 200:**
```json
{
  "question": "Dame un listado de puentes...",
  "sql": "SELECT p.id, p.nombre, p.carga_maxima_tn, p.pk_vial, ST_AsGeoJSON(p.geom)::json AS geometry FROM puentes p JOIN viales v ON p.vial_id = v.id WHERE v.nombre ILIKE '%carretera central%' AND p.carga_maxima_tn >= 10 ORDER BY p.pk_vial LIMIT 50",
  "results": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Point", "coordinates": [-82.4, 22.9] },
        "properties": {
          "id": 42,
          "nombre": "Puente Río San Diego",
          "carga_maxima_tn": 15.0,
          "pk_vial": 45.2
        }
      }
    ]
  },
  "total": 8,
  "time_ms": 342.5,
  "explanation": "Se buscan puentes asociados a la vía 'Carretera Central' con carga máxima >= 10 toneladas, ordenados por punto kilométrico."
}
```

#### `GET /api/v1/schema` — Esquema de tablas disponibles

Retorna el esquema de tablas detectadas en PostGIS para que el usuario sepa qué puede consultar.

#### `GET /api/v1/history` — Historial de consultas

Parámetros: `limit` (default 20), `offset` (default 0), `status` (filtro por estado).

#### `GET /api/v1/health` — Estado del servicio

```json
{
  "status": "healthy",
  "database": "connected",
  "llm_provider": "openai",
  "llm_model": "gpt-4o",
  "schema_cached": true,
  "uptime_seconds": 3600
}
```

### 7.2 Formato de Error

```json
{
  "error": "sql_generation_failed",
  "message": "El LLM no pudo generar SQL válido para la pregunta",
  "detail": "Intente reformular la pregunta con más especificidad",
  "request_id": "a1b2c3d4"
}
```

### 7.3 Documentación Interactiva

FastAPI genera automáticamente documentación Swagger UI en `/docs` y ReDoc en `/redoc`. Disponible en desarrollo; configurable en producción.

---

## 8. Manejo de Errores y Seguridad

### 8.1 Categorías de Error

| Código Error            | Causa                                   | Acción                              |
|-------------------------|-----------------------------------------|-------------------------------------|
| `llm_unavailable`       | LLM no accesible                        | Retornar 503 + mensaje              |
| `sql_generation_failed` | LLM generó SQL inválido tras reintentos | Retornar 422 + sugerencia           |
| `sql_forbidden`         | SQL generado contiene DML/DDL           | Retornar 400 + log de seguridad     |
| `db_timeout`            | Query excedió `SQL_TIMEOUT`             | Retornar 408                        |
| `db_error`              | Error de PostgreSQL                     | Retornar 500 + log interno          |
| `schema_not_found`      | Tabla referenciada no existe            | Retornar 404 + sugerencia           |

### 8.2 Estrategia de Reintentos

Si el LLM genera SQL inválido (sintaxis errónea o contiene DDL):
1. Se reintenta el prompt añadiendo el SQL fallido y el error como contexto.
2. Máximo 2 reintentos.
3. Si sigue fallando, se retorna error `sql_generation_failed`.

### 8.3 Seguridad

- **Solo SELECT:** El validador SQL bloquea cualquier otra operación.
- **Timeout de BD:** Cada query tiene `SET LOCAL statement_timeout`.
- **Usuario de BD:** El usuario PostgreSQL configurado debe tener solo permisos `SELECT` sobre las tablas de datos.
- **Rate Limiting:** FastAPI + `slowapi` para limitar peticiones por IP.
- **Logs de auditoría:** Todas las consultas se registran en `query_history`.

---

## 9. Plan de Implementación

### 9.1 Fases de Desarrollo

#### Fase 1 — Infraestructura Base (Semana 1)
- [ ] Configurar entorno Python (venv, dependencias)
- [ ] Levantar PostgreSQL + PostGIS con Docker
- [ ] Implementar `core/config.py` y `core/exceptions.py`
- [ ] Implementar `db/connection.py` (pool SQLAlchemy)
- [ ] Ejecutar script DDL (`001_initial_schema.sql`)
- [ ] Cargar datos de prueba (`002_sample_data.sql`)

#### Fase 2 — Capa LLM (Semana 1-2)
- [ ] Implementar `llm/base.py` (interfaz abstracta)
- [ ] Implementar `llm/openai_provider.py`
- [ ] Implementar `llm/ollama_provider.py`
- [ ] Implementar `llm/anthropic_provider.py`
- [ ] Implementar `llm/factory.py`
- [ ] Tests unitarios de proveedores

#### Fase 3 — Motor NLQ (Semana 2)
- [ ] Implementar `db/schema_inspector.py` (con caché)
- [ ] Implementar `nlq/prompt_builder.py` (con ejemplos few-shot)
- [ ] Implementar `nlq/sql_validator.py`
- [ ] Implementar `nlq/translator.py`
- [ ] Tests unitarios del motor NLQ

#### Fase 4 — API REST (Semana 2-3)
- [ ] Implementar `api/schemas.py` (modelos Pydantic)
- [ ] Implementar `api/routes.py` (endpoints)
- [ ] Implementar `services/query_service.py` (orquestador)
- [ ] Implementar `main.py`
- [ ] Tests de integración de endpoints

#### Fase 5 — Formatters y Refinamiento (Semana 3)
- [ ] Implementar `formatters/geojson_formatter.py`
- [ ] Implementar `formatters/table_formatter.py`
- [ ] Historial de consultas (`query_history`)
- [ ] Endpoint `/health` y `/schema`
- [ ] Refinamiento de prompts con casos de prueba reales

#### Fase 6 — Testing y Documentación (Semana 3-4)
- [ ] Suite completa de tests unitarios e integración
- [ ] `API_REFERENCE.md`
- [ ] `README.md` completo con guía de instalación
- [ ] Docker Compose para despliegue local completo

### 9.2 Criterios de Aceptación

| Criterio                                    | Métrica objetivo              |
|---------------------------------------------|-------------------------------|
| Precisión de SQL generado (casos de prueba) | ≥ 85% correctos sin retries   |
| Tiempo de respuesta total (p95)             | ≤ 5 segundos                  |
| Cobertura de tests                          | ≥ 80%                         |
| Disponibilidad del servicio                 | ≥ 99% en uso local            |

---

## 9.1 Integración con ide-minfar

El cliente oficial es **IDE Minfar** (Next.js 14). La integración MVP usa:

- Proxy BFF: `POST /api/nlq` → `POST /api/v1/query`
- Configuración servidor: `runtime.json` (`geonlq.baseUrl`) o `GEONLQ_URL`
- UI: barra horizontal `nlquery` + `NLQueryDialog`

Documentación cruzada:

- Guía de implementación: `docs/INTEGRACION_IDE.md`
- SDD del lado cliente: repositorio `ide-minfar` → `docs/geonlq-integration-architecture.md`

---

## 10. Glosario

| Término             | Definición |
|---------------------|------------|
| **Few-shot**        | Técnica de prompt engineering que incluye ejemplos en el prompt para guiar al LLM |
| **GIST index**      | Generalized Search Tree — tipo de índice de PostgreSQL optimizado para geometrías |
| **ST_Intersects**   | Función PostGIS: retorna TRUE si dos geometrías comparten algún punto |
| **ST_Within**       | Función PostGIS: retorna TRUE si la geometría A está completamente dentro de B |
| **ST_Buffer**       | Función PostGIS: crea una zona de influencia alrededor de una geometría |
| **ST_DWithin**      | Función PostGIS: retorna TRUE si dos geometrías están a distancia ≤ D |
| **WKT**             | Well-Known Text — representación textual estándar de geometrías |
| **GeoJSON**         | Formato JSON para representar features geoespaciales (RFC 7946) |
| **EPSG:4326**       | Sistema de referencia geográfico WGS84 (lat/lon en grados decimales) |
| **TTL**             | Time To Live — tiempo de vida de una entrada en caché |
| **ASGI**            | Asynchronous Server Gateway Interface — estándar para servidores Python async |
| **Pool**            | Conjunto de conexiones de BD reutilizables |
| **Prompt**          | Instrucción completa enviada al LLM incluyendo contexto, ejemplos y pregunta |
| **DDL**             | Data Definition Language (CREATE, ALTER, DROP) |
| **DML**             | Data Manipulation Language (INSERT, UPDATE, DELETE) |
