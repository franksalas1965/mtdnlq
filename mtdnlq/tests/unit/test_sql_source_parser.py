"""Tests para extracción de capa origen del SQL."""
from mtdnlq.nlq.sql_source_parser import extract_geometry_source_table


def test_single_table_with_alias():
    sql = """
    SELECT r.geo_id, r.nombre, ST_AsGeoJSON(r.geom)::json AS geometry
    FROM "10_hidrografia".rios_y_arroyos_lineal r
    WHERE r.nombre ILIKE '%carrasco%'
    LIMIT 100
    """
    assert extract_geometry_source_table(sql) == (
        "10_hidrografia",
        "rios_y_arroyos_lineal",
    )


def test_single_table_without_alias():
    sql = """
    SELECT geo_id, ST_AsGeoJSON(geom)::json AS geometry
    FROM "10_limites_estatales".limites_estatales_lineal
    LIMIT 50
    """
    assert extract_geometry_source_table(sql) == (
        "10_limites_estatales",
        "limites_estatales_lineal",
    )


def test_join_prefers_geom_alias():
    sql = """
    SELECT r.geo_id, ST_AsGeoJSON(r.geom)::json AS geometry
    FROM "10_hidrografia".rios_y_arroyos_lineal r
    JOIN "10_red_vial".vias_de_comunicacion_lineal v ON ST_Intersects(r.geom, v.geom)
    LIMIT 10
    """
    assert extract_geometry_source_table(sql) == (
        "10_hidrografia",
        "rios_y_arroyos_lineal",
    )
