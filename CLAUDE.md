# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## MCP Servers

- **mem0**: Persistent memory across sessions. At the start of each session, `search_memories` for relevant context before asking the user to re-explain anything. Use `add_memory` whenever you discover project architecture, coding conventions, debugging insights, key decisions, or user preferences. Use `update_memory` when prior context changes. Save information like: "This project uses PostgreSQL with Prisma", "Tests run with pytest -v", "Auth uses JWT validated in middleware". When in doubt, save it — future sessions benefit from over-remembering.

## Build & Test Commands

```bash
pip install -e ".[dev]"              # Install with dev dependencies
python3 -m pytest tests/unit/ -v     # Unit tests (mocked, no infra needed)
python3 -m pytest tests/contract/ -v # Contract tests (validates mem0ai internals)
python3 -m pytest tests/integration/ -v  # Integration tests (requires live Qdrant + Ollama)
python3 -m pytest tests/ -v          # All tests
python3 -m pytest tests/ -m "not integration" -v  # Skip integration
python3 -m pytest tests/unit/test_auth.py::TestIsOatToken -v  # Single test class
python3 -m pytest tests/unit/test_auth.py::TestIsOatToken::test_oat_token_detected -v  # Single test
```

## Architecture

Self-hosted MCP server using `mem0ai >= 2.0` as a library. 11 tools (9 memory + 2 legacy graph), FastMCP orchestrator.

**Module roles:**
- `server.py` — FastMCP orchestrator, registers all tools + `memory_assistant` prompt; translates tool params to the 2.x `filters`/`top_k` signatures
- `config.py` — Env vars → mem0ai `MemoryConfig` dict (anthropic/ollama/openai LLM providers); logs deprecation warnings for graph-era env vars
- `auth.py` — 3-tier token fallback: `MEM0_ANTHROPIC_TOKEN` → `~/.claude/.credentials.json` → `ANTHROPIC_API_KEY`
- `llm_anthropic.py` — Custom Anthropic provider registered with mem0ai's `LlmFactory`; handles OAT headers, structured outputs (JSON schema via `output_config`), and tool-call parsing
- `helpers.py` — `_mem0_call()` error wrapper, `safe_bulk_delete()` iterates+deletes individually (never calls `memory.delete_all()`), `list_entities_facet()` Qdrant Facet API listing
- `graph_tools.py` — Legacy read-only Neo4j Cypher queries with lazy driver init (mem0ai 2.x never writes graph data; built-in entity linking replaced graph memory)
- `__init__.py` — Suppresses mem0ai telemetry before any imports

**Critical implementation details:**
- mem0ai 2.x has no graph memory: no `Memory.graph`, no `graph_store` config, no `enable_graph` flag. Entity linking is built-in — `add()` extracts entities into a `{collection}_entities` Qdrant collection automatically, and `delete()` cleans the entity store
- `Memory.search()`/`get_all()` take entity ids inside `filters` (`filters={"user_id": ...}`) and `top_k` (not `limit`); top-level entity kwargs raise. Upstream defaults: top_k=20, threshold=0.1, rerank=False
- The 2.x `add()` pipeline makes one JSON-mode LLM call (additive extraction, system+user messages) expecting `{"memory": [...]}` — `ADDITIVE_EXTRACTION_SCHEMA` in `llm_anthropic.py` mirrors that contract
- Contract tests (`tests/contract/`) validate mem0ai internal API assumptions — if these fail after a mem0ai upgrade, the code needs updating
- `Memory.update()` uses `data=` parameter, not `text=`
- Structured output support requires claude-opus-4/sonnet-4/haiku-4 models; older models fall back to JSON extraction
- `custom_fact_extraction_prompt` was renamed upstream to `custom_instructions`; `custom_update_memory_prompt` no longer exists
