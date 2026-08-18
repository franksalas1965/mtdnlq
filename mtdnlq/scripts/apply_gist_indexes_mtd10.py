"""Crea índices GIST en mtd10 si no existen."""
from sqlalchemy import text

from mtdnlq.db.connection import get_db_session

INDEXES = [
    """
    CREATE INDEX IF NOT EXISTS idx_rios_y_arroyos_lineal_geom
      ON "10_hidrografia".rios_y_arroyos_lineal USING GIST (geom)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_vias_de_comunicacion_lineal_geom
      ON "10_red_vial".vias_de_comunicacion_lineal USING GIST (geom)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_malezas_areal_geom
      ON "10_areas_verdes_y_terrenos".malezas_areal USING GIST (geom)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rios_y_arroyos_lineal_geog
      ON "10_hidrografia".rios_y_arroyos_lineal USING GIST ((geom::geography))
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_malezas_areal_geog
      ON "10_areas_verdes_y_terrenos".malezas_areal USING GIST ((geom::geography))
    """,
]

ANALYZE = [
    'ANALYZE "10_hidrografia".rios_y_arroyos_lineal',
    'ANALYZE "10_red_vial".vias_de_comunicacion_lineal',
    'ANALYZE "10_areas_verdes_y_terrenos".malezas_areal',
]


def main() -> None:
    with get_db_session(10000) as session:
        for stmt in INDEXES:
            session.execute(text(stmt))
            print("Creado/verificado indice")
        for stmt in ANALYZE:
            session.execute(text(stmt))
        rows = session.execute(
            text(
                """
                SELECT schemaname, tablename, indexname
                FROM pg_indexes
                WHERE indexdef ILIKE '%USING gist%'
                  AND schemaname IN (
                    '10_hidrografia', '10_red_vial', '10_areas_verdes_y_terrenos'
                  )
                ORDER BY 1, 2
                """
            )
        ).fetchall()
        print("Indices GIST activos:")
        for row in rows:
            print(f"  {row.schemaname}.{row.tablename} -> {row.indexname}")


if __name__ == "__main__":
    main()
