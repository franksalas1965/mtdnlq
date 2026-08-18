# -*- coding: utf-8 -*-
"""Diálogo de configuración del plugin."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .query_worker import HealthWorker
from .scale_presets import (
    DEFAULT_SCALE,
    fill_scale_combo,
    get_scale_option,
    set_combo_scale,
    suggested_api_url,
)
from .settings_manager import DEFAULTS, SettingsManager


class SettingsDialog(QDialog):
    """Opciones portables almacenadas en el perfil de QGIS."""

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._health_worker = None
        self.setWindowTitle("MTD-NLQ — Configuración")
        self.setMinimumWidth(520)
        self.setMaximumHeight(620)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # --- Pestaña 1: conexión al servicio y estado del LLM ---
        conn_tab = QWidget()
        conn_layout = QVBoxLayout(conn_tab)
        conn_layout.setContentsMargins(4, 8, 4, 4)

        api_group = QGroupBox("Servicio MTD-NLQ")
        api_form = QFormLayout(api_group)

        self.scale_combo = QComboBox()
        fill_scale_combo(self.scale_combo)
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        api_form.addRow("Escala MTD:", self.scale_combo)

        self.scale_hint = QLabel("")
        self.scale_hint.setWordWrap(True)
        self.scale_hint.setStyleSheet("color: #555; font-size: 11px;")
        api_form.addRow("", self.scale_hint)

        self.auto_url_check = QCheckBox(
            "Sugerir URL distinta por escala (solo despliegues con un puerto por BD)"
        )
        api_form.addRow(self.auto_url_check)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("http://localhost:8001")
        api_form.addRow("URL base de la API:", self.url_edit)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 3600)
        self.timeout_spin.setSuffix(" s")
        api_form.addRow("Tiempo de espera:", self.timeout_spin)

        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(0, 1000)
        self.max_results_spin.setSpecialValueText("Todos (sin límite)")
        self.max_results_spin.setToolTip(
            "0 = devolver todos los registros (el servidor no añade LIMIT).\n"
            "1–1000 = número máximo de filas por consulta."
        )
        api_form.addRow("Máximo de resultados:", self.max_results_spin)

        self.max_results_hint = QLabel(
            "Use 0 para mostrar todos los resultados. Valores 1–1000 limitan las filas "
            "(consultas grandes pueden tardar más)."
        )
        self.max_results_hint.setWordWrap(True)
        self.max_results_hint.setStyleSheet("color: #555; font-size: 11px;")
        api_form.addRow("", self.max_results_hint)

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItem("GeoJSON (con geometría si existe)", "geojson")
        self.output_format_combo.addItem("Tabla JSON", "table")
        api_form.addRow("Formato de salida por defecto:", self.output_format_combo)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Probar conexión")
        self.test_btn.clicked.connect(self._test_connection)
        self.test_status = QLabel("")
        self.test_status.setWordWrap(True)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_status, 1)
        api_form.addRow("", test_row)

        conn_layout.addWidget(api_group)

        llm_group = QGroupBox("Motor LLM (servidor — solo lectura)")
        llm_form = QFormLayout(llm_group)

        self.llm_mode_label = QLabel("—")
        llm_form.addRow("Modo:", self.llm_mode_label)

        self.llm_device_label = QLabel("—")
        llm_form.addRow("Dispositivo:", self.llm_device_label)

        self.llm_model_label = QLabel("—")
        llm_form.addRow("Modelo:", self.llm_model_label)

        self.llm_url_label = QLabel("—")
        self.llm_url_label.setWordWrap(True)
        llm_form.addRow("URL Ollama:", self.llm_url_label)

        self.llm_key_label = QLabel("—")
        llm_form.addRow("API key cloud:", self.llm_key_label)

        llm_hint = QLabel(
            "El LLM se configura en el .env del servidor MTD-NLQ (Ollama local CPU/GPU "
            "u Ollama Cloud). Tras cambiar .env reinicie uvicorn. "
            "Use «Probar conexión» para actualizar estos datos."
        )
        llm_hint.setWordWrap(True)
        llm_hint.setStyleSheet("color: #555; font-size: 11px;")
        llm_form.addRow("", llm_hint)

        conn_layout.addWidget(llm_group)
        conn_layout.addStretch()
        tabs.addTab(conn_tab, "Conexión")

        # --- Pestaña 2: interfaz del plugin y mapa ---
        ui_tab = QWidget()
        ui_outer = QVBoxLayout(ui_tab)
        ui_outer.setContentsMargins(4, 8, 4, 4)

        ui_scroll = QScrollArea()
        ui_scroll.setWidgetResizable(True)
        ui_scroll.setFrameShape(QScrollArea.NoFrame)
        ui_scroll_content = QWidget()
        ui_scroll_layout = QVBoxLayout(ui_scroll_content)
        ui_scroll_layout.setContentsMargins(0, 0, 0, 0)

        ui_group = QGroupBox("Interfaz y consultas")
        ui_form = QFormLayout(ui_group)

        self.explain_check = QCheckBox("Solicitar explicación del SQL en cada consulta")
        ui_form.addRow(self.explain_check)

        self.show_sql_check = QCheckBox("Mostrar panel con el SQL generado")
        ui_form.addRow(self.show_sql_check)

        self.show_meta_check = QCheckBox("Mostrar barra de metadatos (total, tiempo, modo)")
        ui_form.addRow(self.show_meta_check)

        self.dock_visible_check = QCheckBox("Mostrar panel al cargar el plugin")
        ui_form.addRow(self.dock_visible_check)

        self.async_check = QCheckBox(
            "Usar cola asíncrona (recomendado: encola y consulta estado cada pocos segundos)"
        )
        ui_form.addRow(self.async_check)

        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 30)
        self.poll_spin.setSuffix(" s")
        ui_form.addRow("Intervalo de consulta de estado:", self.poll_spin)

        ui_scroll_layout.addWidget(ui_group)

        map_group = QGroupBox("Mapa — localizar registro")
        map_form = QFormLayout(map_group)

        self.crs_edit = QLineEdit()
        self.crs_edit.setPlaceholderText("EPSG:4267")
        map_form.addRow("CRS para resultados:", self.crs_edit)

        self.color_edit = QLineEdit()
        self.color_edit.setPlaceholderText("#2563eb")
        map_form.addRow("Color de resaltado:", self.color_edit)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 10)
        map_form.addRow("Grosor de línea/borde:", self.width_spin)

        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(0, 100)
        self.buffer_spin.setSuffix(" %")
        map_form.addRow("Margen al hacer zoom:", self.buffer_spin)

        self.remove_prev_check = QCheckBox("Quitar capa de localización anterior")
        map_form.addRow(self.remove_prev_check)

        crs_hint = QLabel(
            "Si el mapa usa OSM (EPSG:3857) y los resultados MTD están en EPSG:4267, "
            "QGIS puede registrar «transformación aproximada» al hacer zoom. Es normal "
            "para visualizar; no afecta la consulta NL. Para menos aviso, ajuste "
            "Transformación de CRS en Opciones de QGIS (NAD27 → WGS84)."
        )
        crs_hint.setWordWrap(True)
        crs_hint.setStyleSheet("color: #555; font-size: 10px;")
        map_form.addRow("", crs_hint)

        geocodigo_hint = QLabel(
            "En capas PostGIS del MTD, geocodigo es texto (varchar). Si filtra en QGIS "
            "por geocodigo use comillas: \"geocodigo\" IN ('70400010','70400020'). "
            "Valores numéricos sin comillas provocan error character varying = integer."
        )
        geocodigo_hint.setWordWrap(True)
        geocodigo_hint.setStyleSheet("color: #555; font-size: 10px;")
        map_form.addRow("", geocodigo_hint)

        ui_scroll_layout.addWidget(map_group)
        ui_scroll_layout.addStretch()
        ui_scroll.setWidget(ui_scroll_content)
        ui_outer.addWidget(ui_scroll)
        tabs.addTab(ui_tab, "Interfaz y mapa")

        layout.addWidget(tabs)

        hint = QLabel(
            "Los ajustes se guardan en el perfil de QGIS (QSettings). "
            "El LLM se configura en el .env del servidor MTD-NLQ."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        layout.addWidget(buttons)

    def _load_values(self):
        s = self.settings.as_dict()
        self.url_edit.setText(str(s["api_base_url"]))
        self.timeout_spin.setValue(int(s["timeout_seconds"]))
        self.max_results_spin.setValue(int(s["max_results"]))
        idx = self.output_format_combo.findData(s["output_format"])
        if idx >= 0:
            self.output_format_combo.setCurrentIndex(idx)
        self.explain_check.setChecked(bool(s["explain_by_default"]))
        self.show_sql_check.setChecked(bool(s["show_sql_panel"]))
        self.show_meta_check.setChecked(bool(s["show_metadata_bar"]))
        self.dock_visible_check.setChecked(bool(s["dock_visible_on_start"]))
        self.async_check.setChecked(bool(s.get("use_async_queries", True)))
        self.poll_spin.setValue(int(s.get("poll_interval_seconds", 3)))
        self.crs_edit.setText(str(s["map_crs"]))
        self.color_edit.setText(str(s["highlight_color"]))
        self.width_spin.setValue(int(s["highlight_width"]))
        self.buffer_spin.setValue(int(s["zoom_buffer_percent"]))
        self.remove_prev_check.setChecked(bool(s["remove_previous_highlight"]))
        set_combo_scale(self.scale_combo, int(s.get("mtd_scale", DEFAULT_SCALE)))
        self.auto_url_check.setChecked(bool(s.get("auto_url_by_scale", DEFAULTS["auto_url_by_scale"])))
        self._update_scale_hint()

    def _on_scale_changed(self):
        self._update_scale_hint()
        if self.auto_url_check.isChecked():
            denom = self.scale_combo.currentData()
            self.url_edit.setText(suggested_api_url(denom))

    def _update_scale_hint(self):
        opt = get_scale_option(self.scale_combo.currentData() or DEFAULT_SCALE)
        url = suggested_api_url(opt["denominator"])
        self.scale_hint.setText(
            f"Prefijo: {opt['prefix']} · Base: {opt['database']}. "
            "Un mismo servicio MTD-NLQ puede atender todas las escalas vía el campo scale."
        )

    def _restore_defaults(self):
        for key, value in DEFAULTS.items():
            self.settings.set(key, value)
        self._load_values()

    def _test_connection(self):
        self.test_btn.setEnabled(False)
        self.test_status.setText("Conectando…")
        url = self.url_edit.text().strip() or DEFAULTS["api_base_url"]
        # Health puede tardar si el servidor está ocupado con otra consulta NL
        health_timeout = max(30, min(int(self.timeout_spin.value()), 60))
        self._health_worker = HealthWorker(url, timeout_seconds=health_timeout)
        self._health_worker.finished_ok.connect(self._on_health_ok)
        self._health_worker.finished_error.connect(self._on_health_error)
        self._health_worker.finished.connect(lambda: self.test_btn.setEnabled(True))
        self._health_worker.start()

    def _on_health_ok(self, data: dict):
        status = data.get("status", "?")
        db = data.get("database", "?")
        model = data.get("llm_model", "?")
        llm = data.get("llm") or {}

        mode = llm.get("ollama_mode", "—")
        device = llm.get("ollama_device", "—")
        url = llm.get("ollama_base_url", "—")
        key_ok = llm.get("ollama_api_key_configured", False)

        self.llm_mode_label.setText(str(mode))
        self.llm_device_label.setText(str(device))
        self.llm_model_label.setText(str(llm.get("model", model)))
        self.llm_url_label.setText(str(url))
        self.llm_key_label.setText(
            "Configurada" if key_ok else ("No aplica (local)" if mode == "local" else "Falta OLLAMA_API_KEY")
        )

        extra = ""
        if mode == "cloud":
            extra = " · Ollama Cloud"
        elif device == "gpu":
            extra = " · GPU local"
        elif device == "cpu":
            extra = " · CPU local"

        self.test_status.setText(
            f"OK — {status}, BD: {db}, modelo: {llm.get('model', model)}{extra}"
        )
        self.test_status.setStyleSheet("color: green;")

    def _on_health_error(self, message: str):
        self.test_status.setText(message)
        self.test_status.setStyleSheet("color: red;")

    def accept(self):
        self.settings.save_all(
            {
                "api_base_url": self.url_edit.text().strip() or DEFAULTS["api_base_url"],
                "mtd_scale": int(self.scale_combo.currentData() or DEFAULT_SCALE),
                "auto_url_by_scale": self.auto_url_check.isChecked(),
                "timeout_seconds": self.timeout_spin.value(),
                "max_results": self.max_results_spin.value(),
                "output_format": self.output_format_combo.currentData(),
                "explain_by_default": self.explain_check.isChecked(),
                "show_sql_panel": self.show_sql_check.isChecked(),
                "show_metadata_bar": self.show_meta_check.isChecked(),
                "dock_visible_on_start": self.dock_visible_check.isChecked(),
                "use_async_queries": self.async_check.isChecked(),
                "poll_interval_seconds": self.poll_spin.value(),
                "map_crs": self.crs_edit.text().strip() or DEFAULTS["map_crs"],
                "highlight_color": self.color_edit.text().strip() or DEFAULTS["highlight_color"],
                "highlight_width": self.width_spin.value(),
                "zoom_buffer_percent": self.buffer_spin.value(),
                "remove_previous_highlight": self.remove_prev_check.isChecked(),
            }
        )
        super().accept()
