"""Tests unitarios para el validador SQL."""
import pytest
from mtdnlq.nlq.sql_validator import validate_sql, normalize_sql
from mtdnlq.core.exceptions import SQLForbiddenError, SQLGenerationError


def test_valid_select_passes():
    sql = "SELECT * FROM puentes WHERE carga_maxima_tn >= 10"
    result = validate_sql(sql)
    assert "SELECT" in result.upper()


def test_select_with_postgis_passes():
    sql = """SELECT p.nombre, ST_AsGeoJSON(p.geom)::json AS geometry
             FROM puentes p
             JOIN viales v ON p.vial_id = v.id
             WHERE v.nombre ILIKE '%carretera central%'"""
    result = validate_sql(sql)
    assert result  # No lanza excepción


def test_insert_blocked():
    with pytest.raises(SQLForbiddenError):
        validate_sql("INSERT INTO puentes (nombre) VALUES ('test')")


def test_drop_blocked():
    with pytest.raises(SQLForbiddenError):
        validate_sql("DROP TABLE puentes")


def test_delete_blocked():
    with pytest.raises(SQLForbiddenError):
        validate_sql("DELETE FROM puentes WHERE id = 1")


def test_update_blocked():
    with pytest.raises(SQLForbiddenError):
        validate_sql("UPDATE puentes SET estado = 'malo' WHERE id = 1")


def test_empty_sql_raises():
    with pytest.raises(SQLGenerationError):
        validate_sql("")


def test_non_select_raises():
    with pytest.raises(SQLGenerationError):
        validate_sql("EXPLAIN SELECT * FROM puentes")


def test_limit_added_when_missing():
    sql = "SELECT * FROM puentes"
    result = validate_sql(sql, max_results=50)
    assert "LIMIT 50" in result


def test_limit_not_duplicated_when_present():
    sql = "SELECT * FROM puentes LIMIT 10"
    result = validate_sql(sql, max_results=50)
    assert result.count("LIMIT") == 1


def test_no_limit_when_max_results_zero():
    sql = "SELECT * FROM puentes"
    result = validate_sql(sql, max_results=0)
    assert "LIMIT" not in result.upper()


def test_cte_with_select_passes():
    sql = """WITH ranked AS (
        SELECT p.*, ROW_NUMBER() OVER (ORDER BY p.pk_vial) as rn
        FROM puentes p
    )
    SELECT * FROM ranked WHERE rn <= 10"""
    result = validate_sql(sql)
    assert result


def test_markdown_free_sql():
    """El validador no debe romper con SQL limpio (sin bloques markdown)."""
    sql = "SELECT nombre FROM municipios WHERE provincia ILIKE '%habana%'"
    result = validate_sql(sql)
    assert "```" not in result


def test_distinct_json_geometry_normalized_to_jsonb():
    sql = (
        'SELECT DISTINCT r.geo_id, ST_AsGeoJSON(r.geom)::json AS geometry '
        'FROM "10_hidrografia".rios_y_arroyos_lineal r '
        'JOIN "10_red_vial".vias_de_comunicacion_lineal v '
        "ON ST_Intersects(r.geom, v.geom)"
    )
    result = validate_sql(sql)
    assert "::jsonb" in result.lower()
    assert "::json AS" not in result.lower()


def test_ilike_double_percent_normalized():
    sql = (
        "SELECT * FROM malezas_areal m "
        "WHERE m.descripcion ILIKE '%%maleza compacta con espinas%%'"
    )
    result = normalize_sql(sql)
    assert "ILIKE '%maleza compacta con espinas%'" in result
    assert "%%" not in result
