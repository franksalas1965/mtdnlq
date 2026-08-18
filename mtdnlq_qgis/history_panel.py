# -*- coding: utf-8 -*-
"""Pestaña de historial local de consultas exitosas (Query Capsules)."""
import os
import subprocess
import sys

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .query_history_store import QueryHistoryStore
from .ui_icons import theme_icon


class HistoryPanel(QWidget):
    """Lista, busca y reutiliza consultas guardadas localmente."""

    restore_results = pyqtSignal(dict)
    restore_question = pyqtSignal(str, int)
    load_on_map = pyqtSignal(str, str, int, str, str, str, str)

    def __init__(self, history_store: QueryHistoryStore, parent=None):
        super().__init__(parent)
        self.store = history_store
        self._entries: list[dict] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)

        intro = QLabel(
            "Consultas completadas con éxito. Cada entrada es una «cápsula» "
            "reutilizable (SQL + resultados en disco). "
            "Buscar solo filtra el historial local (SQLite), no consulta PostGIS."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(intro)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar en pregunta o SQL…")
        self.search_edit.returnPressed.connect(self.refresh)
        search_row.addWidget(self.search_edit, 1)

        self.search_btn = QPushButton("Buscar")
        self.search_btn.clicked.connect(self.refresh)
        search_row.addWidget(self.search_btn)
        layout.addLayout(search_row)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Fecha", "Pregunta", "Reg.", "Tiempo", "Escala"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._on_restore_results)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()

        self.restore_btn = QPushButton("Ver resultados")
        self.restore_btn.setIcon(
            theme_icon("mActionTableOpen.svg", "mActionOpenTable.svg")
        )
        self.restore_btn.setToolTip(
            "Cargar resultados guardados en la pestaña Resultados (sin volver a consultar)."
        )
        self.restore_btn.clicked.connect(self._on_restore_results)
        btn_row.addWidget(self.restore_btn)

        self.question_btn = QPushButton("Usar pregunta")
        self.question_btn.setIcon(
            theme_icon("mActionEditCopy.svg", "mActionCopy.svg")
        )
        self.question_btn.setToolTip("Copiar la pregunta a la pestaña Consulta.")
        self.question_btn.clicked.connect(self._on_restore_question)
        btn_row.addWidget(self.question_btn)

        self.map_btn = QPushButton("Capa en mapa")
        self.map_btn.setIcon(
            theme_icon("mActionAddLayer.svg", "mActionAddOgrLayer.svg")
        )
        self.map_btn.setToolTip(
            "Añadir results.geojson de la cápsula como capa OGR (reutilización directa)."
        )
        self.map_btn.clicked.connect(self._on_load_map)
        btn_row.addWidget(self.map_btn)

        self.folder_btn = QPushButton("Carpeta")
        self.folder_btn.setIcon(
            theme_icon("mActionFileOpen.svg", "mActionOpen.svg")
        )
        self.folder_btn.setToolTip("Abrir la carpeta de la cápsula en el explorador.")
        self.folder_btn.clicked.connect(self._on_open_folder)
        btn_row.addWidget(self.folder_btn)

        self.delete_btn = QPushButton("Eliminar")
        self.delete_btn.setIcon(
            theme_icon("mActionDeleteSelected.svg", "mActionRemove.svg")
        )
        self.delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self.delete_btn)

        layout.addLayout(btn_row)

        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #666; font-size: 10px;")
        self.path_label.setText(f"Almacén: {self.store.root_path}")
        layout.addWidget(self.path_label)

    def refresh(self):
        search = self.search_edit.text().strip()
        self._entries = self.store.list_entries(search=search, limit=200)
        self.table.setRowCount(len(self._entries))

        for row, entry in enumerate(self._entries):
            self.table.setItem(row, 0, QTableWidgetItem(entry.get("created_label", "")))
            question_item = QTableWidgetItem(entry.get("question", ""))
            question_item.setToolTip(entry.get("question", ""))
            self.table.setItem(row, 1, question_item)
            self.table.setItem(row, 2, QTableWidgetItem(str(entry.get("total", 0))))
            time_ms = entry.get("time_ms") or 0
            self.table.setItem(row, 3, QTableWidgetItem(f"{time_ms:.0f} ms"))
            scale = entry.get("scale")
            db = entry.get("database") or ""
            scale_txt = f"1:{scale // 1000}k" if scale else ""
            if db:
                scale_txt = f"{scale_txt} ({db})" if scale_txt else db
            self.table.setItem(row, 4, QTableWidgetItem(scale_txt))

        if self._entries:
            self.table.selectRow(0)

    def _selected_entry(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def _on_restore_results(self):
        entry = self._selected_entry()
        if not entry:
            QMessageBox.information(self, "MTD-NLQ", "Seleccione una consulta del historial.")
            return
        data = self.store.load_response(entry["id"])
        if not data:
            QMessageBox.warning(self, "MTD-NLQ", "No se pudo leer la cápsula guardada.")
            self.refresh()
            return
        self.restore_results.emit(data)

    def _on_restore_question(self):
        entry = self._selected_entry()
        if not entry:
            QMessageBox.information(self, "MTD-NLQ", "Seleccione una consulta del historial.")
            return
        scale = int(entry.get("scale") or 10000)
        self.restore_question.emit(entry.get("question", ""), scale)

    def _on_load_map(self):
        entry = self._selected_entry()
        if not entry:
            QMessageBox.information(self, "MTD-NLQ", "Seleccione una consulta del historial.")
            return
        if not entry.get("has_geometry"):
            QMessageBox.information(
                self,
                "MTD-NLQ",
                "Esta consulta no tiene geometría guardada (formato tabla).",
            )
            return
        data = self.store.load_response(entry["id"])
        geojson_path = (data or {}).get("_results_geojson_path")
        if not geojson_path or not os.path.isfile(geojson_path):
            QMessageBox.warning(self, "MTD-NLQ", "No se encontró results.geojson en la cápsula.")
            return
        label = (entry.get("question") or "consulta")[:48]
        self.load_on_map.emit(
            geojson_path,
            label,
            int(entry.get("scale") or 10000),
            str(data.get("source_schema") or ""),
            str(data.get("source_table") or ""),
            str(data.get("sql") or ""),
            str(data.get("style_qml") or ""),
        )

    def _on_open_folder(self):
        entry = self._selected_entry()
        if not entry:
            return
        folder = self.store.capsule_folder(entry["id"])
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "MTD-NLQ", "La carpeta de la cápsula ya no existe.")
            return
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def _on_delete(self):
        entry = self._selected_entry()
        if not entry:
            return
        answer = QMessageBox.question(
            self,
            "MTD-NLQ",
            "¿Eliminar esta consulta del historial local?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.store.delete(entry["id"])
        self.refresh()
