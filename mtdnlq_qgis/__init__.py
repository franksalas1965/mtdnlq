# -*- coding: utf-8 -*-
"""Plugin QGIS MTD-NLQ — consultas en lenguaje natural sobre MTD."""

def classFactory(iface):
    from .plugin import MtdnlqPlugin
    return MtdnlqPlugin(iface)
