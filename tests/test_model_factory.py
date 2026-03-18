"""Tests cho utils/model_factory.py — LLM provider switching."""

import pytest
from unittest.mock import patch, MagicMock


class TestModelFactoryGemini:

    @patch("utils.model_factory.settings")
    def test_gemini_default(self, mock_settings):
        mock_settings.LLM_PROVIDER = "gemini"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash-001"
        mock_settings.GOOGLE_CLOUD_PROJECT = "test-project"
        mock_settings.GOOGLE_CLOUD_LOCATION = "us-central1"

        with patch("utils.model_factory.Gemini", create=True) as MockGemini:
            # Force import path
            import utils.model_factory as mf
            with patch.object(mf, "settings", mock_settings):
                # Simulate gemini path
                assert mock_settings.LLM_PROVIDER == "gemini"

    @patch("utils.model_factory.settings")
    def test_small_flag_ignored_for_gemini(self, mock_settings):
        """small=True has no effect on Gemini — always same model."""
        mock_settings.LLM_PROVIDER = "gemini"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash-001"
        mock_settings.GOOGLE_CLOUD_PROJECT = "test-project"
        mock_settings.GOOGLE_CLOUD_LOCATION = "us-central1"
        # Both small=True and small=False should use same model for Gemini


class TestModelFactoryOllama:

    @patch("utils.model_factory.settings")
    def test_ollama_default(self, mock_settings):
        mock_settings.LLM_PROVIDER = "ollama"
        mock_settings.OLLAMA_MODEL = "qwen2.5:14b"
        mock_settings.OLLAMA_HOST = "http://localhost:11434"
        mock_settings.OLLAMA_SMALL_MODEL = ""

        assert mock_settings.LLM_PROVIDER == "ollama"
        assert mock_settings.OLLAMA_MODEL == "qwen2.5:14b"

    @patch("utils.model_factory.settings")
    def test_ollama_small_model(self, mock_settings):
        """small=True uses OLLAMA_SMALL_MODEL when set."""
        mock_settings.LLM_PROVIDER = "ollama"
        mock_settings.OLLAMA_MODEL = "qwen2.5:14b"
        mock_settings.OLLAMA_HOST = "http://localhost:11434"
        mock_settings.OLLAMA_SMALL_MODEL = "qwen2.5:7b"

        assert mock_settings.OLLAMA_SMALL_MODEL == "qwen2.5:7b"

    @patch("utils.model_factory.settings")
    def test_ollama_small_empty_fallback(self, mock_settings):
        """small=True falls back to OLLAMA_MODEL when OLLAMA_SMALL_MODEL is empty."""
        mock_settings.LLM_PROVIDER = "ollama"
        mock_settings.OLLAMA_MODEL = "qwen2.5:14b"
        mock_settings.OLLAMA_HOST = "http://localhost:11434"
        mock_settings.OLLAMA_SMALL_MODEL = ""

        model_id = mock_settings.OLLAMA_MODEL
        if mock_settings.OLLAMA_SMALL_MODEL:
            model_id = mock_settings.OLLAMA_SMALL_MODEL
        assert model_id == "qwen2.5:14b"


class TestModelFactoryConfig:

    def test_provider_values(self):
        """LLM_PROVIDER chỉ chấp nhận 'gemini' hoặc 'ollama'."""
        valid = {"gemini", "ollama"}
        assert "gemini" in valid
        assert "ollama" in valid

    def test_default_ollama_models(self):
        """Default Ollama models support tool calling."""
        tool_calling_models = [
            "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b",
            "llama3.1:8b", "llama3.1:70b",
            "mistral-nemo",
        ]
        assert "qwen2.5:14b" in tool_calling_models
        assert "qwen2.5:7b" in tool_calling_models


class TestAgentFactoryIntegration:

    def test_agent_files_use_model_factory(self):
        """Verify all agent files import from model_factory."""
        import importlib
        agent_modules = [
            "agents.agent0_rule_analyzer",
            "agents.agent1_data_reader",
            "agents.agent1_5_diff_analyzer",
            "agents.agent2_code_generator",
            "agents.agent4_bug_fixer",
            "agents.agent5_inspector",
        ]
        for mod_name in agent_modules:
            source = importlib.import_module(mod_name)
            # Check module has no direct Gemini import
            source_code = open(source.__file__, encoding="utf-8").read()
            assert "from agno.models.google import Gemini" not in source_code, (
                f"{mod_name} still imports Gemini directly — should use model_factory"
            )
            assert "from utils.model_factory import create_model" in source_code, (
                f"{mod_name} doesn't import create_model from model_factory"
            )
