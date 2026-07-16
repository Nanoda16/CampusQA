"""
Tests for centralized configuration (Pydantic Settings).

Covers:
- AI service config defaults
- Environment variable overrides (for both config namespaces)
- All expected keys present
- Backend config loading
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure ai_service is importable (no __init__.py in ai_service/)
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

import pytest
from pydantic import ValidationError


# ===================================================================
# AI Service Config
# ===================================================================


class TestAiServiceConfigDefaults:
    """Verify defaults match the hardcoded values in engine code."""

    def test_all_expected_keys_present(self):
        """The Settings class exposes every field listed in the task spec."""
        from config import Settings

        s = Settings()
        assert hasattr(s, "REJECTION_THRESHOLD")
        assert hasattr(s, "BM25_K1")
        assert hasattr(s, "BM25_B")
        assert hasattr(s, "RRF_K")
        assert hasattr(s, "RERANKER_ENABLED")
        assert hasattr(s, "RERANKER_MODEL")
        assert hasattr(s, "RERANKER_MAX_LENGTH")
        assert hasattr(s, "RERANKER_TOP_K")
        assert hasattr(s, "EMBEDDING_MODEL")
        assert hasattr(s, "EMBEDDING_DIM")
        assert hasattr(s, "LLM_MODEL")
        assert hasattr(s, "LLM_TEMPERATURE")
        assert hasattr(s, "LLM_MAX_TOKENS")
        assert hasattr(s, "ARTIFACT_DIR")
        assert hasattr(s, "INGESTION_TIMEOUT_S")
        # Legacy backward-compat fields
        assert hasattr(s, "DEEPSEEK_API_KEY")
        assert hasattr(s, "DEEPSEEK_BASE_URL")
        assert hasattr(s, "DEEPSEEK_MODEL")

    def test_default_values(self):
        """Defaults match engine code values (retriever, bm25, fusion, etc)."""
        from config import Settings

        s = Settings()
        assert s.REJECTION_THRESHOLD == 0.35
        assert s.CHUNK_SIZE == 512
        assert s.CHUNK_OVERLAP == 64
        assert s.TOP_K == 3
        assert s.BM25_K1 == 1.5
        assert s.BM25_B == 0.75
        assert s.RRF_K == 60.0
        assert s.RERANKER_ENABLED is True
        assert s.RERANKER_MODEL == "BAAI/bge-reranker-base"
        assert s.RERANKER_MAX_LENGTH == 512
        assert s.RERANKER_TOP_K == 3
        assert s.EMBEDDING_MODEL == "BAAI/bge-small-zh-v1.5"
        assert s.EMBEDDING_DIM == 512
        assert s.LLM_MODEL == "deepseek-chat"
        assert s.LLM_TEMPERATURE == 0.3
        assert s.LLM_MAX_TOKENS == 1024
        assert s.ARTIFACT_DIR == "data/artifacts"
        assert s.INGESTION_TIMEOUT_S == 300
        # Legacy backward compat
        assert s.DEEPSEEK_API_KEY == ""
        assert s.DEEPSEEK_BASE_URL == "https://api.deepseek.com"
        assert s.DEEPSEEK_MODEL == "deepseek-chat"


class TestAiServiceConfigEnvOverrides:
    """Environment variables override defaults."""

    # Save & restore env vars to avoid cross-test pollution
    _ENV_KEYS = [
        "REJECTION_THRESHOLD",
        "CHUNK_SIZE",
        "BM25_K1",
        "BM25_B",
        "RRF_K",
        "RERANKER_ENABLED",
        "RERANKER_MODEL",
        "RERANKER_MAX_LENGTH",
        "RERANKER_TOP_K",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIM",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "LLM_MAX_TOKENS",
        "ARTIFACT_DIR",
        "INGESTION_TIMEOUT_S",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
    ]

    @pytest.fixture(autouse=True)
    def _clean_env(self):
        """Remove all config env vars before each test, restore after."""
        saved = {}
        for key in self._ENV_KEYS:
            saved[key] = os.environ.pop(key, None)  # type: ignore[arg-type]
        yield
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _make(self, **overrides) -> "Settings":
        """Create a fresh Settings with *overrides* applied as env vars."""
        from config import Settings

        for k, v in overrides.items():
            os.environ[k] = str(v)
        return Settings()

    def test_rejection_threshold_override(self):
        s = self._make(REJECTION_THRESHOLD="0.8")
        assert s.REJECTION_THRESHOLD == 0.8

    def test_bm25_params_override(self):
        s = self._make(BM25_K1="2.0", BM25_B="0.5")
        assert s.BM25_K1 == 2.0
        assert s.BM25_B == 0.5

    def test_rrf_k_override(self):
        s = self._make(RRF_K="30.0")
        assert s.RRF_K == 30.0

    def test_reranker_enabled_false(self):
        s = self._make(RERANKER_ENABLED="false")
        assert s.RERANKER_ENABLED is False

    def test_reranker_params_override(self):
        s = self._make(
            RERANKER_MODEL="custom/model",
            RERANKER_MAX_LENGTH="256",
            RERANKER_TOP_K="5",
        )
        assert s.RERANKER_MODEL == "custom/model"
        assert s.RERANKER_MAX_LENGTH == 256
        assert s.RERANKER_TOP_K == 5

    def test_embedding_params_override(self):
        s = self._make(EMBEDDING_MODEL="other/model", EMBEDDING_DIM="768")
        assert s.EMBEDDING_MODEL == "other/model"
        assert s.EMBEDDING_DIM == 768

    def test_llm_params_override(self):
        s = self._make(
            LLM_MODEL="gpt-4",
            LLM_TEMPERATURE="0.7",
            LLM_MAX_TOKENS="2048",
        )
        assert s.LLM_MODEL == "gpt-4"
        assert s.LLM_TEMPERATURE == 0.7
        assert s.LLM_MAX_TOKENS == 2048

    def test_artifact_dir_override(self):
        s = self._make(ARTIFACT_DIR="/tmp/artifacts")
        assert s.ARTIFACT_DIR == "/tmp/artifacts"

    def test_ingestion_timeout_override(self):
        s = self._make(INGESTION_TIMEOUT_S="600")
        assert s.INGESTION_TIMEOUT_S == 600

    def test_deepseek_legacy_vars(self):
        """Legacy env var names still work."""
        s = self._make(
            DEEPSEEK_API_KEY="sk-test",
            DEEPSEEK_BASE_URL="https://custom.api.com",
            DEEPSEEK_MODEL="deepseek-coder",
        )
        assert s.DEEPSEEK_API_KEY == "sk-test"
        assert s.DEEPSEEK_BASE_URL == "https://custom.api.com"
        assert s.DEEPSEEK_MODEL == "deepseek-coder"

    def test_invalid_float_falls_back(self):
        """Invalid float in env var should not crash (pydantic validates)."""
        from config import Settings

        os.environ["REJECTION_THRESHOLD"] = "not-a-float"
        with pytest.raises(ValidationError):
            Settings()

    def test_invalid_int_falls_back(self):
        """Invalid int in env var raises ValidationError."""
        from config import Settings

        os.environ["BM25_K1"] = "not-an-int"
        with pytest.raises(ValidationError):
            Settings()


# ===================================================================
# Backend Config
# ===================================================================


class TestBackendConfig:
    """Backend config also follows the unified pattern."""

    @pytest.fixture(autouse=True)
    def _clean_env(self):
        """Backend config env vars we might touch."""
        keys = [
            "DB_HOST",
            "DB_PORT",
            "REDIS_FALLBACK_TO_FAKE",
            "CORS_ORIGINS",
        ]
        saved = {}
        for key in keys:
            saved[key] = os.environ.pop(key, None)
        yield
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def test_backend_config_loads(self):
        """Backend config instantiates without error (writes always succeed)."""
        from app.config import settings

        assert settings.DB_HOST == "localhost"
        assert settings.DB_PORT == 3306
        assert settings.REDIS_FALLBACK_TO_FAKE is True
        assert settings.DATABASE_URL is not None

    def test_backend_env_override(self):
        """Backend config respects env vars."""
        from app.config import Settings

        os.environ["DB_HOST"] = "10.0.0.1"
        s = Settings()
        assert s.DB_HOST == "10.0.0.1"
