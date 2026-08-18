"""Prueba consulta completa con patron optimizado (malezas -> rios)."""
import time

from sqlalchemy import text

from mtdnlq.db.connection import get_db_session

SQL = """
WITH candidatos AS (
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
JOIN candidatos c USING (geo_id)
"""


def main() -> None:
    t0 = time.perf_counter()
    with get_db_session(10000) as session:
        session.execute(text("SET LOCAL statement_timeout = '120000'"))
        rows = session.execute(text(SQL)).fetchall()
    print(f"Filas: {len(rows)} en {time.perf_counter() - t0:.2f}s")


if __name__ == "__main__":
    main()
