# GeoNLQ — Guía de Escalado: Añadir Nuevas Tablas

**Versión:** 1.0  
**Aplica a:** GeoNLQ con modelo fine-tuneado ya en producción  
**Tiempo estimado:** 2–4 horas según número de tablas nuevas

---

## Índice

1. [Visión general del impacto](#1-visión-general-del-impacto)
2. [Paso 1 — DDL y estructura de la tabla](#2-paso-1--ddl-y-estructura-de-la-tabla)
3. [Paso 2 — Actualizar el prompt del LLM](#3-paso-2--actualizar-el-prompt-del-llm)
4. [Paso 3 — Generar nuevos datos de entrenamiento](#4-paso-3--generar-nuevos-datos-de-entrenamiento)
5. [Paso 4 — Re-entrenar el modelo en Colab](#5-paso-4--re-entrenar-el-modelo-en-colab)
6. [Paso 5 — Exportar y desplegar el nuevo modelo](#6-paso-5--exportar-y-desplegar-el-nuevo-modelo)
7. [Paso 6 — Verificación post-despliegue](#7-paso-6--verificación-post-despliegue)
8. [Referencia rápida de componentes](#8-referencia-rápida-de-componentes)
9. [Ejemplo completo: tabla vegetacion](#9-ejemplo-completo-tabla-vegetacion)

---

## 1. Visión general del impacto

Cuando añades una nueva tabla al sistema, cada componente de GeoNLQ se ve afectado de manera diferente:

| Componente | Archivo | ¿Requiere cambio? | Esfuerzo |
|---|---|---|---|
| DDL / PostGIS | `docs/schema/` | Sí, crear migration | 30 min |
| Schema inspector | `db/schema_inspector.py` | **No** — detecta automático | Ninguno |
| SQL validator | `nlq/sql_validator.py` | No | Ninguno |
| Prompt few-shot | `nlq/prompt_builder.py` | **Sí** — crítico | 30 min |
| Datos entrenamiento | `modelos_locales/scripts/` | **Sí** — para fine-tuning | 1–2 h |
| Modelo fine-tuneado | Ollama / GGUF | **Sí** — re-entrenar | 2–3 h en Colab |
| Modelfile Ollama | `modelos_locales/ollama/` | Sí — actualizar esquema | 15 min |
| Documentación | `docs/` | Sí | 30 min |

> **Importante:** si solo usas el modelo base (`qwen2.5-coder:1.5b` sin fine-tuning),
> basta con actualizar el prompt y el Modelfile. El re-entrenamiento es necesario
> solo si tienes el modelo fine-tuneado en producción.

---

## 2. Paso 1 — DDL y estructura de la tabla

### 2.1 Crear el archivo de migración

Crea un nuevo archivo SQL siguiendo la numeración existente en `docs/schema/`:

```
docs/schema/
├── 001_initial_schema.sql   ← esquema original
├── 002_sample_data.sql      ← datos de prueba
└── 003_vegetacion.sql       ← tu nueva migración ← aquí
```

### 2.2 Estructura recomendada del DDL

```sql
-- =============================================================================
-- GeoNLQ — Migración 003: tabla vegetacion
-- Fecha: YYYY-MM-DD
-- =============================================================================

CREATE TABLE IF NOT EXISTS vegetacion (
    id                  SERIAL PRIMARY KEY,
    codigo              VARCHAR(20)   NOT NULL UNIQUE,
    tipo_cobertura      VARCHAR(50)   NOT NULL
                            CHECK (tipo_cobertura IN ('bosque', 'matorral',
                                   'pastizal', 'cultivo', 'manglar', 'otro')),
    especie_dominante   VARCHAR(100),
    densidad            VARCHAR(20)   DEFAULT 'media'
                            CHECK (densidad IN ('baja', 'media', 'alta')),
    municipio_id        INTEGER       REFERENCES municipios(id) ON DELETE SET NULL,
    area_ha             NUMERIC(12,4),
    observaciones       TEXT,
    geom                GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índice espacial obligatorio
CREATE INDEX IF NOT EXISTS idx_vegetacion_geom
    ON vegetacion USING GIST (geom);

-- Índice FK
CREATE INDEX IF NOT EXISTS idx_vegetacion_municipio_id
    ON vegetacion (municipio_id);

-- Índice trigrama para búsqueda de texto
CREATE INDEX IF NOT EXISTS idx_vegetacion_especie_trgm
    ON vegetacion USING GIN (especie_dominante gin_trgm_ops);

-- Trigger updated_at
CREATE TRIGGER trg_vegetacion_updated_at
    BEFORE UPDATE ON vegetacion
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE vegetacion IS 'Cobertura vegetal y uso del suelo';
COMMENT ON COLUMN vegetacion.tipo_cobertura IS 'Clasificación de cobertura vegetal';
COMMENT ON COLUMN vegetacion.densidad IS 'Densidad de cobertura: baja, media, alta';
```

### 2.3 Aplicar la migración en el contenedor Docker

```bash
# En WSL
docker exec -i -e PGPASSWORD='Gispostgres123!' postgres14-3.3 \
    psql -U postgres -d geonlq \
    < /mnt/d/proyectos/AI/Analisis\ en\ lenguaje\ Natural/geonlq/docs/schema/003_vegetacion.sql

# Verificar que se creó correctamente
docker exec -it -e PGPASSWORD='Gispostgres123!' postgres14-3.3 \
    psql -U postgres -d geonlq \
    -c "\d vegetacion"
```

### 2.4 Verificar que el schema inspector la detecta

```bash
# Con el servicio GeoNLQ corriendo, forzar refresco del caché
curl -X POST http://localhost:8000/api/v1/schema/refresh

# Ver el esquema actualizado
curl http://localhost:8000/api/v1/schema | python3 -m json.tool
# La tabla 'vegetacion' debe aparecer en la lista
```

---

## 3. Paso 2 — Actualizar el prompt del LLM

Este es el cambio más crítico. Sin él, el modelo no sabe que la tabla existe.

### 3.1 Editar `src/geonlq/nlq/prompt_builder.py`

Localiza la sección `SCHEMA_DESCRIPTION` y añade la nueva tabla:

```python
# ANTES
SCHEMA_DESCRIPTION = """
Tablas disponibles en la base de datos PostGIS:

- municipios(id, codigo, nombre, provincia, area_km2, poblacion,
             geom MULTIPOLYGON 4326)
- viales(id, codigo, nombre, tipo_via[autopista|carretera|camino|otro],
         categoria[nacional|provincial|local], longitud_km, estado[bueno|regular|malo|en_obras],
         geom MULTILINESTRING 4326)
- puentes(id, codigo, nombre, vial_id FK→viales, municipio_id FK→municipios,
          longitud_m, carga_maxima_tn, tipo_estructura[hormigon|metal|mixto|madera|otro],
          año_construccion, estado[bueno|regular|malo|cerrado], pk_vial,
          geom POINT 4326)
"""

# DESPUÉS — añadir la nueva tabla al final
SCHEMA_DESCRIPTION = """
Tablas disponibles en la base de datos PostGIS:

- municipios(id, codigo, nombre, provincia, area_km2, poblacion,
             geom MULTIPOLYGON 4326)
- viales(id, codigo, nombre, tipo_via[autopista|carretera|camino|otro],
         categoria[nacional|provincial|local], longitud_km, estado[bueno|regular|malo|en_obras],
         geom MULTILINESTRING 4326)
- puentes(id, codigo, nombre, vial_id FK→viales, municipio_id FK→municipios,
          longitud_m, carga_maxima_tn, tipo_estructura[hormigon|metal|mixto|madera|otro],
          año_construccion, estado[bueno|regular|malo|cerrado], pk_vial,
          geom POINT 4326)
- vegetacion(id, codigo, tipo_cobertura[bosque|matorral|pastizal|cultivo|manglar|otro],
             especie_dominante, densidad[baja|media|alta], municipio_id FK→municipios,
             area_ha, geom MULTIPOLYGON 4326)
"""
```

### 3.2 Añadir ejemplos few-shot para la nueva tabla

En el mismo archivo, localiza el bloque `FEW_SHOT_EXAMPLES` y añade 3 ejemplos representativos que cubran los casos más comunes:

```python
# Ejemplo 1: filtro simple por tipo
{
    "pregunta": "Dame las zonas de bosque en la provincia de Pinar del Río",
    "sql": (
        "SELECT v.codigo, v.tipo_cobertura, v.especie_dominante, v.area_ha, "
        "ST_AsGeoJSON(v.geom)::json AS geometry "
        "FROM vegetacion v "
        "JOIN municipios m ON v.municipio_id = m.id "
        "WHERE v.tipo_cobertura = 'bosque' "
        "AND m.provincia ILIKE '%Pinar del Río%' "
        "ORDER BY v.area_ha DESC LIMIT 100;"
    )
},
# Ejemplo 2: consulta espacial (proximidad a otra tabla)
{
    "pregunta": "¿Qué vegetación hay a menos de 500 metros de la Autopista Nacional?",
    "sql": (
        "SELECT v.tipo_cobertura, v.especie_dominante, v.densidad, "
        "ST_AsGeoJSON(v.geom)::json AS geometry "
        "FROM vegetacion v "
        "JOIN viales vi ON ST_DWithin(v.geom::geography, vi.geom::geography, 500) "
        "WHERE vi.nombre ILIKE '%Autopista Nacional%' "
        "LIMIT 100;"
    )
},
# Ejemplo 3: agregación
{
    "pregunta": "¿Cuántas hectáreas de manglar hay en total?",
    "sql": (
        "SELECT SUM(area_ha) AS total_hectareas "
        "FROM vegetacion "
        "WHERE tipo_cobertura = 'manglar';"
    )
},
```

### 3.3 Actualizar el Modelfile de Ollama

Edita `modelos_locales/ollama/Modelfile` y `Modelfile.base` para añadir la tabla al esquema del SYSTEM prompt:

```
# Línea a añadir en la sección ESQUEMA del SYSTEM prompt
- vegetacion: id, codigo, tipo_cobertura, especie_dominante, densidad,
              municipio_id(FK), area_ha, geom(MULTIPOLYGON,4326)
```

Recrea el modelo base en Ollama para que tome los cambios:

```bash
cd modelos_locales/ollama
ollama create geonlq-base -f Modelfile.base
```

---

## 4. Paso 3 — Generar nuevos datos de entrenamiento

### 4.1 Ampliar `generate_training_data.py`

Abre `modelos_locales/scripts/generate_training_data.py` y añade un bloque de plantillas para la nueva tabla. Sigue el mismo patrón que los bloques existentes:

```python
# ── Plantillas para vegetacion ────────────────────────────────────────────────
TIPOS_COBERTURA = ["bosque", "matorral", "pastizal", "cultivo", "manglar"]
DENSIDADES      = ["baja", "media", "alta"]
DISTANCIAS_VEG  = [100, 250, 500, 1000, 2000]

plantillas_vegetacion = [
    # Filtro por tipo en municipio/provincia
    (
        "Dame las zonas de {tipo} en {municipio}",
        "SELECT v.codigo, v.tipo_cobertura, v.especie_dominante, v.area_ha, "
        "ST_AsGeoJSON(v.geom)::json AS geometry FROM vegetacion v "
        "JOIN municipios m ON v.municipio_id = m.id "
        "WHERE v.tipo_cobertura = '{tipo}' AND m.nombre ILIKE '%{municipio}%' LIMIT 100;"
    ),
    # Densidad
    (
        "Vegetación de densidad {densidad} en la provincia de {provincia}",
        "SELECT v.tipo_cobertura, v.especie_dominante, v.area_ha, "
        "ST_AsGeoJSON(v.geom)::json AS geometry FROM vegetacion v "
        "JOIN municipios m ON v.municipio_id = m.id "
        "WHERE v.densidad = '{densidad}' AND m.provincia ILIKE '%{provincia}%' LIMIT 100;"
    ),
    # Proximidad a viales
    (
        "¿Qué vegetación hay a menos de {dist} metros de {via}?",
        "SELECT v.tipo_cobertura, v.especie_dominante, v.densidad, "
        "ST_AsGeoJSON(v.geom)::json AS geometry FROM vegetacion v "
        "JOIN viales vi ON ST_DWithin(v.geom::geography, vi.geom::geography, {dist}) "
        "WHERE vi.nombre ILIKE '%{via}%' LIMIT 100;"
    ),
    # Área total por tipo
    (
        "¿Cuántas hectáreas de {tipo} hay en {provincia}?",
        "SELECT SUM(v.area_ha) AS total_hectareas FROM vegetacion v "
        "JOIN municipios m ON v.municipio_id = m.id "
        "WHERE v.tipo_cobertura = '{tipo}' AND m.provincia ILIKE '%{provincia}%';"
    ),
    # Intersección espacial con municipio
    (
        "Zonas de {tipo} dentro del municipio de {municipio}",
        "SELECT v.codigo, v.tipo_cobertura, v.area_ha, "
        "ST_AsGeoJSON(v.geom)::json AS geometry FROM vegetacion v "
        "JOIN municipios m ON ST_Intersects(v.geom, m.geom) "
        "WHERE v.tipo_cobertura = '{tipo}' AND m.nombre ILIKE '%{municipio}%' LIMIT 100;"
    ),
]

# Generar ejemplos combinando plantillas con valores
for plantilla_q, plantilla_sql in plantillas_vegetacion:
    for tipo in TIPOS_COBERTURA:
        for municipio in MUNICIPIOS[:5]:   # usar los primeros 5 para no inflar demasiado
            ejemplos.append({
                "pregunta": plantilla_q.format(tipo=tipo, municipio=municipio, ...),
                "sql":      plantilla_sql.format(tipo=tipo, municipio=municipio, ...),
            })
```

### 4.2 Regenerar el dataset completo

```bash
cd modelos_locales/scripts
python generate_training_data.py \
    --output ../datos/ \
    --split

# Verificar los conteos
wc -l ../datos/train.jsonl ../datos/eval.jsonl
# Esperar: train ~1000+, eval ~100+
```

### 4.3 Revisar manualmente una muestra

Antes de entrenar, revisa 20–30 ejemplos al azar para asegurarte de que el SQL generado es correcto:

```bash
python3 -c "
import json, random
with open('../datos/train.jsonl') as f:
    lines = f.readlines()
sample = random.sample(lines, 20)
for line in sample:
    ex = json.loads(line)
    msgs = ex['messages']
    print('Q:', msgs[1]['content'])
    print('A:', msgs[2]['content'])
    print('---')
"
```

---

## 5. Paso 4 — Re-entrenar el modelo en Colab

### 5.1 Subir los datos nuevos a Colab

En Google Colab, ejecuta:

```python
# Opción A: subir desde tu máquina
from google.colab import files
files.upload()   # selecciona train.jsonl y eval.jsonl

# Opción B: montar Google Drive
from google.colab import drive
drive.mount('/content/drive')
# copiar desde Drive a /content/
```

### 5.2 Estrategia recomendada: mezclar datos viejos + nuevos

**No entrenes solo con los datos nuevos.** El modelo olvidaría lo aprendido antes (catastrophic forgetting). Siempre mezcla el dataset original con el nuevo:

```bash
# En Colab — mezclar los datasets
cat datos_v1/train.jsonl datos_v2_vegetacion/train.jsonl | shuf > train_combined.jsonl
cat datos_v1/eval.jsonl  datos_v2_vegetacion/eval.jsonl  | shuf > eval_combined.jsonl

wc -l train_combined.jsonl   # total combinado
```

### 5.3 Ejecutar el fine-tuning

```bash
# En Colab
python finetune_qlora.py \
    --train_file train_combined.jsonl \
    --eval_file  eval_combined.jsonl \
    --output_dir ./geonlq-sql-v2-adapter \
    --num_epochs 3
```

El entrenamiento tarda aproximadamente:
- Dataset de ~1000 ejemplos → 20–30 minutos en T4
- Dataset de ~2000 ejemplos → 40–50 minutos en T4

### 5.4 Monitorear el entrenamiento

Durante el entrenamiento observa dos métricas clave:

```
Step  100 | train_loss: 1.42 | eval_loss: 1.38  ← bien, eval baja con train
Step  200 | train_loss: 0.89 | eval_loss: 0.91  ← bien
Step  300 | train_loss: 0.61 | eval_loss: 0.74  ← bien
Step  400 | train_loss: 0.45 | eval_loss: 0.89  ← ALERTA: eval sube = overfitting
```

Si `eval_loss` empieza a subir mientras `train_loss` baja, el entrenamiento se detiene automáticamente (early stopping ya configurado en `finetune_qlora.py`). El mejor checkpoint se guarda automáticamente.

---

## 6. Paso 5 — Exportar y desplegar el nuevo modelo

### 6.1 Exportar a GGUF desde Colab

```bash
# En Colab — adaptar ADAPTER_DIR al nuevo adaptador
ADAPTER_DIR="./geonlq-sql-v2-adapter" bash export_to_gguf.sh
# Genera: geonlq-sql-gguf/geonlq-sql-Q4_K_M.gguf
```

### 6.2 Descargar el GGUF a tu máquina

```python
# En Colab
from google.colab import files
files.download('geonlq-sql-gguf/geonlq-sql-Q4_K_M.gguf')
```

### 6.3 Importar en Ollama (en WSL)

```bash
# Copiar el GGUF al directorio del proyecto
cp ~/Downloads/geonlq-sql-Q4_K_M.gguf \
   "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/modelos_locales/ollama/"

# Crear el nuevo modelo en Ollama
cd "/mnt/d/proyectos/AI/Analisis en lenguaje Natural/modelos_locales/ollama"
ollama create geonlq-sql-v2 -f Modelfile

# Verificar
ollama list
# geonlq-sql-v2   ... debe aparecer
```

### 6.4 Actualizar la configuración del servicio

Edita el `.env` del proyecto para apuntar al nuevo modelo:

```bash
# En ~/geonlq/.env  (o donde tengas el servicio)
LLM_MODEL=geonlq-sql-v2     # ← cambiar de geonlq-sql a geonlq-sql-v2
```

### 6.5 Reiniciar el servicio GeoNLQ

```bash
# Detener el servicio actual (Ctrl+C si está en primer plano, o:)
pkill -f "uvicorn geonlq.main:app"

# Reiniciar
cd ~/geonlq
source .venv/bin/activate
uvicorn geonlq.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 7. Paso 6 — Verificación post-despliegue

### 7.1 Pruebas funcionales básicas

Ejecuta estas consultas de prueba y verifica que devuelven resultados correctos:

```bash
BASE="http://localhost:8000/api/v1"

# Prueba 1: consulta simple a la nueva tabla
curl -s -X POST $BASE/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Dame las zonas de bosque", "include_geometry": false}' \
  | python3 -m json.tool

# Prueba 2: consulta espacial cruzando tablas
curl -s -X POST $BASE/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Vegetación a menos de 500 metros de la Carretera Central", "include_geometry": false}' \
  | python3 -m json.tool

# Prueba 3: verificar que las tablas antiguas siguen funcionando
curl -s -X POST $BASE/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Puentes con carga mayor a 10 toneladas", "include_geometry": false}' \
  | python3 -m json.tool
```

### 7.2 Revisar el historial de consultas

```sql
-- Conectar a PostgreSQL y revisar las últimas consultas
SELECT question, status, result_count, execution_ms, error_msg
FROM query_history
ORDER BY created_at DESC
LIMIT 20;

-- Tasa de éxito reciente
SELECT status, COUNT(*) 
FROM query_history 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status;
```

### 7.3 Criterios de aceptación

Antes de considerar el despliegue completo, verifica:

- [ ] La nueva tabla aparece en `/api/v1/schema`
- [ ] Al menos 3 consultas simples a la nueva tabla devuelven resultados
- [ ] Al menos 1 consulta espacial cruzando la nueva tabla con otras funciona
- [ ] Las consultas a tablas anteriores (puentes, viales, municipios) siguen funcionando
- [ ] No hay errores `status: error` en los últimos 10 intentos de prueba
- [ ] El tiempo de respuesta es menor a 30 segundos por consulta

---

## 8. Referencia rápida de componentes

```
src/geonlq/
├── nlq/
│   ├── prompt_builder.py    ← EDITAR: añadir tabla al SCHEMA_DESCRIPTION
│   │                                  añadir 3 ejemplos few-shot
│   ├── sql_validator.py     ← NO tocar
│   └── translator.py        ← NO tocar
├── db/
│   └── schema_inspector.py  ← NO tocar (automático)
└── services/
    └── query_service.py     ← NO tocar

modelos_locales/
├── scripts/
│   ├── generate_training_data.py  ← EDITAR: añadir plantillas nuevas
│   └── finetune_qlora.py          ← NO tocar (genérico)
└── ollama/
    ├── Modelfile                  ← EDITAR: añadir tabla al SYSTEM
    └── Modelfile.base             ← EDITAR: añadir tabla al SYSTEM

docs/schema/
└── 00N_nueva_tabla.sql            ← CREAR: migración DDL
```

---

## 9. Ejemplo completo: tabla vegetacion

Checklist de pasos para el caso específico de añadir `vegetacion`:

```
□ 1. Crear docs/schema/003_vegetacion.sql con DDL + índices GIST + GIN
□ 2. Aplicar migración: docker exec ... psql < 003_vegetacion.sql
□ 3. Verificar con: curl /api/v1/schema/refresh && curl /api/v1/schema
□ 4. Editar prompt_builder.py → añadir vegetacion al SCHEMA_DESCRIPTION
□ 5. Editar prompt_builder.py → añadir 3 ejemplos few-shot
□ 6. Editar Modelfile y Modelfile.base → añadir vegetacion al SYSTEM
□ 7. Editar generate_training_data.py → añadir plantillas de vegetacion
□ 8. Ejecutar: python generate_training_data.py --output ../datos/ --split
□ 9. Revisar muestra manual de 20 ejemplos generados
□ 10. En Colab: mezclar dataset v1 + v2 → entrenar → exportar GGUF
□ 11. Importar GGUF en Ollama: ollama create geonlq-sql-v2 -f Modelfile
□ 12. Actualizar .env: LLM_MODEL=geonlq-sql-v2
□ 13. Reiniciar servicio GeoNLQ
□ 14. Ejecutar pruebas funcionales y verificar criterios de aceptación
□ 15. Actualizar este documento con la versión del modelo y fecha
```

---

## Historial de versiones del modelo

| Versión | Fecha | Tablas incluidas | Dataset (ejemplos) | Notas |
|---------|-------|------------------|--------------------|-------|
| v1 | YYYY-MM-DD | municipios, viales, puentes | ~800 | Versión inicial |
| v2 | — | + vegetacion | — | Pendiente |

*Actualizar esta tabla cada vez que se re-entrene el modelo.*
