# -*- coding: utf-8 -*-
"""Exportación de resultados tabulares a Excel (XML) o CSV sin dependencias externas."""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

EXCEL_XML_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles>
  <Style ss:ID="Header">
   <Font ss:Bold="1"/>
  </Style>
 </Styles>
"""


def default_export_basename(question: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(question)[:40] if question else "resultados"
    return f"mtdnlq_{slug}_{stamp}"


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "_", text, flags=re.UNICODE)
    return text.strip("_") or "resultados"


def _cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def response_to_table(data: dict) -> tuple[list[str], list[list[str]]]:
    """
    Convierte la respuesta API a cabeceras y filas (sin columna geometry cruda).
    """
    display_mode = data.get("display_mode", "table")
    columns = [c for c in (data.get("columns") or []) if c != "geometry"]

    if display_mode == "summary":
        rows_raw = _extract_rows(data)
        if not rows_raw:
            return [], []
        row = rows_raw[0]
        keys = columns or list(row.keys())
        headers = ["campo", "valor"]
        table_rows = [[str(k), _cell_value(row.get(k))] for k in keys if k != "geometry"]
        return headers, table_rows

    rows_raw = _extract_rows(data)
    if not rows_raw:
        return [], []

    headers = columns or [k for k in rows_raw[0].keys() if k != "geometry"]
    table_rows = []
    for row in rows_raw:
        table_rows.append([_cell_value(row.get(h)) for h in headers])
    return headers, table_rows


def _extract_rows(data: dict) -> list[dict]:
    results = data.get("results")
    if isinstance(results, list):
        return [r for r in results if isinstance(r, dict)]
    if isinstance(results, dict) and results.get("type") == "FeatureCollection":
        rows = []
        for feat in results.get("features") or []:
            if isinstance(feat, dict):
                rows.append(dict(feat.get("properties") or {}))
        return rows
    return []


def metadata_rows(data: dict) -> list[list[str]]:
    """Filas de metadatos para hoja opcional de contexto."""
    rows = [
        ["pregunta", _cell_value(data.get("question"))],
        ["sql", _cell_value(data.get("sql"))],
        ["escala", _cell_value(data.get("scale"))],
        ["base_datos", _cell_value(data.get("database"))],
        ["total_registros", _cell_value(data.get("total"))],
        ["tiempo_ms", _cell_value(data.get("time_ms"))],
        ["exportado", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    ]
    return rows


def write_excel_xml(
    path: str,
    headers: list[str],
    rows: list[list[str]],
    metadata: list[list[str]] | None = None,
    sheet_name: str = "Datos",
) -> None:
    """Genera .xls compatible con Excel (SpreadsheetML, solo biblioteca estándar)."""
    parts = [EXCEL_XML_HEADER]

    if metadata:
        parts.append(_worksheet_xml("Consulta", ["campo", "valor"], metadata))

    parts.append(_worksheet_xml(sheet_name, headers, rows))
    parts.append("</Workbook>")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(parts))


def _worksheet_xml(name: str, headers: list[str], rows: list[list[str]]) -> str:
    safe_name = escape(name[:31])
    out = [f' <Worksheet ss:Name="{safe_name}"><Table>']

    if headers:
        out.append("  <Row>")
        for header in headers:
            out.append(f'   <Cell ss:StyleID="Header"><Data ss:Type="String">{escape(str(header))}</Data></Cell>')
        out.append("  </Row>")

    for row in rows:
        out.append("  <Row>")
        for value in row:
            text = escape(value)
            data_type = "Number" if _looks_numeric(value) else "String"
            out.append(f'   <Cell><Data ss:Type="{data_type}">{text}</Data></Cell>')
        out.append("  </Row>")

    out.append(" </Table></Worksheet>")
    return "\n".join(out)


def _looks_numeric(value: str) -> bool:
    if not value or value.startswith("0") and value != "0":
        return False
    try:
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False


def write_csv(path: str, headers: list[str], rows: list[list[str]], delimiter: str = ";") -> None:
    """CSV con BOM UTF-8 para abrir bien en Excel en Windows."""
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        if headers:
            writer.writerow(headers)
        writer.writerows(rows)


def export_response(data: dict, path: str) -> str:
    """
    Exporta respuesta a path (.xls SpreadsheetML o .csv).
    Devuelve formato usado: 'xls' o 'csv'.
    """
    headers, rows = response_to_table(data)
    if not headers and not rows:
        raise ValueError("No hay datos tabulares para exportar.")

    meta = metadata_rows(data)
    lower = path.lower()
    if lower.endswith(".csv"):
        write_csv(path, headers, rows)
        return "csv"

    if not lower.endswith(".xls"):
        path = f"{path}.xls"
    write_excel_xml(path, headers, rows, metadata=meta)
    return "xls"
