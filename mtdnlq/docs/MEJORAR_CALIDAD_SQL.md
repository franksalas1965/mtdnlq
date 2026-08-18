# Cómo disminuir errores en la generación de SQL

Guía práctica para mejorar la calidad del SQL que produce el modelo LLM en **MTD-NLQ** sobre la base `mtd10` (133 tablas, escala 1:10 000).

---

## Por qué falla el modelo

El servicio envía al LLM **todo el esquema** de los esquemas permitidos (`ALLOWED_SCHEMAS`), más ejemplos few-shot y la pregunta del usuario. Con un modelo pequeño como `qwen2.5-coder:1.5b` es frecuente recibir HTTP **422** con:

```json
{
  "detail": {
    "error": "sql_generation_failed",
    "message": "No se pudo generar SQL válido..."
  }
}
```

Las causas más habituales:

| Causa | Qué ocurre |
|-------|------------|
| Esquema muy grande | El modelo elige tablas o columnas que no existen |
| Nombres poco intuitivos | `zanjas_y_canales_secos_lineal` vs. pregunta “canales secos” |
| Modelo pequeño | Inventa sintaxis, omite comillas en esquemas `10_*`, no respeta SRID |
| Pregunta ambigua | “Muéstrame el mapa” no indica capa ni tipo de dato |
| Timeout | Ollama tarda más de `OLLAMA_TIMEOUT_SECONDS` (180 s por defecto) |

MTD-NLQ reintenta hasta **3 veces** (`MAX_LLM_RETRIES=2` + intento inicial) enviando el error anterior al modelo. Si tras eso el SQL sigue inválido, devuelve 422.

---

## Cómo MTD-NLQ usa el esquema en el prompt

El módulo `schema_inspector` lee del catálogo de PostgreSQL:

- Comentarios de **tabla** (`COMMENT ON TABLE`)
- Comentarios de **columna** (`COMMENT ON COLUMN`)
- Tipos de datos, geometría PostGIS y SRID

Eso se formatea así en el prompt del LLM:

```
Tabla: 10_hidrografia.rios_y_arroyos_lineal
  Descripción: Cursos de agua: ríos y arroyos del MTD 1:10000
  Geometría: columna 'geom' tipo LINESTRING SRID=4267
  Columnas:
    - geo_id (character varying)
    - nombre (character varying)  -- Nombre del curso de agua
    - geocodigo (character varying)  -- Código temático MTD
    ...
```

**Sí ayuda** añadir comentarios: el modelo dispone de pistas semánticas (“río”, “habitantes”, “presa”) además del nombre técnico de la tabla. No sustituye un modelo mayor, pero reduce errores de **tabla equivocada** y **columna inexistente**.

---

## 1. Comentarios en PostgreSQL (recomendado)

### Sintaxis básica

Los esquemas MTD llevan guion bajo y **requieren comillas dobles**:

```sql
-- Tabla
COMMENT ON TABLE "10_hidrografia".rios_y_arroyos_lineal IS
  'Cursos de agua permanentes: ríos y arroyos. Geometría línea. Sinónimos: caudal, cauce.';

-- Columna
COMMENT ON COLUMN "10_puntos_poblados".ciudad_puntual.cantidad_habitantes IS
  'Número de habitantes del asentamiento; usar en filtros numéricos (>, <).';

-- Quitar un comentario
COMMENT ON TABLE "10_hidrografia".rios_y_arroyos_lineal IS NULL;
```

### Qué comentar primero (prioridad)

1. **Tablas más consultadas** — las del [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md) y las [preguntas sugeridas](PRUEBAS_INICIALES.md#preguntas-de-prueba-sugeridas).
2. **Columnas no obvias** — `geocodigo`, `nomenclatura`, `categoria_poblacional`, campos numéricos de filtro.
3. **Tablas con nombres largos o similares** — p. ej. `embalses_*` vs `presas_*`, `vias_de_comunicacion_*` vs `caminos_y_senderos_*`.

No hace falta comentar las ~133 tablas de golpe: empiece por 15–30 capas frecuentes y amplíe según las preguntas reales de los usuarios.

### Plantilla de comentario útil para el LLM

Incluya en una sola frase:

- **Qué representa** la capa (sustantivo claro en español).
- **Tipo geométrico** (punto, línea, polígono) si no es obvio por el sufijo.
- **Sinónimos** que usaría un usuario (“carretera” → `vias_de_comunicacion`).
- **Columna clave para filtrar** si aplica (`nombre`, `cantidad_habitantes`).

Ejemplo:

```sql
COMMENT ON TABLE "10_red_vial".vias_de_comunicacion_lineal IS
  'Carreteras y vías principales (líneas). Sinónimos: carretera, autopista, camino principal. Filtrar por nomenclatura o descripcion.';

COMMENT ON COLUMN "10_red_vial".vias_de_comunicacion_lineal.nomenclatura IS
  'Código alfanumérico de la vía según nomenclatura MTD.';
```

### Script de ejemplo para mtd10

Guarde como `docs/sql/comentarios_mtd10_ejemplo.sql` y ejecútelo en pgAdmin o `psql`:

```sql
-- Hidrografía
COMMENT ON TABLE "10_hidrografia".rios_y_arroyos_lineal IS
  'Ríos y arroyos (líneas). Preguntas: cuántos ríos, ríos con nombre X.';
COMMENT ON COLUMN "10_hidrografia".rios_y_arroyos_lineal.nombre IS
  'Nombre del curso de agua; usar ILIKE para búsqueda parcial.';

COMMENT ON TABLE "10_hidrografia".embalses_areal IS
  'Embalses y lagos artificiales (polígonos). No confundir con presas en 10_hidrografia_presas.';

-- Presas (esquema aparte)
COMMENT ON TABLE "10_hidrografia_presas".presas_areal IS
  'Presas y diques de retención (polígonos). Preguntas: presas del MTD, represas.';

-- Población
COMMENT ON TABLE "10_puntos_poblados".ciudad_puntual IS
  'Ciudades y pueblos (puntos). Filtrar por cantidad_habitantes o categoria_poblacional.';
COMMENT ON COLUMN "10_puntos_poblados".ciudad_puntual.cantidad_habitantes IS
  'Habitantes; comparaciones numéricas (> 10000, etc.).';

-- Límites y relieve
COMMENT ON TABLE "10_limites_estatales".limites_estatales_lineal IS
  'Fronteras entre provincias/estados (líneas). Preguntas: límites estatales, fronteras administrativas.';

COMMENT ON TABLE "10_relieve".curvas_lineal IS
  'Curvas de nivel del terreno (líneas). Preguntas: relieve, topografía, curvas de nivel.';

-- Infraestructura
COMMENT ON TABLE "10_red_vial".vias_de_comunicacion_lineal IS
  'Vías de comunicación principales (líneas). Sinónimos: carreteras, caminos, red vial.';

COMMENT ON TABLE "10_puntos_de_apoyo".puntos_de_apoyo_puntual IS
  'Puntos de apoyo topográfico y geodésicos (puntos). Preguntas: puntos de apoyo, vértices.';

COMMENT ON TABLE "10_objetivos_economicos".fabricas_e_industrias_puntual IS
  'Fábricas e instalaciones industriales (puntos).';
```

### Cómo ejecutar los comentarios

**pgAdmin:** Query Tool → pegar SQL → Execute (F5).

**psql (PowerShell, PostgreSQL en Windows):**

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -p 5433 -U postgres -d mtd10 -f "D:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq\docs\sql\comentarios_mtd10_ejemplo.sql"
```

**Verificar que se guardaron:**

```sql
SELECT
  n.nspname AS esquema,
  c.relname AS tabla,
  obj_description(c.oid) AS comentario_tabla
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname LIKE '10\_%' ESCAPE '\'
  AND c.relkind = 'r'
  AND obj_description(c.oid) IS NOT NULL
ORDER BY 1, 2;
```

### Refrescar el caché de MTD-NLQ

Los comentarios se leen al construir el prompt, pero el esquema se **cachea** (`SCHEMA_CACHE_TTL=300` segundos por defecto). Tras cambiar comentarios:

```powershell
# Forzar recarga
Invoke-RestMethod "http://localhost:8001/api/v1/schema?refresh=true"
```

O espere 5 minutos, o reinicie el servicio.

Compruebe que el comentario aparece en la respuesta JSON del endpoint `/api/v1/schema` (campo `comment` en tabla y columnas).

---

## 2. Usar un modelo LLM más capaz

El cambio con **mayor impacto** suele ser subir de modelo. En `.env`:

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:7b
OLLAMA_TIMEOUT_SECONDS=300
```

Descargar en WSL:

```bash
ollama pull qwen2.5-coder:7b
```

| Modelo | VRAM aprox. | Calidad SQL mtd10 | Velocidad |
|--------|-------------|-------------------|-----------|
| `qwen2.5-coder:1.5b` | ~1 GB | Baja (mucho 422) | Rápido |
| `qwen2.5-coder:7b` | ~5 GB | Media–alta | Moderado |
| `qwen2.5:14b` | ~9 GB | Alta | Lento |
| GPT-4o / Claude (API) | N/A | Muy alta | Depende de red |

Reinicie MTD-NLQ tras cambiar `.env`.

---

## 3. Formular preguntas concretas

El prompt ya incluye convenciones (`10_` = 1:10 000, SRID 4267, sufijos `_lineal` / `_areal` / `_puntual`). Las preguntas que mejor funcionan:

**Bien:**

- *¿Cuántos ríos y arroyos hay?*
- *Lista las ciudades con más de 10000 habitantes*
- *Dame los límites estatales en GeoJSON*
- *Curvas de nivel del relieve*

**Mal (ambiguas):**

- *Muéstrame el mapa*
- *Dame toda la hidrografía*
- *Elementos cerca de La Habana* (sin indicar capa ni criterio espacial)

Incluya en la pregunta **qué tipo de objeto** busca (río, ciudad, presa, carretera) y, si aplica, **filtro** (nombre, conteo, umbral numérico).

Para conteos use `"output_format": "table"`. Para mapas use `"output_format": "geojson"`.

---

## 4. Reducir el esquema expuesto (`ALLOWED_SCHEMAS`)

Si solo consultará hidrografía y población, limite los esquemas en `.env`:

```env
ALLOWED_SCHEMAS=10_hidrografia,10_hidrografia_presas,10_puntos_poblados
```

Menos tablas en el prompt → menos confusión para el modelo. **Inconveniente:** preguntas sobre esquemas omitidos fallarán aunque existan en la BD.

Lista completa recomendada para mtd10 general: ver [GUIA_USO_SERVICIO.md](GUIA_USO_SERVICIO.md#4-conectar-la-base-de-datos-mtd10).

---

## 5. Ajustes de comportamiento en `.env`

```env
# Más tiempo para modelos grandes en CPU
OLLAMA_TIMEOUT_SECONDS=300

# Un reintento extra ante SQL inválido (4 intentos totales)
MAX_LLM_RETRIES=3

# Recargar esquema/comentarios más a menudo mientras documenta tablas
SCHEMA_CACHE_TTL=60
```

---

## 6. Qué valida MTD-NLQ (y por qué se rechaza el SQL)

El validador exige:

- Sentencia que empiece por `SELECT` o `WITH`
- Sin `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.
- Respuesta no vacía del LLM

Si falta `LIMIT`, el servicio añade `LIMIT 100` automáticamente.

Errores frecuentes del modelo que **no** pasan validación o fallan en ejecución:

- Explicación en markdown en lugar de SQL puro
- Esquema sin comillas: `10_hidrografia.tabla` → debe ser `"10_hidrografia".tabla`
- Tabla inventada: `10_hidrografia.rios` (no existe; la real es `rios_y_arroyos_lineal`)
- Columna incorrecta: `poblacion` en lugar de `cantidad_habitantes`

Los comentarios y un modelo mayor atacan sobre todo los dos últimos puntos.

---

## 7. Mejoras avanzadas (requieren cambio de código)

Si tras comentarios + modelo 7b aún hay errores en dominios concretos:

| Medida | Dónde | Efecto |
|--------|-------|--------|
| Más ejemplos few-shot | `src/mtdnlq/nlq/prompt_builder.py` → `FEW_SHOT_EXAMPLES` | Enseña al modelo consultas reales de su organización |
| Vista SQL simplificada | BD + prompt manual | Expone solo columnas renombradas (`nombre_rio` en lugar de joins) |
| Fine-tuning del modelo | Fuera del alcance de esta guía | Máxima precisión para un vocabulario fijo |

Para añadir un few-shot, copie el patrón existente (pregunta + SQL con esquema entre comillas y `ST_AsGeoJSON` cuando haya geometría).

---

## 8. Flujo de trabajo recomendado

```
1. Identificar preguntas que fallan (422) o SQL incorrecto
2. Anotar qué tabla/columna esperaba el usuario
3. Añadir COMMENT ON TABLE/COLUMN en PostgreSQL
4. GET /api/v1/schema?refresh=true
5. Repetir la misma pregunta
6. Si sigue fallando → subir a qwen2.5-coder:7b
7. Documentar nuevas preguntas exitosas como few-shot (opcional)
```

---

## 9. Checklist rápido

| Acción | ¿Hecho? |
|--------|---------|
| Comentarios en 15–30 tablas frecuentes | ☐ |
| `schema?refresh=true` tras comentarios | ☐ |
| Modelo ≥ 7b si hay GPU/RAM suficiente | ☐ |
| Preguntas concretas (capa + filtro) | ☐ |
| `ALLOWED_SCHEMAS` acotado al uso real | ☐ |
| `OLLAMA_TIMEOUT_SECONDS` aumentado si hay timeout | ☐ |

---

## Referencias

- [PRUEBAS_INICIALES.md](PRUEBAS_INICIALES.md) — pruebas y error 422
- [ESQUEMA_MTD10.md](ESQUEMA_MTD10.md) — listado de tablas y columnas
- [CONVENCION_ESCALAS.md](CONVENCION_ESCALAS.md) — prefijos `10_`, `25_`, `100_`
- [DESPLIEGUE_PRODUCCION.md](DESPLIEGUE_PRODUCCION.md) §10 — resumen de optimización en producción
- Código: `src/mtdnlq/db/schema_inspector.py`, `src/mtdnlq/nlq/prompt_builder.py`
