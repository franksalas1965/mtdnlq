"""Tests del servicio layer_styles."""
from unittest.mock import MagicMock, patch

from mtdnlq.services.layer_style_service import fetch_layer_style_qml


@patch("mtdnlq.services.layer_style_service.get_db_session")
def test_fetch_layer_style_prefers_named_style(mock_session_ctx):
    session = MagicMock()
    session.execute.return_value.fetchone.return_value = ("<qml/>", "rios_y_arroyos_lineal_i")
    mock_session_ctx.return_value.__enter__.return_value = session

    qml, name = fetch_layer_style_qml("10_hidrografia", "rios_y_arroyos_lineal", 10000, mode="i")

    assert qml == "<qml/>"
    assert name == "rios_y_arroyos_lineal_i"


@patch("mtdnlq.services.layer_style_service.get_db_session")
def test_fetch_layer_style_returns_none_when_missing(mock_session_ctx):
    session = MagicMock()
    session.execute.return_value.fetchone.return_value = None
    mock_session_ctx.return_value.__enter__.return_value = session

    qml, name = fetch_layer_style_qml("10_hidrografia", "missing_table", 10000)

    assert qml is None
    assert name is None
