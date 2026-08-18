"""Tests de creación automática de query_history."""
from unittest.mock import MagicMock, patch

from mtdnlq.db.query_history import ensure_query_history_table, _ensured_scales


@patch("mtdnlq.db.query_history.get_db_session")
def test_ensure_query_history_runs_ddl_once_per_scale(mock_session_ctx):
    _ensured_scales.clear()
    session = MagicMock()
    mock_session_ctx.return_value.__enter__.return_value = session

    ensure_query_history_table(10000)
    ensure_query_history_table(10000)

    mock_session_ctx.assert_called_once_with(10000)
    session.execute.assert_called_once()
    assert 10000 in _ensured_scales
