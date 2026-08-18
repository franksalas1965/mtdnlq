# -*- coding: utf-8 -*-
"""Normalización de atributos MTD para QGIS y PostGIS."""
from typing import Any

# Campos que en mtd10 son character varying y deben compararse como texto
MTD_TEXT_FIELDS = frozenset(
    {
        "geo_id",
        "geocodigo",
        "nomenclatura",
        "nombre",
        "descripcion",
        "categoria_poblacional",
        "escala",
    }
)


def stringify_mtd_value(key: str, value: Any) -> Any:
    """Convierte a str códigos MTD que QGIS/PostGIS deben tratar como texto."""
    if value is None:
        return value
    key_lower = key.lower()
    if key_lower in MTD_TEXT_FIELDS or key_lower.endswith("codigo"):
        return str(value)
    return value


def stringify_mtd_properties(props: dict) -> dict:
    """Devuelve copia de propiedades con códigos MTD como cadena."""
    if not props:
        return {}
    return {k: stringify_mtd_value(k, v) for k, v in props.items()}


def normalize_geojson_results(results: Any) -> Any:
    """Normaliza FeatureCollection o filas tabulares antes de guardar o mostrar."""
    if isinstance(results, dict) and results.get("type") == "FeatureCollection":
        features = []
        for feat in results.get("features") or []:
            if not isinstance(feat, dict):
                features.append(feat)
                continue
            feat = dict(feat)
            props = feat.get("properties")
            if isinstance(props, dict):
                feat["properties"] = stringify_mtd_properties(props)
            features.append(feat)
        out = dict(results)
        out["features"] = features
        return out
    if isinstance(results, list):
        rows = []
        for row in results:
            if isinstance(row, dict):
                rows.append(stringify_mtd_properties(row))
            else:
                rows.append(row)
        return rows
    return results
