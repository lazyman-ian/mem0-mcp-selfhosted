# Changelog

All notable changes to mem0-mcp-selfhosted are documented here.

## [0.1.0] - 2026-02-27

First public release. Self-hosted mem0 MCP server for Claude Code with 11 tools, dual LLM provider support, and knowledge graph integration.

### New Features

- **11 MCP tools** — 9 memory tools (`add_memory`, `search_memories`, `get_memories`, `get_memory`, `update_memory`, `delete_memory`, `delete_all_memories`, `list_entities`, `delete_entities`) + 2 graph tools (`search_graph`, `get_entity`) + `memory_assistant` prompt
- **Dual LLM providers** — Anthropic (Claude) and Ollama as configurable main LLM for fact extraction and memory updates. Set `MEM0_PROVIDER=ollama` for a fully local setup with no cloud dependencies
- **Knowledge graph** — Neo4j-backed entity and relationship extraction via `enable_graph` toggle. Supports 5 graph LLM providers: `anthropic`, `ollama`, `gemini`, `gemini_split`, and `anthropic_oat`
- **Split-model graph pipeline** — `gemini_split` routes entity extraction to Gemini and contradiction detection to Claude, combining Gemini's extraction quality with Claude's reasoning
- **Zero-config Anthropic auth** — Automatically reads Claude Code's OAT token from `~/.claude/.credentials.json`. No API key needed for Claude Code users
- **OAT token self-refresh** — Proactive pre-expiry refresh + 3-step defensive retry (piggyback on credentials file, self-refresh via OAuth, wait-and-retry). Long-running sessions survive token rotation seamlessly
- **`MEM0_PROVIDER` cascade** — Single env var configures both main LLM and graph LLM providers. `MEM0_OLLAMA_URL` cascades to all Ollama-backed services. Per-service overrides still work
- **Structured outputs** — Claude Opus/Sonnet/Haiku 4.x models use native JSON schema via `output_config` for reliable fact extraction
- **Ollama defense-in-depth** — 6 layers for reliable structured output from Ollama: `/no_think` injection, deterministic params, think-tag stripping, JSON extraction, and retry on empty responses
- **Per-call graph toggle** — `enable_graph` parameter on `add_memory` and `search_memories` with thread-safe locking
- **Wildcard graph search** — Pass `*` to `search_graph` to list all entities
- **Qdrant Facet API** — `list_entities` uses server-side aggregation (Qdrant v1.12+) with scroll+dedupe fallback for older versions
- **Safe bulk delete** — Never calls `memory.delete_all()`. Iterates and deletes individually with explicit graph cleanup

### Bug Fixes

- Fix `anthropic_oat` provider not registered in `LlmFactory`, preventing explicit use
- Fix `is_oat_token(None)` crash in proactive refresh when no Anthropic token configured
- Fix `response.content[0]` IndexError when Anthropic API returns empty content
- Fix thread-safety race condition in `safe_bulk_delete` reading mutable `enable_graph` state
- Fix contradiction model defaulting to Ollama model name when sent to Anthropic API
- Fix Anthropic provider not registered for `gemini_split` contradiction LLM
- Fix `MEM0_QDRANT_TIMEOUT` rejected by Pydantic — use pre-configured `QdrantClient` instead
- Fix Gemini `_parse_response` signature mismatch after upstream `tools` parameter addition
- Fix Neo4j `CypherSyntaxError` on LLM-generated relationship names with hyphens or leading digits

### Infrastructure

- **301 tests** — Unit, contract, integration, MCP protocol, and concurrency test suites
- **Centralized env helpers** — `env()`, `opt_env()`, `bool_env()` with consistent whitespace stripping across all modules
- **Telemetry suppression** — mem0ai PostHog telemetry disabled before any imports
- **Relationship sanitizer** — Monkey-patches mem0ai's sanitizer at startup for Neo4j identifier compliance
- **Gemini null content guard** — Patches `GeminiLLM._parse_response` to handle `content=None` responses
- **Transient retry** — Anthropic API 500/502/503/529 errors retried with exponential backoff
