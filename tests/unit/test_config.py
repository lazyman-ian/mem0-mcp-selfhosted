"""Tests for config.py — build_config() with various env var combinations."""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest


class TestBuildConfig:
    def _build_with_env(self, env: dict):
        """Build config with the given env vars, mocking resolve_token."""
        # Clear env vars that could leak from integration tests or CLI
        leak_keys = [k for k in os.environ if k.startswith("MEM0_")]
        if "GOOGLE_API_KEY" in os.environ:
            leak_keys.append("GOOGLE_API_KEY")
        with patch.dict("os.environ", env, clear=False) as patched_env:
            for k in leak_keys:
                if k not in env:
                    patched_env.pop(k, None)
            with patch("mem0_mcp_selfhosted.config.resolve_token", return_value="sk-test-token"):
                from mem0_mcp_selfhosted.config import build_config
                config_dict, providers_info = build_config()
                return config_dict, providers_info

    def test_defaults(self):
        """All defaults applied when no env vars set."""
        config_dict, provider_info = self._build_with_env({})

        assert config_dict["llm"]["provider"] == "anthropic"
        assert config_dict["llm"]["config"]["model"] == "claude-opus-4-6"
        assert config_dict["embedder"]["provider"] == "ollama"
        assert config_dict["embedder"]["config"]["model"] == "bge-m3"
        assert config_dict["vector_store"]["provider"] == "qdrant"
        assert config_dict["vector_store"]["config"]["collection_name"] == "mem0_mcp_selfhosted"
        assert config_dict["version"] == "v1.1"

    def test_env_overrides(self):
        """Environment variables override defaults."""
        env = {
            "MEM0_LLM_MODEL": "claude-sonnet-4-5-20250929",
            "MEM0_EMBED_MODEL": "nomic-embed-text",
            "MEM0_COLLECTION": "custom_collection",
        }
        config_dict, _ = self._build_with_env(env)

        assert config_dict["llm"]["config"]["model"] == "claude-sonnet-4-5-20250929"
        assert config_dict["embedder"]["config"]["model"] == "nomic-embed-text"
        assert config_dict["vector_store"]["config"]["collection_name"] == "custom_collection"

    def test_no_graph_store_key(self):
        """mem0ai >= 2.0 has no graph_store config — never emitted, even when
        the deprecated MEM0_ENABLE_GRAPH is still set."""
        config_dict, _ = self._build_with_env({"MEM0_ENABLE_GRAPH": "true"})
        assert "graph_store" not in config_dict

    def test_config_keys_match_memoryconfig_schema(self):
        """Every top-level key must be a valid mem0ai 2.x MemoryConfig field."""
        from mem0.configs.base import MemoryConfig

        config_dict, _ = self._build_with_env({"MEM0_HISTORY_DB_PATH": "/tmp/h.db"})
        valid_fields = set(MemoryConfig.model_fields)
        assert set(config_dict) <= valid_fields, (
            f"Unknown MemoryConfig keys: {set(config_dict) - valid_fields}"
        )

    def test_deprecated_graph_env_warns(self, caplog):
        """Setting graph-era env vars logs a deprecation warning."""
        with caplog.at_level(logging.WARNING, logger="mem0_mcp_selfhosted.config"):
            self._build_with_env({
                "MEM0_ENABLE_GRAPH": "true",
                "MEM0_GRAPH_LLM_PROVIDER": "gemini",
            })
        assert "MEM0_ENABLE_GRAPH" in caplog.text
        assert "MEM0_GRAPH_LLM_PROVIDER" in caplog.text
        assert "no effect" in caplog.text

    def test_no_warning_without_graph_env(self, caplog):
        """No deprecation warning when graph env vars are absent."""
        with caplog.at_level(logging.WARNING, logger="mem0_mcp_selfhosted.config"):
            self._build_with_env({})
        assert "Deprecated graph env" not in caplog.text

    def test_explicit_embedder_provider(self):
        """Embedder provider is always explicit (never default to openai)."""
        config_dict, _ = self._build_with_env({})
        assert config_dict["embedder"]["provider"] == "ollama"

    def test_provider_info_structure(self):
        """Provider info list includes Anthropic and Ollama entries."""
        _, providers_info = self._build_with_env({})

        provider_names = [pi["name"] for pi in providers_info]
        assert "ollama" in provider_names  # Always registered
        assert "anthropic" in provider_names

        anthropic_pi = next(pi for pi in providers_info if pi["name"] == "anthropic")
        assert "AnthropicOATLLM" in anthropic_pi["class_path"]

        ollama_pi = next(pi for pi in providers_info if pi["name"] == "ollama")
        assert "OllamaToolLLM" in ollama_pi["class_path"]

    def test_qdrant_optional_fields(self):
        """Optional Qdrant fields only included when env vars set."""
        config_dict, _ = self._build_with_env({})
        assert "api_key" not in config_dict["vector_store"]["config"]

        env = {"MEM0_QDRANT_API_KEY": "test-key"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["vector_store"]["config"]["api_key"] == "test-key"

    # --- Provider selection and config branching ---

    def test_default_llm_provider_is_anthropic(self):
        """Default provider is anthropic when MEM0_LLM_PROVIDER not set."""
        config_dict, _ = self._build_with_env({})
        assert config_dict["llm"]["provider"] == "anthropic"

    def test_ollama_llm_provider(self):
        """MEM0_LLM_PROVIDER=ollama sets the LLM provider to ollama."""
        env = {"MEM0_LLM_PROVIDER": "ollama"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["provider"] == "ollama"

    def test_unsupported_llm_provider_raises(self):
        """Unsupported MEM0_LLM_PROVIDER raises ValueError."""
        leak_keys = [k for k in os.environ if k.startswith("MEM0_")]
        env = {"MEM0_LLM_PROVIDER": "gemini"}
        with patch.dict("os.environ", env, clear=False) as patched_env:
            for k in leak_keys:
                if k not in env:
                    patched_env.pop(k, None)
            with patch("mem0_mcp_selfhosted.config.resolve_token", return_value="sk-test"):
                from mem0_mcp_selfhosted.config import build_config
                with pytest.raises(ValueError, match="Unsupported MEM0_LLM_PROVIDER='gemini'"):
                    build_config()

    def test_anthropic_config_has_api_key_and_max_tokens(self):
        """Anthropic LLM config includes api_key and max_tokens."""
        config_dict, _ = self._build_with_env({})
        llm_cfg = config_dict["llm"]["config"]
        assert llm_cfg["api_key"] == "sk-test-token"
        assert llm_cfg["max_tokens"] == 16384

    def test_ollama_config_has_base_url_no_api_key(self):
        """Ollama LLM config includes ollama_base_url, no api_key or max_tokens."""
        env = {"MEM0_LLM_PROVIDER": "ollama"}
        config_dict, _ = self._build_with_env(env)
        llm_cfg = config_dict["llm"]["config"]
        assert "ollama_base_url" in llm_cfg
        assert "api_key" not in llm_cfg
        assert "max_tokens" not in llm_cfg

    def test_ollama_default_model(self):
        """Ollama provider defaults to qwen3:14b when MEM0_LLM_MODEL not set."""
        env = {"MEM0_LLM_PROVIDER": "ollama"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["model"] == "qwen3:14b"

    def test_ollama_llm_url_custom(self):
        """MEM0_LLM_URL sets ollama_base_url when provider is ollama."""
        env = {"MEM0_LLM_PROVIDER": "ollama", "MEM0_LLM_URL": "http://gpu:11434"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["ollama_base_url"] == "http://gpu:11434"

    def test_ollama_llm_url_default(self):
        """MEM0_LLM_URL defaults to localhost:11434 when not set."""
        env = {"MEM0_LLM_PROVIDER": "ollama"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["ollama_base_url"] == "http://localhost:11434"

    def test_llm_url_not_read_for_anthropic(self):
        """MEM0_LLM_URL is not included in anthropic config."""
        env = {"MEM0_LLM_URL": "http://gpu:11434"}
        config_dict, _ = self._build_with_env(env)
        assert "ollama_base_url" not in config_dict["llm"]["config"]

    def test_openai_llm_provider(self):
        """MEM0_LLM_PROVIDER=openai includes api_key/base_url when set."""
        env = {
            "MEM0_LLM_PROVIDER": "openai",
            "MEM0_OPENAI_API_KEY": "sk-openai-test",
            "MEM0_OPENAI_BASE_URL": "https://proxy.example/v1",
        }
        config_dict, _ = self._build_with_env(env)
        llm_cfg = config_dict["llm"]["config"]
        assert config_dict["llm"]["provider"] == "openai"
        assert llm_cfg["api_key"] == "sk-openai-test"
        assert llm_cfg["openai_base_url"] == "https://proxy.example/v1"
        assert llm_cfg["model"] == "gpt-4o"

    # --- Conditional provider registration ---

    def test_providers_info_includes_anthropic(self):
        """providers_info includes Anthropic when LLM provider is anthropic."""
        _, providers_info = self._build_with_env({})
        provider_names = [pi["name"] for pi in providers_info]
        assert "anthropic" in provider_names
        assert "ollama" in provider_names  # Always included

    def test_providers_info_ollama_only(self):
        """providers_info includes only Ollama when LLM provider is ollama."""
        env = {"MEM0_LLM_PROVIDER": "ollama"}
        _, providers_info = self._build_with_env(env)
        provider_names = [pi["name"] for pi in providers_info]
        assert "ollama" in provider_names
        assert "anthropic" not in provider_names

    # --- Qdrant timeout ---

    def test_qdrant_timeout_creates_preconfigured_client(self):
        """MEM0_QDRANT_TIMEOUT creates a pre-configured QdrantClient via 'client' field."""
        env = {"MEM0_QDRANT_TIMEOUT": "30"}
        config_dict, _ = self._build_with_env(env)
        vc = config_dict["vector_store"]["config"]
        # "timeout" must NOT be a direct key (QdrantConfig rejects it)
        assert "timeout" not in vc
        # A pre-configured QdrantClient should be in the "client" field
        from qdrant_client import QdrantClient
        assert isinstance(vc["client"], QdrantClient)

    def test_qdrant_timeout_absent_when_not_set(self):
        """No client or timeout key in vector_config when MEM0_QDRANT_TIMEOUT is not set."""
        config_dict, _ = self._build_with_env({})
        vc = config_dict["vector_store"]["config"]
        assert "timeout" not in vc
        assert "client" not in vc

    # --- MEM0_PROVIDER cascade ---

    def test_mem0_provider_cascades_to_llm(self):
        """MEM0_PROVIDER=ollama alone sets LLM provider to ollama."""
        env = {"MEM0_PROVIDER": "ollama"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["provider"] == "ollama"

    def test_llm_provider_overrides_mem0_provider(self):
        """MEM0_LLM_PROVIDER takes precedence over MEM0_PROVIDER."""
        env = {"MEM0_PROVIDER": "ollama", "MEM0_LLM_PROVIDER": "anthropic"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["provider"] == "anthropic"

    def test_neither_provider_set_defaults_to_anthropic(self):
        """Neither MEM0_PROVIDER nor MEM0_LLM_PROVIDER → defaults to anthropic."""
        config_dict, _ = self._build_with_env({})
        assert config_dict["llm"]["provider"] == "anthropic"

    def test_mem0_provider_does_not_cascade_to_embed(self):
        """MEM0_PROVIDER does NOT cascade to embed provider (stays ollama)."""
        env = {"MEM0_PROVIDER": "anthropic"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["embedder"]["provider"] == "ollama"

    def test_invalid_mem0_provider_raises_valueerror(self):
        """Invalid MEM0_PROVIDER raises ValueError."""
        leak_keys = [k for k in os.environ if k.startswith("MEM0_")]
        env = {"MEM0_PROVIDER": "unsupported"}
        with patch.dict("os.environ", env, clear=False) as patched_env:
            for k in leak_keys:
                if k not in env:
                    patched_env.pop(k, None)
            with patch("mem0_mcp_selfhosted.config.resolve_token", return_value="sk-test"):
                from mem0_mcp_selfhosted.config import build_config
                with pytest.raises(ValueError, match="Unsupported MEM0_PROVIDER"):
                    build_config()

    def test_invalid_mem0_provider_fails_fast_with_llm_override(self):
        """Invalid MEM0_PROVIDER raises ValueError even when MEM0_LLM_PROVIDER is valid."""
        leak_keys = [k for k in os.environ if k.startswith("MEM0_")]
        env = {"MEM0_PROVIDER": "foobar", "MEM0_LLM_PROVIDER": "anthropic"}
        with patch.dict("os.environ", env, clear=False) as patched_env:
            for k in leak_keys:
                if k not in env:
                    patched_env.pop(k, None)
            with patch("mem0_mcp_selfhosted.config.resolve_token", return_value="sk-test"):
                from mem0_mcp_selfhosted.config import build_config
                with pytest.raises(ValueError, match="Unsupported MEM0_PROVIDER='foobar'"):
                    build_config()

    def test_mem0_provider_ollama_excludes_anthropic_registration(self):
        """MEM0_PROVIDER=ollama excludes Anthropic from providers_info."""
        env = {"MEM0_PROVIDER": "ollama"}
        _, providers_info = self._build_with_env(env)
        provider_names = [pi["name"] for pi in providers_info]
        assert "anthropic" not in provider_names

    # --- MEM0_OLLAMA_URL cascade ---

    def test_ollama_url_cascades_to_llm(self):
        """MEM0_OLLAMA_URL sets LLM ollama_base_url when MEM0_LLM_URL not set."""
        env = {"MEM0_LLM_PROVIDER": "ollama", "MEM0_OLLAMA_URL": "http://192.168.0.208:11434"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["ollama_base_url"] == "http://192.168.0.208:11434"

    def test_llm_url_overrides_ollama_url(self):
        """MEM0_LLM_URL takes precedence over MEM0_OLLAMA_URL for LLM."""
        env = {
            "MEM0_LLM_PROVIDER": "ollama",
            "MEM0_OLLAMA_URL": "http://192.168.0.208:11434",
            "MEM0_LLM_URL": "http://10.0.0.5:11434",
        }
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["ollama_base_url"] == "http://10.0.0.5:11434"

    def test_ollama_url_cascades_to_embed(self):
        """MEM0_OLLAMA_URL sets embed ollama_base_url when MEM0_EMBED_URL not set."""
        env = {"MEM0_OLLAMA_URL": "http://192.168.0.208:11434"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["embedder"]["config"]["ollama_base_url"] == "http://192.168.0.208:11434"

    def test_embed_url_overrides_ollama_url(self):
        """MEM0_EMBED_URL takes precedence over MEM0_OLLAMA_URL for embed."""
        env = {
            "MEM0_OLLAMA_URL": "http://192.168.0.208:11434",
            "MEM0_EMBED_URL": "http://10.0.0.5:11434",
        }
        config_dict, _ = self._build_with_env(env)
        assert config_dict["embedder"]["config"]["ollama_base_url"] == "http://10.0.0.5:11434"

    def test_ollama_url_ignored_for_anthropic_provider(self):
        """MEM0_OLLAMA_URL is ignored when LLM provider is anthropic."""
        env = {"MEM0_OLLAMA_URL": "http://192.168.0.208:11434"}
        config_dict, _ = self._build_with_env(env)
        assert "ollama_base_url" not in config_dict["llm"]["config"]

    # --- Whitespace stripping ---

    def test_url_whitespace_stripped(self):
        """Trailing whitespace in URL env vars is stripped."""
        env = {"MEM0_LLM_PROVIDER": "ollama", "MEM0_LLM_URL": "  http://gpu:11434\n"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["ollama_base_url"] == "http://gpu:11434"

    def test_ollama_url_fallback_whitespace_stripped(self):
        """MEM0_OLLAMA_URL whitespace is stripped in fallback."""
        env = {"MEM0_LLM_PROVIDER": "ollama", "MEM0_OLLAMA_URL": " http://gpu:11434 "}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["ollama_base_url"] == "http://gpu:11434"

    def test_provider_whitespace_stripped(self):
        """Trailing whitespace in provider env vars is stripped."""
        env = {"MEM0_PROVIDER": "  ollama\n"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["provider"] == "ollama"

    def test_llm_provider_whitespace_stripped(self):
        """Trailing whitespace in MEM0_LLM_PROVIDER is stripped."""
        env = {"MEM0_LLM_PROVIDER": " ollama \n"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["provider"] == "ollama"

    def test_numeric_env_whitespace_stripped(self):
        """Whitespace in numeric env vars (e.g. MEM0_LLM_MAX_TOKENS) is handled."""
        env = {"MEM0_LLM_MAX_TOKENS": " 8192 \n"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["config"]["max_tokens"] == 8192

    def test_optional_env_whitespace_stripped(self):
        """Whitespace in optional env vars (e.g. MEM0_QDRANT_API_KEY) is stripped."""
        env = {"MEM0_QDRANT_API_KEY": "  my-secret-key \n"}
        config_dict, _ = self._build_with_env(env)
        assert config_dict["vector_store"]["config"]["api_key"] == "my-secret-key"

    # --- End-to-end cascade ---

    def test_two_env_vars_configure_full_ollama_stack(self):
        """MEM0_PROVIDER + MEM0_OLLAMA_URL configure LLM and embed in one shot."""
        env = {
            "MEM0_PROVIDER": "ollama",
            "MEM0_OLLAMA_URL": "http://192.168.0.208:11434",
        }
        config_dict, _ = self._build_with_env(env)
        assert config_dict["llm"]["provider"] == "ollama"
        assert config_dict["llm"]["config"]["ollama_base_url"] == "http://192.168.0.208:11434"
        assert config_dict["embedder"]["config"]["ollama_base_url"] == "http://192.168.0.208:11434"
