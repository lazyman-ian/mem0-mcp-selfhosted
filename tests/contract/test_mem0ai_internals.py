"""Contract tests: mem0ai internal API stability.

These tests validate assumptions about mem0ai internals that our code depends on.
If these fail after a mem0ai upgrade, our code needs updating.

NOTE: These tests require mem0ai to be installed. They test the real package,
not mocks. Skip with `pytest -m "not contract"` if deps unavailable.
"""

from __future__ import annotations

import inspect

import pytest

# Mark all tests in this module as contract tests
pytestmark = pytest.mark.contract


class TestVectorStoreClientAccess:
    """Test that memory.vector_store.client is a public, stable attribute."""

    def test_qdrant_class_has_client_attribute(self):
        """The Qdrant vector store class exposes .client as a public attribute."""
        try:
            from mem0.vector_stores.qdrant import Qdrant
        except ImportError:
            pytest.skip("mem0ai not installed")

        # Verify 'client' is in the class (not a private _client)
        assert hasattr(Qdrant, "__init__"), "Qdrant class must have __init__"
        # Check the source to verify client is assigned (not _client)
        import inspect

        source = inspect.getsource(Qdrant.__init__)
        assert "self.client" in source, (
            "INVARIANT BROKEN: Qdrant.__init__ must assign self.client. "
            "Our code accesses memory.vector_store.client directly."
        )

    def test_qdrant_class_has_collection_name(self):
        """The Qdrant vector store class exposes .collection_name."""
        try:
            from mem0.vector_stores.qdrant import Qdrant
        except ImportError:
            pytest.skip("mem0ai not installed")

        import inspect

        source = inspect.getsource(Qdrant.__init__)
        assert "self.collection_name" in source, (
            "INVARIANT BROKEN: Qdrant.__init__ must assign self.collection_name. "
            "Our code accesses memory.vector_store.collection_name."
        )


class TestMcpSdkImports:
    """Test MCP SDK import paths remain stable."""

    def test_mcp_client_session_importable(self):
        """ClientSession import path remains valid across MCP SDK versions."""
        try:
            from mcp.client.session import ClientSession
        except ImportError:
            pytest.skip("mcp SDK not installed")

        assert ClientSession  # Import succeeded — contract satisfied


class TestLlmFactoryRegistration:
    """Test LlmFactory.register_provider() behavior."""

    def test_register_provider_exists(self):
        """LlmFactory has a register_provider classmethod."""
        try:
            from mem0.utils.factory import LlmFactory
        except ImportError:
            pytest.skip("mem0ai not installed")

        assert hasattr(LlmFactory, "register_provider"), (
            "INVARIANT BROKEN: LlmFactory must have register_provider classmethod."
        )

    def test_register_provider_is_idempotent(self):
        """Calling register_provider twice with same name doesn't error."""
        try:
            from mem0.utils.factory import LlmFactory
        except ImportError:
            pytest.skip("mem0ai not installed")

        # Register once
        LlmFactory.register_provider(
            name="test_idempotent",
            class_path="mem0_mcp_selfhosted.llm_anthropic.AnthropicOATLLM",
            config_class=None,
        )
        # Register again — should not raise
        LlmFactory.register_provider(
            name="test_idempotent",
            class_path="mem0_mcp_selfhosted.llm_anthropic.AnthropicOATLLM",
            config_class=None,
        )

    def test_registration_persists_across_calls(self):
        """Registered provider persists in factory after registration."""
        try:
            from mem0.utils.factory import LlmFactory
        except ImportError:
            pytest.skip("mem0ai not installed")

        LlmFactory.register_provider(
            name="test_persist",
            class_path="mem0_mcp_selfhosted.llm_anthropic.AnthropicOATLLM",
            config_class=None,
        )

        # Verify the provider is in the factory's registry
        # The factory uses a class-level dict, so it should persist
        provider_map = getattr(LlmFactory, "provider_to_class", None)
        if provider_map is not None:
            assert "test_persist" in provider_map, (
                "INVARIANT BROKEN: Registered provider must persist in LlmFactory."
            )


class TestMem0V2Surface:
    """Validate the mem0ai >= 2.0 API surface our code targets."""

    def test_memoryconfig_has_no_graph_store(self):
        """Graph memory was removed from OSS in 2.0 — config must not accept it."""
        try:
            from mem0.configs.base import MemoryConfig
        except ImportError:
            pytest.skip("mem0ai not installed")

        fields = set(MemoryConfig.model_fields)
        assert "graph_store" not in fields, (
            "INVARIANT BROKEN: graph_store reappeared in MemoryConfig — "
            "the graph removal assumptions in config.py no longer hold."
        )
        assert "custom_instructions" in fields
        assert "custom_fact_extraction_prompt" not in fields

    def test_graph_memory_module_removed(self):
        """mem0.memory.graph_memory must not exist (no .graph attribute on Memory)."""
        import importlib.util

        if importlib.util.find_spec("mem0") is None:
            pytest.skip("mem0ai not installed")

        assert importlib.util.find_spec("mem0.memory.graph_memory") is None, (
            "INVARIANT BROKEN: mem0.memory.graph_memory exists again."
        )

    def test_memory_has_entity_store(self):
        """Built-in entity linking exposes the entity_store property."""
        try:
            from mem0.memory.main import Memory
        except ImportError:
            pytest.skip("mem0ai not installed")

        assert isinstance(
            inspect.getattr_static(Memory, "entity_store"), property
        ), "INVARIANT BROKEN: Memory.entity_store property missing."

    def test_search_signature_uses_filters(self):
        """search() takes filters/top_k/threshold keywords, not entity kwargs."""
        try:
            from mem0.memory.main import Memory
        except ImportError:
            pytest.skip("mem0ai not installed")

        params = inspect.signature(Memory.search).parameters
        assert "filters" in params
        assert "top_k" in params and params["top_k"].default == 20
        assert "threshold" in params and params["threshold"].default == 0.1
        assert "rerank" in params and params["rerank"].default is False
        assert "user_id" not in params, (
            "INVARIANT BROKEN: search() grew a top-level user_id param again."
        )

    def test_get_all_signature_uses_filters(self):
        """get_all() takes filters/top_k keywords, not entity kwargs."""
        try:
            from mem0.memory.main import Memory
        except ImportError:
            pytest.skip("mem0ai not installed")

        params = inspect.signature(Memory.get_all).parameters
        assert "filters" in params
        assert "top_k" in params and params["top_k"].default == 20
        assert "user_id" not in params

    def test_update_uses_data_param(self):
        """update() takes the new text via the 'data' parameter."""
        try:
            from mem0.memory.main import Memory
        except ImportError:
            pytest.skip("mem0ai not installed")

        params = inspect.signature(Memory.update).parameters
        assert "data" in params, (
            "INVARIANT BROKEN: Memory.update no longer has a 'data' parameter."
        )

    def test_qdrant_list_uses_top_k(self):
        """Qdrant.list() takes top_k (helpers' scroll fallback depends on it)."""
        try:
            from mem0.vector_stores.qdrant import Qdrant
        except ImportError:
            pytest.skip("mem0ai not installed")

        params = inspect.signature(Qdrant.list).parameters
        assert "top_k" in params
        assert "filters" in params


class TestOllamaLLMInterface:
    """Validate upstream OllamaLLM interface our subclass depends on."""

    def test_ollama_llm_has_parse_response(self):
        """OllamaLLM has _parse_response method we override."""
        try:
            from mem0.llms.ollama import OllamaLLM
        except ImportError:
            pytest.skip("mem0ai not installed")

        assert hasattr(OllamaLLM, "_parse_response"), (
            "INVARIANT BROKEN: OllamaLLM must have _parse_response method. "
            "Our OllamaToolLLM subclass overrides it."
        )

    def test_ollama_llm_has_generate_response(self):
        """OllamaLLM has generate_response method we override."""
        try:
            from mem0.llms.ollama import OllamaLLM
        except ImportError:
            pytest.skip("mem0ai not installed")

        assert hasattr(OllamaLLM, "generate_response"), (
            "INVARIANT BROKEN: OllamaLLM must have generate_response method. "
            "Our OllamaToolLLM subclass overrides it."
        )

    def test_ollama_config_has_base_url(self):
        """OllamaConfig accepts ollama_base_url parameter."""
        try:
            from mem0.configs.llms.ollama import OllamaConfig
        except ImportError:
            pytest.skip("mem0ai not installed")

        # Verify __init__ accepts ollama_base_url and stores it
        cfg = OllamaConfig(ollama_base_url="http://test:11434")
        assert cfg.ollama_base_url == "http://test:11434", (
            "INVARIANT BROKEN: OllamaConfig must accept and store ollama_base_url. "
            "Our config.py passes this field to Ollama LLM config."
        )

    def test_ollama_llm_init_accepts_config(self):
        """OllamaLLM.__init__ accepts a 'config' parameter by name."""
        try:
            from mem0.llms.ollama import OllamaLLM
        except ImportError:
            pytest.skip("mem0ai not installed")

        import inspect

        sig = inspect.signature(OllamaLLM.__init__)
        params = list(sig.parameters.keys())
        assert "config" in params, (
            "INVARIANT BROKEN: OllamaLLM.__init__ must accept a 'config' parameter. "
            f"Our OllamaToolLLM inherits __init__ from it. Found params: {params}"
        )
