"""Diagnóstico: EXPLAIN ANALYZE de consulta ríos × vías × malezas."""
from sqlalchemy import text

from mtdnlq.db.connection import get_db_session

SQL_EXISTS = """
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT r.geo_id, r.nombre
FROM "10_hidrografia".rios_y_arroyos_lineal r
WHERE EXISTS (
    SELECT 1 FROM "10_red_vial".vias_de_comunicacion_lineal v
    WHERE ST_Intersects(r.geom, v.geom)
)
AND EXISTS (
    SELECT 1 FROM "10_areas_verdes_y_terrenos".malezas_areal m
    WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
      AND ST_DWithin(r.geom::geography, m.geom::geography, 100)
)
LIMIT 100;
"""

SQL_JOIN = """
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT DISTINCT ON (r.geo_id) r.geo_id, r.nombre
FROM "10_hidrografia".rios_y_arroyos_lineal r
JOIN "10_red_vial".vias_de_comunicacion_lineal v ON ST_Intersects(r.geom, v.geom)
JOIN "10_areas_verdes_y_terrenos".malezas_areal m
  ON ST_DWithin(r.geom::geography, m.geom::geography, 100)
WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
ORDER BY r.geo_id
LIMIT 100;
"""

INDEX_SQL = """
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname IN (
    '10_hidrografia', '10_red_vial', '10_areas_verdes_y_terrenos'
)
AND tablename IN (
    'rios_y_arroyos_lineal', 'vias_de_comunicacion_lineal', 'malezas_areal'
)
ORDER BY 1, 2, 3;
"""

COUNT_SQL = """
SELECT
  (SELECT COUNT(*) FROM "10_hidrografia".rios_y_arroyos_lineal) AS rios,
  (SELECT COUNT(*) FROM "10_red_vial".vias_de_comunicacion_lineal) AS vias,
  (SELECT COUNT(*) FROM "10_areas_verdes_y_terrenos".malezas_areal) AS malezas,
  (SELECT COUNT(*) FROM "10_areas_verdes_y_terrenos".malezas_areal
   WHERE descripcion ILIKE '%maleza compacta con espinas%') AS malezas_filtradas;
"""


def run_explain(label: str, sql: str, timeout_ms: int = 120_000) -> None:
    print(f"\n=== {label} (timeout {timeout_ms // 1000}s) ===")
    try:
        with get_db_session(10000) as session:
            session.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}'"))
            for row in session.execute(text(sql)):
                print(row[0])
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")


def main() -> None:
    with get_db_session(10000) as session:
        counts = session.execute(text(COUNT_SQL)).one()
        print("Conteos:", dict(counts._mapping))

        print("\n=== Índices espaciales ===")
        for row in session.execute(text(INDEX_SQL)):
            print(dict(row._mapping))

    run_explain("EXISTS (recomendado)", SQL_EXISTS)
    run_explain("JOIN (patrón antiguo)", SQL_JOIN)


if __name__ == "__main__":
    main()
