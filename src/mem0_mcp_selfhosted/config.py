"""Environment-driven configuration for mem0-mcp-selfhosted.

Reads all config from env vars with sensible defaults, constructs a
mem0ai MemoryConfig dict, and returns provider registration info.

Graph memory was removed from mem0ai OSS in 2.0 (no ``graph_store`` config,
no Neo4j writes). Its replacement is mem0ai's built-in entity linking: every
``add()`` extracts entities into a parallel ``{collection}_entities`` Qdrant
collection automatically. The MEM0_ENABLE_GRAPH / MEM0_GRAPH_* env vars are
therefore deprecated — they are still parsed here only to emit a warning so
existing deployments notice instead of silently losing behavior.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from mem0_mcp_selfhosted.auth import resolve_token
from mem0_mcp_selfhosted.env import bool_env, env, opt_env

logger = logging.getLogger(__name__)

# Graph-era env vars that no longer have any effect (mem0ai >= 2.0).
# MEM0_NEO4J_* joined the list when the legacy read-only graph tools
# (mcp_search_graph/mcp_get_entity) and graph_tools.py were removed —
# nothing reads a Neo4j connection anymore.
_DEPRECATED_GRAPH_ENV_VARS = (
    "MEM0_ENABLE_GRAPH",
    "MEM0_GRAPH_LLM_PROVIDER",
    "MEM0_GRAPH_LLM_MODEL",
    "MEM0_GRAPH_LLM_URL",
    "MEM0_GRAPH_THRESHOLD",
    "MEM0_GRAPH_CONTRADICTION_LLM_PROVIDER",
    "MEM0_GRAPH_CONTRADICTION_LLM_MODEL",
    "MEM0_NEO4J_BASE_LABEL",
    "MEM0_NEO4J_URL",
    "MEM0_NEO4J_USER",
    "MEM0_NEO4J_PASSWORD",
    "MEM0_NEO4J_DATABASE",
)


class ProviderInfo(TypedDict):
    """Custom LLM provider registration info for LlmFactory."""

    name: str
    class_path: str


def _resolve_ollama_url(*env_keys: str) -> str:
    """Resolve the Ollama base URL from a priority chain of env vars.

    Checks each key in *env_keys* first, then falls back to
    ``MEM0_OLLAMA_URL``, then ``"http://localhost:11434"``.
    """
    for key in env_keys:
        val = env(key)
        if val:
            return val
    return env("MEM0_OLLAMA_URL") or "http://localhost:11434"


def _warn_deprecated_graph_env() -> None:
    """Log a deprecation warning for any graph-era env vars still set.

    Graph writes no longer exist in mem0ai 2.x; entity linking replaces them.
    """
    stale = [key for key in _DEPRECATED_GRAPH_ENV_VARS if opt_env(key) is not None]
    if stale:
        logger.warning(
            "Deprecated graph env vars are set but have no effect with "
            "mem0ai >= 2.0 (graph memory was removed from OSS; built-in "
            "entity linking replaces it): %s. Remove them from your "
            "environment.",
            ", ".join(stale),
        )


def build_config() -> tuple[dict[str, Any], list[ProviderInfo]]:
    """Build mem0ai MemoryConfig dict and provider registration info.

    Returns:
        (config_dict, providers_info) where providers_info is a list of
        ProviderInfo dicts (name + class_path) for LlmFactory registration.
    """
    token = resolve_token()

    _warn_deprecated_graph_env()

    # --- Top-level provider default (cascades to LLM) ---
    _provider_default = env("MEM0_PROVIDER", "anthropic")
    _supported_llm_providers = ("anthropic", "ollama", "openai")
    if _provider_default not in _supported_llm_providers:
        raise ValueError(
            f"Unsupported MEM0_PROVIDER={_provider_default!r}. "
            f"Supported: {list(_supported_llm_providers)}"
        )

    # --- LLM ---
    llm_provider = env("MEM0_LLM_PROVIDER", _provider_default)
    if llm_provider not in _supported_llm_providers:
        raise ValueError(
            f"Unsupported MEM0_LLM_PROVIDER={llm_provider!r}. "
            f"Supported: {list(_supported_llm_providers)}"
        )

    _llm_model_defaults = {"anthropic": "claude-opus-4-6", "ollama": "qwen3:14b", "openai": "gpt-4o"}
    llm_model = env("MEM0_LLM_MODEL", _llm_model_defaults[llm_provider])
    llm_max_tokens = int(env("MEM0_LLM_MAX_TOKENS", "16384"))

    llm_config: dict[str, Any] = {"model": llm_model}
    if llm_provider == "anthropic":
        llm_config["max_tokens"] = llm_max_tokens
        if token:
            llm_config["api_key"] = token
    elif llm_provider == "ollama":
        llm_config["ollama_base_url"] = _resolve_ollama_url("MEM0_LLM_URL")
    elif llm_provider == "openai":
        openai_api_key = opt_env("MEM0_OPENAI_API_KEY") or opt_env("OPENAI_API_KEY")
        openai_base_url = opt_env("MEM0_OPENAI_BASE_URL") or opt_env("OPENAI_BASE_URL")
        if openai_api_key:
            llm_config["api_key"] = openai_api_key
        if openai_base_url:
            llm_config["openai_base_url"] = openai_base_url

    # --- Embedder ---
    embed_provider = env("MEM0_EMBED_PROVIDER", "ollama")
    embed_model = env("MEM0_EMBED_MODEL", "bge-m3")
    embed_url = _resolve_ollama_url("MEM0_EMBED_URL")
    embed_dims = int(env("MEM0_EMBED_DIMS", "1024"))

    embedder_config: dict[str, Any] = {
        "model": embed_model,
    }
    if embed_provider == "ollama":
        embedder_config["ollama_base_url"] = embed_url

    # --- Vector Store ---
    qdrant_url = env("MEM0_QDRANT_URL", "http://localhost:6333")
    collection = env("MEM0_COLLECTION", "mem0_mcp_selfhosted")
    qdrant_api_key = opt_env("MEM0_QDRANT_API_KEY")
    qdrant_on_disk = bool_env("MEM0_QDRANT_ON_DISK")

    vector_config: dict[str, Any] = {
        "collection_name": collection,
        "url": qdrant_url,
        "embedding_model_dims": embed_dims,
    }
    if qdrant_api_key:
        vector_config["api_key"] = qdrant_api_key
    if qdrant_on_disk:
        vector_config["on_disk"] = True
    qdrant_timeout = opt_env("MEM0_QDRANT_TIMEOUT")
    if qdrant_timeout:
        # QdrantConfig's Pydantic model does not accept "timeout" directly.
        # Create a pre-configured QdrantClient with the timeout and pass it
        # via the "client" field, which mem0ai uses as-is.
        from qdrant_client import QdrantClient

        client_kwargs: dict[str, Any] = {
            "url": qdrant_url,
            "timeout": int(qdrant_timeout),
        }
        if qdrant_api_key:
            client_kwargs["api_key"] = qdrant_api_key
        vector_config["client"] = QdrantClient(**client_kwargs)

    # --- History ---
    history_db_path = opt_env("MEM0_HISTORY_DB_PATH")

    # --- Build config dict ---
    config_dict: dict[str, Any] = {
        "llm": {
            "provider": llm_provider,
            "config": llm_config,
        },
        "embedder": {
            "provider": embed_provider,  # Explicit — never rely on mem0ai's openai default
            "config": embedder_config,
        },
        "vector_store": {
            "provider": "qdrant",
            "config": vector_config,
        },
        "version": "v1.1",
    }

    if history_db_path:
        config_dict["history_db_path"] = history_db_path

    # --- Provider registration info ---
    # Always register custom Ollama provider — strict superset of upstream
    # OllamaLLM (restores tool-calling removed in mem0ai PR #3241).
    # Registering even when not used has no side effects.
    providers_info: list[ProviderInfo] = [
        {
            "name": "ollama",
            "class_path": "mem0_mcp_selfhosted.llm_ollama.OllamaToolLLM",
        },
    ]
    if llm_provider == "anthropic":
        providers_info.append({
            "name": "anthropic",
            "class_path": "mem0_mcp_selfhosted.llm_anthropic.AnthropicOATLLM",
        })

    return config_dict, providers_info
