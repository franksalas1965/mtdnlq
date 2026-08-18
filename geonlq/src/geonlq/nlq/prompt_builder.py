"""
Constructor de prompts para traducción NL → SQL.
Incluye esquema de BD y ejemplos few-shot específicos para consultas geoespaciales.
"""
from ..db.schema_inspector import schema_inspector

# Ejemplos few-shot para guiar al LLM con el dominio geoespacial
FEW_SHOT_EXAMPLES = """
EJEMPLOS DE CONSULTAS:

Pregunta: ¿Cuántos puentes hay en La Habana?
SQL: SELECT COUNT(*) AS total_puentes
     FROM puentes p
     JOIN municipios m ON p.municipio_id = m.id
     WHERE m.provincia ILIKE '%habana%';

Pregunta: Dame los puentes de la Carretera Central con carga máxima de al menos 20 toneladas
SQL: SELECT p.codigo, p.nombre, p.carga_maxima_tn, p.longitud_m, p.estado,
            ST_AsGeoJSON(p.geom)::json AS geometry
     FROM puentes p
     JOIN viales v ON p.vial_id = v.id
     WHERE v.nombre ILIKE '%carretera central%'
       AND p.carga_maxima_tn >= 20
     ORDER BY p.nombre
     LIMIT 100;

Pregunta: Dame todos los puentes
SQL: SELECT p.codigo, p.nombre, p.carga_maxima_tn, p.estado,
            ST_AsGeoJSON(p.geom)::json AS geometry
     FROM puentes p
     ORDER BY p.nombre
     LIMIT 100;

Pregunta: Dame los puentes que soporten más de 20 toneladas con el nombre de la vía
SQL: SELECT p.codigo, p.nombre, p.carga_maxima_tn, v.nombre AS nombre_via, p.estado,
            ST_AsGeoJSON(p.geom)::json AS geometry
     FROM puentes p
     JOIN viales v ON p.vial_id = v.id
     WHERE p.carga_maxima_tn > 20
     ORDER BY p.nombre
     LIMIT 100;

Pregunta: Listado de viales en mal estado en Pinar del Río
SQL: SELECT v.codigo, v.nombre, v.tipo_via, v.longitud_km, v.estado,
            ST_AsGeoJSON(v.geom)::json AS geometry
     FROM viales v
     JOIN municipios m ON ST_Intersects(v.geom, m.geom)
     WHERE m.provincia ILIKE '%pinar%'
       AND v.estado = 'malo'
     LIMIT 100;

Pregunta: ¿Qué puentes están a menos de 500 metros de la Autopista Nacional?
SQL: SELECT p.nombre, p.carga_maxima_tn, p.estado,
            ROUND(ST_Distance(p.geom::geography, v.geom::geography)::numeric, 2) AS distancia_m,
            ST_AsGeoJSON(p.geom)::json AS geometry
     FROM puentes p
     CROSS JOIN viales v
     WHERE v.nombre ILIKE '%autopista nacional%'
       AND ST_DWithin(p.geom::geography, v.geom::geography, 500)
     ORDER BY distancia_m
     LIMIT 100;

Pregunta: Dame los municipios con más puentes en mal estado
SQL: SELECT m.nombre, m.provincia, COUNT(p.id) AS puentes_malos
     FROM municipios m
     JOIN puentes p ON p.municipio_id = m.id
     WHERE p.estado = 'malo'
     GROUP BY m.id, m.nombre, m.provincia
     ORDER BY puentes_malos DESC
     LIMIT 20;
"""


def build_prompt(question: str) -> str:
    """
    Construye el prompt completo para el LLM.

    Args:
        question: Pregunta del usuario en lenguaje natural.

    Returns:
        Prompt completo con esquema, ejemplos y pregunta.
    """
    schema_description = schema_inspector.build_schema_description()

    return f"""{schema_description}

{FEW_SHOT_EXAMPLES}

INSTRUCCIONES ADICIONALES:
- Para búsquedas de nombres de vías o municipios, usa ILIKE '%término%' para ser flexible.
- Para operaciones espaciales entre tablas, usa los índices espaciales: ST_Intersects, ST_Within, ST_DWithin.
- Al calcular distancias en metros, convierte geometrías a geography: geom::geography.
- Si la pregunta menciona un tramo entre dos puntos (ej: "de Pinar del Río a La Habana"),
  filtra por los municipios extremos o usa ST_Intersects con sus polígonos.
- Incluye siempre ST_AsGeoJSON(geom)::json AS geometry cuando retornes filas con geometría.
- El peso de vehículos corresponde a la columna carga_maxima_tn en la tabla puentes.
- Si piden el nombre de la vía, incluye v.nombre (alias nombre_via) con JOIN viales v ON p.vial_id = v.id.
- Responde ÚNICAMENTE con la sentencia SQL, sin explicación ni markdown.
PREGUNTA DEL USUARIO:
{question}

SQL:"""
