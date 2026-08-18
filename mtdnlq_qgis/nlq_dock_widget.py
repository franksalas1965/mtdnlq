# -*- coding: utf-8 -*-
"""Panel acoplable principal del plugin MTD-NLQ."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .history_panel import HistoryPanel
from .map_locator import MapLocator
from .mtd_fields import normalize_geojson_results
from .query_history_store import QueryHistoryStore
from .query_worker import QueryWorker
from .result_panel import ResultPanel
from .scale_presets import fill_scale_combo, get_scale_option, set_combo_scale
from .settings_dialog import SettingsDialog
from .settings_manager import SettingsManager
from .ui_icons import theme_icon


class NlqDockWidget(QDockWidget):
    """Dock con entrada NL, opciones y panel de resultados."""

    def __init__(self, iface, settings: SettingsManager, parent=None):
        super().__init__("MTD-NLQ — Consulta natural", parent)
        self.iface = iface
        self.settings = settings
        self.map_locator = MapLocator(iface, settings)
        self.history_store = QueryHistoryStore(
            max_entries=self.settings.get("history_max_entries")
        )
        self._worker = None

        self.setObjectName("MtdnlqDockWidget")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._build_ui()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        self.tabs = QTabWidget()

        # --- Pestaña Consulta ---
        query_tab = QWidget()
        query_layout = QVBoxLayout(query_tab)
        query_layout.setContentsMargins(4, 8, 4, 4)

        intro = QLabel("Pregunte en español sobre el MTD.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #555; font-size: 11px;")
        query_layout.addWidget(intro)

        scale_row = QHBoxLayout()
        self.scale_combo = QComboBox()
        fill_scale_combo(self.scale_combo)
        set_combo_scale(self.scale_combo, self.settings.get("mtd_scale"))
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        scale_row.addWidget(QLabel("Escala:"))
        scale_row.addWidget(self.scale_combo, 1)
        self.scale_label = QLabel("")
        self.scale_label.setStyleSheet("color: #555; font-size: 11px;")
        scale_row.addWidget(self.scale_label)
        query_layout.addLayout(scale_row)
        self._update_scale_label()

        self.question_edit = QTextEdit()
        self.question_edit.setPlaceholderText(
            "Ej.: ¿Cuántos ríos y arroyos hay?\n"
            "Ej.: Lista las ciudades con más de 10000 habitantes"
        )
        self.question_edit.setMinimumHeight(72)
        self.question_edit.setMaximumHeight(90)
        self.question_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        query_layout.addWidget(self.question_edit)

        options_row = QHBoxLayout()
        self.explain_check = QCheckBox("Incluir explicación")
        self.explain_check.setChecked(self.settings.get("explain_by_default"))
        options_row.addWidget(self.explain_check)

        self.format_combo = QComboBox()
        self.format_combo.addItem("GeoJSON", "geojson")
        self.format_combo.addItem("Tabla", "table")
        self.format_combo.setItemData(
            0,
            "Incluye geometría y botón «Localizar» por fila en el mapa.",
            Qt.ToolTipRole,
        )
        self.format_combo.setItemData(
            1,
            "Solo atributos en tabla; no permite localizar en el mapa.",
            Qt.ToolTipRole,
        )
        self.format_combo.setToolTip(
            "GeoJSON: ver en mapa · Tabla: solo datos alfanuméricos"
        )
        fmt = self.settings.get("output_format")
        idx = self.format_combo.findData(fmt)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        options_row.addWidget(QLabel("Formato:"))
        options_row.addWidget(self.format_combo)
        options_row.addStretch()
        query_layout.addLayout(options_row)

        btn_row = QHBoxLayout()

        self.query_btn = QPushButton("Consultar")
        self.query_btn.setIcon(theme_icon("mActionSearch.svg", "mActionStart.svg"))
        self.query_btn.setToolTip(
            "Enviar la pregunta al servicio MTD-NLQ y obtener resultados "
            "(SQL + tabla o GeoJSON)."
        )
        self.query_btn.setDefault(True)
        self.query_btn.clicked.connect(self.run_query)
        btn_row.addWidget(self.query_btn)

        self.settings_btn = QPushButton("Configuración…")
        self.settings_btn.setIcon(theme_icon("mActionOptions.svg", "mActionConfigure.svg"))
        self.settings_btn.setToolTip(
            "Abrir opciones del plugin: URL del servicio, escala MTD, timeout, mapa, etc."
        )
        self.settings_btn.clicked.connect(self.open_settings)
        btn_row.addWidget(self.settings_btn)

        self.clear_btn = QPushButton("Limpiar")
        self.clear_btn.setIcon(theme_icon("mActionDeleteAll.svg", "mActionRemove.svg"))
        self.clear_btn.setToolTip(
            "Borrar resultados, SQL y explicación; vuelve a la pestaña Consulta."
        )
        self.clear_btn.clicked.connect(self.clear_results)
        btn_row.addWidget(self.clear_btn)

        btn_row.addStretch()
        query_layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        query_layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(20)
        query_layout.addWidget(self.status_label)

        query_layout.addStretch()

        self._tab_query = self.tabs.addTab(query_tab, "Consulta")

        # --- Pestaña Resultados ---
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.setContentsMargins(0, 0, 0, 0)

        self.result_panel = ResultPanel(self.map_locator)
        results_layout.addWidget(self.result_panel, 1)

        self._tab_results = self.tabs.addTab(results_tab, "Resultados")

        # --- Pestaña Historial ---
        self.history_panel = HistoryPanel(self.history_store)
        self.history_panel.restore_results.connect(self._on_history_restore_results)
        self.history_panel.restore_question.connect(self._on_history_restore_question)
        self.history_panel.load_on_map.connect(self._on_history_load_map)
        self._tab_history = self.tabs.addTab(self.history_panel, "Historial")

        layout.addWidget(self.tabs, 1)

        self.setWidget(container)

    def _on_scale_changed(self):
        denom = self.scale_combo.currentData()
        if denom is not None:
            self.settings.set("mtd_scale", int(denom))
        self._update_scale_label()

    def _update_scale_label(self):
        opt = get_scale_option(self.scale_combo.currentData() or 10000)
        self.scale_label.setText(f"{opt['prefix']}* → {opt['database']}")

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec_():
            self.explain_check.setChecked(self.settings.get("explain_by_default"))
            idx = self.format_combo.findData(self.settings.get("output_format"))
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)
            set_combo_scale(self.scale_combo, self.settings.get("mtd_scale"))
            self._update_scale_label()
            self.status_label.setText("Configuración guardada.")

    def clear_results(self):
        self.result_panel.clear()
        self.status_label.clear()
        self.tabs.setCurrentIndex(self._tab_query)

    def run_query(self):
        question = self.question_edit.toPlainText().strip()
        if len(question) < 5:
            QMessageBox.warning(
                self,
                "MTD-NLQ",
                "Escriba una pregunta de al menos 5 caracteres.",
            )
            return

        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "MTD-NLQ", "Ya hay una consulta en curso.")
            return

        scale = int(self.scale_combo.currentData() or self.settings.get("mtd_scale"))
        opt = get_scale_option(scale)
        timeout = self.settings.get("timeout_seconds")

        self._set_query_controls_enabled(False)
        self.progress.show()
        self.status_label.setText(
            f"Consultando MTD-NLQ ({opt['label']})… "
            f"puede tardar varios minutos (timeout {timeout}s)."
        )
        self.result_panel.clear()

        self._worker = QueryWorker(
            base_url=self.settings.get("api_base_url"),
            timeout_seconds=timeout,
            question=question,
            output_format=self.format_combo.currentData(),
            max_results=self.settings.get("max_results"),
            explain=self.explain_check.isChecked(),
            scale=scale,
            use_async=self.settings.get("use_async_queries"),
            poll_interval_seconds=self.settings.get("poll_interval_seconds"),
        )
        self._worker.finished_ok.connect(
            lambda data: self._on_query_ok(data, scale_label=opt["label"])
        )
        self._worker.finished_error.connect(self._on_query_error)
        self._worker.status_update.connect(self._on_status_update)
        self._worker.finished.connect(self._on_query_finished)
        self._worker.start()

    def _on_status_update(self, message: str):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #333;")

    def _set_query_controls_enabled(self, enabled: bool):
        self.query_btn.setEnabled(enabled)
        self.scale_combo.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.explain_check.setEnabled(enabled)
        self.question_edit.setEnabled(enabled)
        self.settings_btn.setEnabled(enabled)

    def _on_query_ok(self, data: dict, scale_label: str = ""):
        data = self._normalize_response(data)
        if not scale_label and data.get("scale"):
            scale_label = get_scale_option(int(data["scale"]))["label"]
        self.result_panel.show_response(
            data,
            show_sql=self.settings.get("show_sql_panel"),
            show_meta=self.settings.get("show_metadata_bar"),
            scale_label=scale_label,
        )
        question = self.question_edit.toPlainText().strip()
        try:
            self.history_store.save_success(question, data)
            self.history_panel.refresh()
        except Exception:
            pass
        self.tabs.setCurrentIndex(self._tab_results)
        self.status_label.setText("Consulta completada.")
        self.status_label.setStyleSheet("color: green;")

    def _on_history_restore_results(self, data: dict):
        data = self._normalize_response(data)
        scale_label = ""
        if data.get("scale"):
            scale_label = get_scale_option(int(data["scale"]))["label"]
        self.result_panel.show_response(
            data,
            show_sql=self.settings.get("show_sql_panel"),
            show_meta=self.settings.get("show_metadata_bar"),
            scale_label=scale_label,
        )
        self.tabs.setCurrentIndex(self._tab_results)
        self.status_label.setText("Resultados restaurados desde el historial local.")
        self.status_label.setStyleSheet("color: #2563eb;")

    def _on_history_restore_question(self, question: str, scale: int):
        self.question_edit.setPlainText(question)
        set_combo_scale(self.scale_combo, scale)
        self._update_scale_label()
        self.tabs.setCurrentIndex(self._tab_query)
        self.status_label.setText("Pregunta cargada desde el historial.")
        self.status_label.setStyleSheet("color: #2563eb;")

    def _on_history_load_map(self, geojson_path: str, label: str):
        ok = self.map_locator.load_geojson_file(geojson_path, label)
        if ok:
            self.status_label.setText(f"Capa añadida al mapa: {label[:40]}")
            self.status_label.setStyleSheet("color: green;")
        else:
            QMessageBox.warning(
                self,
                "MTD-NLQ",
                "No se pudo cargar el GeoJSON como capa. Compruebe que el archivo existe.",
            )

    def _on_query_error(self, message: str):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: red;")
        QMessageBox.critical(self, "MTD-NLQ — Error", message)

    @staticmethod
    def _normalize_response(data: dict) -> dict:
        """Asegura códigos MTD como texto (geocodigo, geo_id, …) para QGIS/PostGIS."""
        if not data:
            return data
        out = dict(data)
        if "results" in out:
            out["results"] = normalize_geojson_results(out.get("results"))
        return out

    def _on_query_finished(self):
        self._set_query_controls_enabled(True)
        self.progress.hide()
