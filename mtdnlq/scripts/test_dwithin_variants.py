"""Prueba orden invertido: partir de malezas (339) hacia rios."""
import time

from sqlalchemy import text

from mtdnlq.db.connection import get_db_session

QUERIES = {
    "exists_rio_maleza": """
        SELECT COUNT(*) FROM "10_hidrografia".rios_y_arroyos_lineal r
        WHERE EXISTS (
            SELECT 1 FROM "10_areas_verdes_y_terrenos".malezas_areal m
            WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
              AND ST_DWithin(r.geom::geography, m.geom::geography, 100)
        )
    """,
    "join_maleza_rio": """
        SELECT COUNT(DISTINCT r.geo_id)
        FROM "10_areas_verdes_y_terrenos".malezas_areal m
        JOIN "10_hidrografia".rios_y_arroyos_lineal r
          ON ST_DWithin(r.geom::geography, m.geom::geography, 100)
        WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
    """,
    "buffer_intersects": """
        SELECT COUNT(DISTINCT r.geo_id)
        FROM "10_areas_verdes_y_terrenos".malezas_areal m
        JOIN "10_hidrografia".rios_y_arroyos_lineal r
          ON ST_Intersects(r.geom, ST_Buffer(m.geom::geography, 100)::geometry)
        WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
    """,
}


def main() -> None:
    for label, sql in QUERIES.items():
        t0 = time.perf_counter()
        try:
            with get_db_session(10000) as session:
                session.execute(text("SET LOCAL statement_timeout = '30000'"))
                n = session.execute(text(sql)).scalar()
            print(f"{label}: {n} en {time.perf_counter() - t0:.2f}s")
        except Exception as exc:
            print(f"{label}: FALLO en {time.perf_counter() - t0:.2f}s -> {exc}")


if __name__ == "__main__":
    main()
