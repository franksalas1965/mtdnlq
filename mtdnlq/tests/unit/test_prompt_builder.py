"""Tests unitarios para el constructor de prompts."""
from unittest.mock import patch, MagicMock
from mtdnlq.nlq.prompt_builder import build_prompt


def test_prompt_contains_question():
    question = "¿Cuántos puentes hay en La Habana?"
    with patch("mtdnlq.nlq.prompt_builder.schema_inspector") as mock_inspector:
        mock_inspector.build_schema_description.return_value = "ESQUEMA: tabla puentes"
        prompt = build_prompt(question)
    assert question in prompt


def test_prompt_contains_schema():
    question = "test"
    schema_text = "ESQUEMA DE BASE DE DATOS PostGIS:"
    with patch("mtdnlq.nlq.prompt_builder.schema_inspector") as mock_inspector:
        mock_inspector.build_schema_description.return_value = schema_text
        prompt = build_prompt(question)
    assert schema_text in prompt


def test_prompt_contains_few_shot_examples():
    with patch("mtdnlq.nlq.prompt_builder.schema_inspector") as mock_inspector:
        mock_inspector.build_schema_description.return_value = ""
        prompt = build_prompt("test")
    assert "EJEMPLOS" in prompt


def test_prompt_ends_with_sql_marker():
    with patch("mtdnlq.nlq.prompt_builder.schema_inspector") as mock_inspector:
        mock_inspector.build_schema_description.return_value = ""
        prompt = build_prompt("test question")
    assert prompt.strip().endswith("SQL:")
