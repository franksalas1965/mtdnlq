"""Tests de configuración Ollama CPU/GPU/cloud."""
from unittest.mock import patch

from mtdnlq.core.config import (
    DEFAULT_LLM_MODEL_CLOUD,
    DEFAULT_LLM_MODEL_LOCAL,
    Settings,
    settings,
)
from mtdnlq.llm.ollama_config import build_ollama_options, llm_public_info


def test_cloud_default_model_when_local_placeholder():
    cfg = Settings(
        llm_provider="ollama",
        ollama_mode="cloud",
        llm_model="qwen2.5-coder:7b",
    )
    assert cfg.llm_model == DEFAULT_LLM_MODEL_CLOUD


def test_cloud_explicit_model_preserved():
    cfg = Settings(
        llm_provider="ollama",
        ollama_mode="cloud",
        llm_model="qwen3.5:397b",
    )
    assert cfg.llm_model == "qwen3.5:397b"


def test_local_default_model_from_generic():
    cfg = Settings(llm_provider="ollama", ollama_mode="local", llm_model="gpt-4o")
    assert cfg.llm_model == DEFAULT_LLM_MODEL_LOCAL


def test_env_file_resolves_from_project_root():
    from mtdnlq.core.config import _ENV_FILE

    assert _ENV_FILE.name == ".env"
    assert _ENV_FILE.parent.name == "mtdnlq"
    assert _ENV_FILE.is_file()


def test_build_options_cpu():
    with patch.object(settings, "ollama_mode", "local"), patch.object(
        settings, "ollama_device", "cpu"
    ), patch.object(settings, "ollama_num_thread", 0):
        opts = build_ollama_options()
        assert opts["num_gpu"] == 0


def test_build_options_cloud_no_gpu():
    with patch.object(settings, "ollama_mode", "cloud"):
        opts = build_ollama_options()
        assert "num_gpu" not in opts


def test_llm_public_info_no_api_key():
    with patch.object(settings, "ollama_api_key", ""):
        info = llm_public_info()
        assert info["ollama_api_key_configured"] is False
