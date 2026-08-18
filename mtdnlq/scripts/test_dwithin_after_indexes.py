"""Prueba rápida de ST_DWithin tras índices geography."""
import time

from sqlalchemy import text

from mtdnlq.db.connection import get_db_session

SQL = """
SELECT COUNT(*) AS n
FROM "10_hidrografia".rios_y_arroyos_lineal r
WHERE EXISTS (
    SELECT 1 FROM "10_areas_verdes_y_terrenos".malezas_areal m
    WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
      AND ST_DWithin(r.geom::geography, m.geom::geography, 100)
)
"""


def main() -> None:
    t0 = time.perf_counter()
    with get_db_session(10000) as session:
        session.execute(text("SET LOCAL statement_timeout = '60000'"))
        n = session.execute(text(SQL)).scalar()
    print(f"Rios cerca maleza 100m: {n} en {time.perf_counter() - t0:.2f}s")


if __name__ == "__main__":
    main()
