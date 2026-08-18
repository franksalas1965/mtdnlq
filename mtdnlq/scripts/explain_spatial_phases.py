"""Diagnóstico por fases: qué subconsulta espacial tarda más."""
import time

from sqlalchemy import text

from mtdnlq.db.connection import get_db_session

TIMEOUT_MS = 60_000


def timed(label: str, sql: str) -> None:
    print(f"\n--- {label} ---")
    t0 = time.perf_counter()
    try:
        with get_db_session(10000) as session:
            session.execute(text(f"SET LOCAL statement_timeout = '{TIMEOUT_MS}'"))
            row = session.execute(text(sql)).one()
            elapsed = time.perf_counter() - t0
            print(f"OK en {elapsed:.2f}s -> {dict(row._mapping)}")
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"FALLO en {elapsed:.2f}s -> {type(exc).__name__}: {exc}")


def main() -> None:
    timed(
        "Solo malezas filtradas",
        """
        SELECT COUNT(*) AS n
        FROM "10_areas_verdes_y_terrenos".malezas_areal m
        WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
        """,
    )
    timed(
        "Ríos que cruzan vía (EXISTS ST_Intersects)",
        """
        SELECT COUNT(*) AS n
        FROM "10_hidrografia".rios_y_arroyos_lineal r
        WHERE EXISTS (
            SELECT 1 FROM "10_red_vial".vias_de_comunicacion_lineal v
            WHERE ST_Intersects(r.geom, v.geom)
        )
        """,
    )
    timed(
        "Ríos cerca de maleza 100m (EXISTS ST_DWithin)",
        """
        SELECT COUNT(*) AS n
        FROM "10_hidrografia".rios_y_arroyos_lineal r
        WHERE EXISTS (
            SELECT 1 FROM "10_areas_verdes_y_terrenos".malezas_areal m
            WHERE m.descripcion ILIKE '%maleza compacta con espinas%'
              AND ST_DWithin(r.geom::geography, m.geom::geography, 100)
        )
        """,
    )
    timed(
        "Un solo río × todas las vías (nested loop peor caso)",
        """
        SELECT COUNT(*) AS n
        FROM "10_red_vial".vias_de_comunicacion_lineal v
        WHERE ST_Intersects(
            (SELECT geom FROM "10_hidrografia".rios_y_arroyos_lineal LIMIT 1),
            v.geom
        )
        """,
    )


if __name__ == "__main__":
    main()
