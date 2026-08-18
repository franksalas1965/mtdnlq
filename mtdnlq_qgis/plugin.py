# -*- coding: utf-8 -*-
"""Clase principal del plugin QGIS MTD-NLQ."""
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .nlq_dock_widget import NlqDockWidget
from .settings_manager import SettingsManager


class MtdnlqPlugin:
    """Integración del servicio MTD-NLQ en QGIS 3.40.x."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.settings = SettingsManager()
        self.dock = None
        self.action = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icons", "mtdnlq.svg")
        self.action = QAction(QIcon(icon_path), "MTD-NLQ — Consulta natural", self.iface.mainWindow())
        self.action.setObjectName("MtdnlqPluginAction")
        self.action.setWhatsThis(
            "Abre el panel para consultas en lenguaje natural sobre el MTD "
            "mediante el servicio MTD-NLQ."
        )
        self.action.triggered.connect(self.toggle_dock)
        self.iface.addPluginToMenu("&MTD-NLQ", self.action)
        self.iface.addToolBarIcon(self.action)

        self.dock = NlqDockWidget(self.iface, self.settings, self.iface.mainWindow())
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        if self.settings.get("dock_visible_on_start"):
            self.dock.show()
        else:
            self.dock.hide()

    def unload(self):
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action:
            self.iface.removePluginMenu("&MTD-NLQ", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

    def toggle_dock(self):
        if not self.dock:
            return
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()
            self.dock.raise_()
