# -*- coding: utf-8 -*-
"""Panel de resultados: tabla, resumen, explicación y localización en mapa."""
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qgis.core import QgsApplication

from .export_utils import default_export_basename, export_response
from .ui_icons import theme_icon


class ResultPanel(QWidget):
    """Muestra la respuesta según display_mode sin cargar todo el GeoJSON en el mapa."""

    def __init__(self, map_locator, parent=None):
        super().__init__(parent)
        self.map_locator = map_locator
        self._features_by_row: dict[int, dict] = {}
        self._current_data: dict | None = None
        self._query_scale: int = 10000
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet(
            "background: #f0f4f8; padding: 6px; border-radius: 4px; font-size: 11px;"
        )
        layout.addWidget(self.meta_label)
        self.meta_label.hide()

        self.tabs = QTabWidget()

        # --- Pestaña Datos ---
        data_widget = QWidget()
        data_layout = QVBoxLayout(data_widget)
        data_layout.setContentsMargins(4, 8, 4, 4)

        self.stack = QStackedWidget()

        self.empty_widget = QLabel(
            "Sin resultados todavía.\n\n"
            "Escriba una pregunta en la pestaña «Consulta» y pulse «Consultar».\n\n"
            "Los registros con geometría incluyen un botón para localizarlos en el mapa."
        )
        self.empty_widget.setAlignment(Qt.AlignCenter)
        self.empty_widget.setWordWrap(True)
        self.stack.addWidget(self.empty_widget)

        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table_header = self.table_widget.horizontalHeader()
        table_header.setStretchLastSection(False)
        table_header.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.stack.addWidget(self.table_widget)

        self.summary_widget = QTableWidget()
        self.summary_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.summary_widget.setColumnCount(2)
        self.summary_widget.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.summary_widget.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.summary_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        summary_header = self.summary_widget.horizontalHeader()
        summary_header.setStretchLastSection(False)
        summary_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        summary_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.summary_widget.setAlternatingRowColors(True)
        self.stack.addWidget(self.summary_widget)

        data_layout.addWidget(self.stack, 1)

        actions_row = QHBoxLayout()
        self.export_btn = QPushButton("Exportar Excel…")
        self.export_btn.setIcon(theme_icon("mActionFileSave.svg", "mActionSaveAllEdits.svg"))
        self.export_btn.setToolTip(
            "Guardar los datos visibles en Excel (.xls) o CSV para análisis externo."
        )
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)
        actions_row.addWidget(self.export_btn)
        actions_row.addStretch()
        data_layout.addLayout(actions_row)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #555; font-size: 11px;")
        data_layout.addWidget(self.hint_label)

        self._tab_data = self.tabs.addTab(data_widget, "Datos")

        # --- Pestaña SQL ---
        sql_widget = QWidget()
        sql_layout = QVBoxLayout(sql_widget)
        sql_layout.setContentsMargins(4, 8, 4, 4)
        self.sql_text = QTextEdit()
        self.sql_text.setReadOnly(True)
        self.sql_text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        sql_layout.addWidget(self.sql_text)
        self._tab_sql = self.tabs.addTab(sql_widget, "SQL")

        # --- Pestaña Explicación ---
        exp_widget = QWidget()
        exp_layout = QVBoxLayout(exp_widget)
        exp_layout.setContentsMargins(4, 8, 4, 4)
        self.explanation_text = QTextEdit()
        self.explanation_text.setReadOnly(True)
        exp_layout.addWidget(self.explanation_text)
        self._tab_explanation = self.tabs.addTab(exp_widget, "Explicación")

        self.tabs.setTabVisible(self._tab_sql, False)
        self.tabs.setTabVisible(self._tab_explanation, False)

        layout.addWidget(self.tabs, 1)

    def clear(self):
        self._current_data = None
        self.export_btn.setEnabled(False)
        self._features_by_row.clear()
        self.meta_label.clear()
        self.meta_label.hide()
        self.hint_label.clear()
        self.sql_text.clear()
        self.explanation_text.clear()
        self.tabs.setTabVisible(self._tab_sql, False)
        self.tabs.setTabVisible(self._tab_explanation, False)
        self.tabs.setCurrentIndex(self._tab_data)
        self.table_widget.clear()
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(0)
        self.summary_widget.setRowCount(0)
        self.stack.setCurrentWidget(self.empty_widget)

    def show_response(
        self,
        data: dict,
        show_sql: bool = True,
        show_meta: bool = True,
        scale_label: str = "",
    ):
        self.clear()
        self._current_data = data
        self._query_scale = int(data.get("scale") or 10000)

        display_mode = data.get("display_mode", "table")
        total = data.get("total", 0)
        time_ms = data.get("time_ms", 0)
        has_geometry = data.get("has_geometry", False)
        columns = data.get("columns") or []

        if show_meta:
            mode_labels = {
                "map": "Mapa (tabla + localizar)",
                "table": "Tabla",
                "summary": "Resumen",
            }
            scale_part = f"Escala: {scale_label} · " if scale_label else ""
            timing = data.get("timing_ms") or {}
            timing_part = ""
            if timing.get("executing_sql") is not None:
                timing_part = f" · BD: {timing['executing_sql']:.0f} ms"
            self.meta_label.setText(
                f"{scale_part}"
                f"Modo: {mode_labels.get(display_mode, display_mode)} · "
                f"Registros: {total} · Tiempo: {time_ms:.0f} ms{timing_part}"
            )
            self.meta_label.show()

        explanation = data.get("explanation")
        if explanation:
            self.explanation_text.setPlainText(str(explanation))
            self.tabs.setTabVisible(self._tab_explanation, True)

        sql = data.get("sql")
        if show_sql and sql:
            self.sql_text.setPlainText(str(sql))
            self.tabs.setTabVisible(self._tab_sql, True)

        if display_mode == "summary":
            self._show_summary(data, columns)
        elif display_mode == "map" and has_geometry:
            self._show_geo_table(data, columns)
        else:
            self._show_plain_table(data, columns)

        self.export_btn.setEnabled(bool(self._extract_rows(data)))
        self.tabs.setCurrentIndex(self._tab_data)

    def _on_export(self):
        if not self._current_data:
            QMessageBox.information(
                self,
                "MTD-NLQ",
                "No hay resultados para exportar.",
            )
            return

        default_name = default_export_basename(self._current_data.get("question") or "")
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar resultados",
            f"{default_name}.xls",
            "Excel (*.xls);;CSV (*.csv)",
        )
        if not path:
            return

        if selected_filter.startswith("CSV") and not path.lower().endswith(".csv"):
            path = f"{path}.csv"
        elif selected_filter.startswith("Excel") and not path.lower().endswith((".xls", ".xlsx")):
            path = f"{path}.xls"

        try:
            fmt = export_response(self._current_data, path)
        except ValueError as exc:
            QMessageBox.warning(self, "MTD-NLQ", str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self, "MTD-NLQ", f"No se pudo guardar el archivo:\n{exc}")
            return

        label = "Excel" if fmt == "xls" else "CSV"
        self.hint_label.setText(f"Exportado como {label}: {path}")
        QMessageBox.information(
            self,
            "MTD-NLQ",
            f"Resultados exportados correctamente ({label}).\n\n{path}",
        )

    def _show_summary(self, data: dict, columns: list):
        results = data.get("results")
        rows = []
        if isinstance(results, list) and results:
            rows = results
        elif isinstance(results, dict) and results.get("type") == "FeatureCollection":
            for feat in results.get("features", []):
                props = dict(feat.get("properties") or {})
                rows.append(props)

        if not rows:
            self.hint_label.setText("Sin datos en el resumen.")
            self.stack.setCurrentWidget(self.empty_widget)
            return

        row_data = rows[0]
        keys = columns or list(row_data.keys())
        self.summary_widget.setRowCount(len(keys))
        for i, key in enumerate(keys):
            self.summary_widget.setItem(i, 0, QTableWidgetItem(str(key)))
            value = row_data.get(key, "")
            if isinstance(value, (dict, list)):
                import json
                value = json.dumps(value, ensure_ascii=False)
            self.summary_widget.setItem(i, 1, QTableWidgetItem(str(value)))

        self.hint_label.setText("Resumen agregado o consulta de conteo.")
        self.stack.setCurrentWidget(self.summary_widget)

    def _show_plain_table(self, data: dict, columns: list):
        rows = self._extract_rows(data)
        if not rows:
            self.hint_label.setText("La consulta no devolvió filas.")
            self.stack.setCurrentWidget(self.empty_widget)
            return

        keys = columns or list(rows[0].keys())
        self.table_widget.setColumnCount(len(keys))
        self.table_widget.setHorizontalHeaderLabels([str(k) for k in keys])
        self.table_widget.setRowCount(len(rows))

        for r, row in enumerate(rows):
            for c, key in enumerate(keys):
                val = row.get(key, "")
                if isinstance(val, (dict, list)):
                    import json
                    val = json.dumps(val, ensure_ascii=False)
                self.table_widget.setItem(r, c, QTableWidgetItem(str(val) if val is not None else ""))

        self.table_widget.resizeColumnsToContents()
        self.hint_label.setText(
            "Listado tabular (sin geometría en el mapa). "
            "Para localizar registros use formato GeoJSON en la pestaña Consulta."
        )
        self.stack.setCurrentWidget(self.table_widget)

    def _show_geo_table(self, data: dict, columns: list):
        features = self._extract_features(data)
        if not features:
            self._show_plain_table(data, columns)
            return

        props_keys = columns[:]
        if not props_keys and features:
            props_keys = list((features[0].get("properties") or {}).keys())

        self.table_widget.setColumnCount(len(props_keys) + 1)
        headers = ["Mapa"] + [str(k) for k in props_keys]
        self.table_widget.setHorizontalHeaderLabels(headers)
        self.table_widget.setRowCount(len(features))

        locate_icon = QgsApplication.getThemeIcon("mActionZoomToSelected.svg")

        for r, feat in enumerate(features):
            self._features_by_row[r] = feat

            btn = QToolButton()
            btn.setIcon(locate_icon)
            btn.setToolTip("Localizar este registro en el mapa")
            btn.setAutoRaise(True)
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(lambda checked=False, row=r: self._on_locate(row))

            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(2, 0, 2, 0)
            cell_layout.addWidget(btn)
            cell_layout.addStretch()
            self.table_widget.setCellWidget(r, 0, cell_widget)

            props = feat.get("properties") or {}
            for c, key in enumerate(props_keys, start=1):
                val = props.get(key, "")
                self.table_widget.setItem(r, c, QTableWidgetItem(str(val) if val is not None else ""))

        self.table_widget.setColumnWidth(0, 48)
        self.table_widget.resizeColumnsToContents()
        self.hint_label.setText(
            f"{len(features)} registro(s) con geometría. "
            "Use el icono de localizar (requiere al menos una capa base en el proyecto: "
            "OSM, WMS, SHP, GPKG, etc.)."
        )
        self.stack.setCurrentWidget(self.table_widget)

    def _on_locate(self, row: int):
        feat = self._features_by_row.get(row)
        if not feat:
            return
        props = feat.get("properties") or {}
        label = props.get("nombre") or props.get("nomenclatura") or props.get("geo_id") or f"Fila {row + 1}"
        ok = self.map_locator.locate_feature(
            feat,
            label=str(label),
            scale=self._query_scale,
            source_schema=self._current_data.get("source_schema") if self._current_data else None,
            source_table=self._current_data.get("source_table") if self._current_data else None,
            sql=self._current_data.get("sql") if self._current_data else None,
            style_qml=self._current_data.get("style_qml") if self._current_data else None,
        )
        if not ok:
            if self.map_locator.has_base_layers():
                self.hint_label.setText("No se pudo localizar la geometría de este registro.")
            else:
                self.hint_label.setText(
                    "Cargue al menos una capa base en el proyecto antes de localizar."
                )
        else:
            self.hint_label.setText(f"Localizado en mapa: {label}")

    @staticmethod
    def _extract_features(data: dict) -> list:
        results = data.get("results")
        if isinstance(results, dict) and results.get("type") == "FeatureCollection":
            return [
                f for f in results.get("features", [])
                if f.get("geometry") is not None
            ]
        return []

    @staticmethod
    def _extract_rows(data: dict) -> list:
        results = data.get("results")
        if isinstance(results, list):
            return results
        if isinstance(results, dict) and results.get("type") == "FeatureCollection":
            rows = []
            for feat in results.get("features", []):
                row = dict(feat.get("properties") or {})
                rows.append(row)
            return rows
        return []
