# -*- coding: utf-8 -*-
"""Extrae esquema y tabla origen del SQL generado por MTD-NLQ."""
from __future__ import annotations

import re

_FROM_JOIN = re.compile(
    r'(?:FROM|JOIN)\s+"([^"]+)"\s*\.\s*"?([a-zA-Z0-9_]+)"?\s*(?:AS\s+)?(\w+)?',
    re.IGNORECASE,
)
_GEOM_ALIAS = re.compile(
    r"ST_AsGeoJSON\s*\(\s*(?:(\w+)\.)?geom\s*\)",
    re.IGNORECASE,
)


def _strip_sql_comments(sql: str) -> str:
    text = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)


def extract_geometry_source_table(sql: str) -> tuple[str, str] | None:
    """
    Devuelve (schema, table) de la capa que aporta la geometría al resultado.

    Prioriza el alias usado en ST_AsGeoJSON(alias.geom); si no hay alias,
    usa la primera tabla del FROM.
    """
    if not sql or not sql.strip():
        return None

    cleaned = _strip_sql_comments(sql)
    geom_match = _GEOM_ALIAS.search(cleaned)
    geom_alias = geom_match.group(1) if geom_match else None

    tables: list[tuple[str, str, str | None]] = []
    for match in _FROM_JOIN.finditer(cleaned):
        schema, table, alias = match.group(1), match.group(2), match.group(3)
        tables.append((schema, table, alias))

    if not tables:
        return None

    if geom_alias:
        for schema, table, alias in tables:
            if alias and alias.lower() == geom_alias.lower():
                return schema, table

    return tables[0][0], tables[0][1]
