"""
Constructor de prompts para traducción NL → SQL.
Incluye esquema de BD y ejemplos few-shot específicos para consultas geoespaciales.
"""
from ..db.schema_inspector import schema_inspector

# Ejemplos few-shot basados en el esquema real mtd10 (volcado mtd10.sql)
FEW_SHOT_EXAMPLES = """
EJEMPLOS DE CONSULTAS SOBRE MTD 1:10 000 (base mtd10, SRID 4267):

Pregunta: ¿Cuántos ríos y arroyos hay en el mapa?
SQL: SELECT COUNT(*) AS total_rios
     FROM "10_hidrografia".rios_y_arroyos_lineal;

Pregunta: Dame los ríos con nombre que contenga "Yateras"
SQL: SELECT geo_id, nombre, geocodigo, descripcion,
            ST_AsGeoJSON(geom)::json AS geometry
     FROM "10_hidrografia".rios_y_arroyos_lineal
     WHERE nombre ILIKE '%yateras%'
     LIMIT 100;

Pregunta: Lista las ciudades con más de 10000 habitantes
SQL: SELECT nombre, cantidad_habitantes, categoria_poblacional, geocodigo,
            ST_AsGeoJSON(geom)::json AS geometry
     FROM "10_puntos_poblados".ciudad_puntual
     WHERE cantidad_habitantes > 10000
     ORDER BY cantidad_habitantes DESC
     LIMIT 100;

Pregunta: Muéstrame las presas del MTD
SQL: SELECT geo_id, geocodigo, nomenclatura, descripcion,
            ST_AsGeoJSON(geom)::json AS geometry
     FROM "10_hidrografia_presas".presas_areal
     LIMIT 100;

Pregunta: Dame los límites estatales
SQL: SELECT geo_id, geocodigo, nomenclatura, descripcion,
            ST_AsGeoJSON(geom)::json AS geometry
     FROM "10_limites_estatales".limites_estatales_lineal
     LIMIT 100;

Pregunta: ¿Cuántos puntos de apoyo topográfico hay?
SQL: SELECT COUNT(*) AS total_puntos_apoyo
     FROM "10_puntos_de_apoyo".puntos_de_apoyo_puntual;

Pregunta: Vías de comunicación principales
SQL: SELECT geo_id, geocodigo, nomenclatura, descripcion,
            ST_AsGeoJSON(geom)::json AS geometry
     FROM "10_red_vial".vias_de_comunicacion_lineal
     LIMIT 100;

Pregunta: Curvas de nivel del relieve
SQL: SELECT geo_id, geocodigo, nomenclatura, descripcion,
            ST_AsGeoJSON(geom)::json AS geometry
     FROM "10_relieve".curvas_lineal
     LIMIT 100;

Pregunta: Fábricas e industrias
SQL: SELECT geo_id, nombre, geocodigo, descripcion,
            ST_AsGeoJSON(geom)::json AS geometry
     FROM "10_objetivos_economicos".fabricas_e_industrias_puntual
     LIMIT 100;

Pregunta: Ríos que cruzan alguna carretera o vía de comunicación
SQL: SELECT r.geo_id, r.nombre, r.geocodigo, r.descripcion,
            ST_AsGeoJSON(r.geom)::json AS geometry
     FROM "10_hidrografia".rios_y_arroyos_lineal r
     WHERE EXISTS (
         SELECT 1 FROM "10_red_vial".vias_de_comunicacion_lineal v
         WHERE ST_Intersects(r.geom, v.geom)
     )
     LIMIT 100;

Pregunta: Ríos que cruzan una carretera y están a menos de 100 m de maleza compacta con espinas
SQL: WITH candidatos AS (
         SELECT DISTINCT r.geo_id
         FROM "10_areas_verdes_y_terrenos".malezas_areal m
         JOIN "10_hidrografia".rios_y_arroyos_lineal r
           ON ST_DWithin(r.geom::geography, m.geom::geography, 100)
         WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
           AND EXISTS (
               SELECT 1 FROM "10_red_vial".vias_de_comunicacion_lineal v
               WHERE ST_Intersects(r.geom, v.geom)
           )
         LIMIT 100
     )
     SELECT r.geo_id, r.nombre, r.geocodigo, r.descripcion,
            ST_AsGeoJSON(r.geom)::json AS geometry
     FROM "10_hidrografia".rios_y_arroyos_lineal r
     JOIN candidatos c USING (geo_id);
"""


def build_prompt(question: str, scale: int = 10000) -> str:
    """
    Construye el prompt completo para el LLM.

    Args:
        question: Pregunta del usuario en lenguaje natural.
        scale:    Denominador de escala MTD (10000 = 1:10 000).

    Returns:
        Prompt completo con esquema, ejemplos y pregunta.
    """
    schema_description = schema_inspector.build_schema_description(scale)
    prefix = scale // 1000

    return f"""{schema_description}

{FEW_SHOT_EXAMPLES}

INSTRUCCIONES ADICIONALES:
- ESCALA ACTIVA DE ESTA CONSULTA: 1:{prefix} 000 (prefijo de esquema "{prefix}_").
- CONVENCIÓN DE ESCALA: el prefijo numérico del esquema es el denominador de la escala × 1000.
  10_ = 1:10 000 (mtd10), 25_ = 1:25 000 (mtd25), 100_ = 1:100 000 (mtd100), etc.
  Ejemplo: "10_hidrografia" es hidrografía a 1:10 000; en mtd25 sería "25_hidrografia".
- Esquemas con comillas dobles: "{prefix}_hidrografia".tabla
- Geometrías en SRID 4267 (NAD27). Columna estándar: geom.
- Identificadores comunes: geo_id, geocodigo, nomenclatura, nombre, descripcion, escala.
- Sufijos de tabla: _areal (polígonos), _lineal (líneas), _puntual (puntos), _puntual_vector (símbolos).
- NO uses el esquema {{N}}_configuraciones salvo que la pregunta sea sobre configuración del sistema.
- Para búsquedas de nombres usa ILIKE '%término%' sobre nombre o descripcion.
- Incluye ST_AsGeoJSON(geom)::json AS geometry cuando retornes geometría.
- JOIN espacial: usa ST_Intersects(a.geom, b.geom). Tras un JOIN pueden repetirse filas.
- Consultas con VARIOS criterios espaciales (cruza X Y además cerca de Y):
  prefiera EXISTS (SELECT 1 FROM tabla WHERE condición) encadenados en WHERE,
  NO varios JOIN entre tablas grandes (provoca timeout).
  Filtre atributos (descripcion ILIKE) DENTRO del EXISTS, antes del ST_DWithin/ST_Intersects.
- Distancias en metros: ST_DWithin(a.geom::geography, b.geom::geography, metros).
  Para ST_DWithin, parta del conjunto MÁS PEQUEÑO (tabla filtrada por ILIKE)
  haciendo JOIN hacia la otra geometría; NO use EXISTS desde la tabla grande
  hacia muchas filas con ST_DWithin (provoca timeout).
- Consultas con geometría y VARIOS filtros espaciales costosos:
  use patrón en dos pasos con CTE candidatos (solo geo_id + filtros + LIMIT)
  y SELECT final con ST_AsGeoJSON solo para esos IDs (JOIN candidatos USING (geo_id)).
- Para eliminar duplicados NO uses SELECT DISTINCT con geometry ::json (PostgreSQL falla).
  Prefiere EXISTS (evita duplicados) o SELECT DISTINCT ON (tabla.geo_id) ... ORDER BY tabla.geo_id
  o ::jsonb en lugar de ::json si necesitas DISTINCT.
- Usa los nombres exactos de tablas del ESQUEMA DE BASE DE DATOS arriba.
- Responde ÚNICAMENTE con la sentencia SQL, sin explicación ni markdown.
PREGUNTA DEL USUARIO:
{question}

SQL:"""
