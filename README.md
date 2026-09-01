# mem0-mcp-selfhosted

<a href="https://glama.ai/mcp/servers/elvismdev/mem0-mcp-selfhosted"><img width="380" height="200" src="https://glama.ai/mcp/servers/elvismdev/mem0-mcp-selfhosted/badge?v=1" alt="mem0-mcp-selfhosted MCP server" /></a>

Self-hosted [mem0](https://github.com/mem0ai/mem0) MCP server for Claude Code. Run a complete memory server against self-hosted Qdrant + Ollama, with your choice of Anthropic (Claude) or Ollama as the main LLM. Requires `mem0ai >= 2.0`.

Uses the `mem0ai` package directly as a library, supports both Claude's OAT token and fully local Ollama setups, and exposes 11 MCP tools for full memory management.

## Prerequisites

| Service | Required | Purpose |
|---------|----------|---------|
| **Qdrant** | Yes | Vector memory storage and search |
| **Ollama** | Yes | Embedding generation (`bge-m3`) and optionally local LLM |

Python >= 3.10 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

> **Authentication:** The default setup uses Claude (Anthropic) as the LLM for fact extraction. No API key needed, the server automatically uses your Claude Code session token. For fully local setups, set `MEM0_PROVIDER=ollama`. See [Authentication](#authentication) for advanced options.

## Quick Start

### Default (Anthropic)

Add the MCP server globally (available across all projects):

```bash
claude mcp add --scope user --transport stdio mem0 \
  --env MEM0_USER_ID=your-user-id \
  -- uvx --from git+https://github.com/elvismdev/mem0-mcp-selfhosted.git mem0-mcp-selfhosted
```

All defaults work out of the box: Qdrant on `localhost:6333`, Ollama embeddings on `localhost:11434` with `bge-m3` (1024 dims). Override any default via `--env` (see [Configuration](#configuration)).

`uvx` automatically downloads, installs, and runs the server in an isolated environment, no manual installation needed. Claude Code launches it on demand when the MCP connection starts.

The server auto-reads your OAT token from `~/.claude/.credentials.json`, no manual token configuration needed.

### Fully Local (Ollama)

For a fully local setup with no cloud dependencies, use Ollama for both the main LLM and embeddings:

```bash
claude mcp add --scope user --transport stdio mem0 \
  --env MEM0_PROVIDER=ollama \
  --env MEM0_LLM_MODEL=qwen3:14b \
  --env MEM0_USER_ID=your-user-id \
  -- uvx --from git+https://github.com/elvismdev/mem0-mcp-selfhosted.git mem0-mcp-selfhosted
```

`MEM0_PROVIDER=ollama` switches the main LLM to Ollama. Same infrastructure defaults apply (Qdrant on `localhost:6333`, `bge-m3` embeddings). Per-service overrides (e.g. `MEM0_LLM_URL`, `MEM0_EMBED_URL`) still work when needed.

Or add it to a single project by creating `.mcp.json` in the project root:

```json
{
  "mcpServers": {
    "mem0": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/elvismdev/mem0-mcp-selfhosted.git", "mem0-mcp-selfhosted"],
      "env": {
        "MEM0_PROVIDER": "ollama",
        "MEM0_LLM_MODEL": "qwen3:14b",
        "MEM0_USER_ID": "your-user-id"
      }
    }
  }
}
```

### Try It

Restart Claude Code, then:

```
> Search my memories for TypeScript preferences
> Remember that I prefer Hatch for Python packaging
> List which users have stored memories
```

## CLAUDE.md Integration

Add these rules to your project's `CLAUDE.md` (or `~/.claude/CLAUDE.md` for global use) so Claude Code proactively uses memory tools throughout the session:

```markdown
# MCP Servers

- **mem0**: Persistent memory across sessions. At the start of each session, `search_memories` for relevant context before asking the user to re-explain anything. Use `add_memory` whenever you discover project architecture, coding conventions, debugging insights, key decisions, or user preferences. Use `update_memory` when prior context changes. Save information like: "This project uses PostgreSQL with Prisma", "Tests run with pytest -v", "Auth uses JWT validated in middleware". When in doubt, save it, future sessions benefit from over-remembering.
```

This gives Claude Code behavioral instructions to actively search and save memories during the session. For best results, combine with [Claude Code Hooks](#claude-code-hooks), the CLAUDE.md rules tell Claude *how to use* memory tools mid-session, while hooks handle the *automatic* injection and saving at session boundaries.

## Claude Code Hooks

Session hooks automate memory at session boundaries, injecting memories on startup and saving summaries on exit. This happens automatically without manual tool calls.

| Hook | Event | What it does |
|------|-------|--------------|
| `mem0-hook-context` | SessionStart (`startup`, `compact`) | Searches mem0 for project-relevant memories and injects them as `additionalContext` |
| `mem0-hook-stop` | Stop | Reads the last ~3 user/assistant exchanges from the transcript and saves a summary to mem0 via `infer=True` |

Both hooks are non-fatal, if mem0 is unreachable or any error occurs, Claude Code continues normally.

### Install

Install hooks into your project:

```bash
mem0-install-hooks
```

Or install globally (all projects):

```bash
mem0-install-hooks --global
```

This adds the hook entries to `.claude/settings.json`. The installer is idempotent, running it twice won't create duplicates.

### How it works

**On session start**, the context hook searches mem0 with two queries (project architecture + recent session summaries), deduplicates by memory ID, and formats the results as numbered lines under a `# mem0 Cross-Session Memory` header. These are injected via the hook's `additionalContext` response field.

**On session stop**, the stop hook reads the JSONL transcript, extracts the last 6 user/assistant messages (a sliding window via bounded deque), builds a summary prompt, and calls `memory.add(infer=True)` to extract atomic facts.

### Entry points

| Command | Function | Registered in `pyproject.toml` |
|---------|----------|-------------------------------|
| `mem0-hook-context` | `hooks:context_main` | SessionStart hook |
| `mem0-hook-stop` | `hooks:stop_main` | Stop hook |
| `mem0-install-hooks` | `hooks:install_main` | CLI installer |

### Hooks + CLAUDE.md

Hooks and CLAUDE.md are complementary layers that work best together:

| Layer | Role | When |
|-------|------|------|
| **Hooks** | Automated data flow, injects stored memories on startup, saves session summaries on exit | Session boundaries (start/stop) |
| **CLAUDE.md** | Behavioral instructions, tells Claude to actively search and save memories during the session | Throughout the session |

Hooks alone give you passive recall (memories appear at startup) and passive saving (summaries saved at exit). CLAUDE.md instructions add active mid-session behavior, Claude searches for relevant memories when encountering new topics, and saves important discoveries immediately rather than waiting for session end.

For the best experience, use both. Hooks ensure memories flow in and out automatically at session boundaries, while CLAUDE.md ensures Claude actively engages with memory tools during the session.

## Authentication

The server resolves an Anthropic token using a prioritized fallback chain:

| Priority | Source | Details |
|----------|--------|---------|
| 1 | `MEM0_ANTHROPIC_TOKEN` env var | Explicit, user-controlled |
| 2 | `~/.claude/.credentials.json` | Auto-reads Claude Code's OAT token (zero-config) |
| 3 | `ANTHROPIC_API_KEY` env var | Standard pay-per-use API key |
| 4 | Disabled | Warns and disables Anthropic LLM features |

**In Claude Code, priority 2 always wins**, the credentials file exists as long as you're logged in. This means `ANTHROPIC_API_KEY` (priority 3) is never reached. To override the OAT token in Claude Code, use `MEM0_ANTHROPIC_TOKEN` (priority 1). `ANTHROPIC_API_KEY` is only useful for non-Claude-Code deployments (Docker, CI, standalone).

**OAT tokens** (`sk-ant-oat...`) use your Claude subscription. The server automatically detects the token type and configures the SDK accordingly. OAT tokens are automatically refreshed before expiry: the server proactively checks the token lifetime and refreshes via the Anthropic OAuth endpoint when nearing expiry (default: 30 minutes). On authentication failures, a 3-step defensive strategy kicks in, piggybacking on Claude Code's credentials file, self-refreshing via OAuth, and wait-and-retry, so long-running sessions survive token rotation seamlessly.

**API keys** (`sk-ant-api...`) use standard pay-per-use billing.

## Tools

### Memory Tools (9 core)

| Tool | Description |
|------|-------------|
| `add_memory` | Store text or conversation history as memories. Supports `infer`, `metadata`. Entity linking is built-in (mem0ai >= 2.0). |
| `search_memories` | Semantic search with optional `filters`, `threshold`, `rerank`. |
| `get_memories` | List/filter memories (non-search). Supports `limit` and scope filters. |
| `get_memory` | Fetch a single memory by UUID. |
| `update_memory` | Replace memory text. Re-embeds and re-indexes in Qdrant. |
| `delete_memory` | Delete a single memory by UUID. |
| `delete_all_memories` | Bulk-delete all memories in a scope. |
| `list_entities` | List users/agents/runs with memory counts. Uses Qdrant Facet API. |
| `delete_entities` | Cascade-delete an entity and all its memories. |

### Prompt

The server registers a `memory_assistant` MCP prompt that provides Claude with a quick-start guide for using the memory tools effectively.

### Parameters

All tools use Pydantic `Annotated[type, Field(description=...)]` for self-documenting parameter schemas. Common patterns:

- **`user_id`** defaults to `MEM0_USER_ID` env var when not provided
- **`filters`** supports structured operators: `{"key": {"eq": "value"}}`, `{"AND": [...]}`
- All responses are JSON strings via `json.dumps(result, ensure_ascii=False)`

## Configuration

All configuration is via environment variables. Create a `.env` file or set them in your MCP config.

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `MEM0_ANTHROPIC_TOKEN` | -- | Anthropic OAT or API token (priority 1) |
| `ANTHROPIC_API_KEY` | -- | Standard Anthropic API key (priority 3) |
| `MEM0_OAT_HEADERS` | `auto` | OAT identity headers: `auto` or `none` |
| `MEM0_OAT_REFRESH_THRESHOLD_SECONDS` | `1800` | Seconds before expiry to trigger proactive OAT token refresh |

### LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `MEM0_PROVIDER` | `anthropic` | Top-level provider (`anthropic`, `ollama`, or `openai`). Cascades to `MEM0_LLM_PROVIDER` when not set. Does **not** affect `MEM0_EMBED_PROVIDER`. |
| `MEM0_LLM_PROVIDER` | _(MEM0_PROVIDER)_ | Main LLM provider: `anthropic`, `ollama`, or `openai`. Inherits from `MEM0_PROVIDER` when not set. |
| `MEM0_OLLAMA_URL` | `http://localhost:11434` | Shared Ollama base URL. Cascades to `MEM0_LLM_URL` and `MEM0_EMBED_URL` when those are not set. |
| `MEM0_LLM_MODEL` | _(per-provider)_ | Model for the selected LLM provider. Defaults to `claude-opus-4-6` for Anthropic, `qwen3:14b` for Ollama |
| `MEM0_LLM_URL` | _(cascades)_ | Ollama base URL for the main LLM. Cascades: `MEM0_LLM_URL` → `MEM0_OLLAMA_URL` → `http://localhost:11434`. Only used when `MEM0_LLM_PROVIDER=ollama` |
| `MEM0_LLM_MAX_TOKENS` | `16384` | Max tokens for LLM responses (Anthropic only) |
| `MEM0_OLLAMA_KEEP_ALIVE` | `30m` | How long Ollama keeps the model in VRAM between calls (e.g., `1h`, `5m`). Prevents model unload between sequential calls |
| `MEM0_OLLAMA_THINK` | `false` | Set to `true` to re-enable qwen3 thinking mode (disabled by default to prevent `<think>` + `format:"json"` collision) |

### Embedder

| Variable | Default | Description |
|----------|---------|-------------|
| `MEM0_EMBED_PROVIDER` | `ollama` | Embedding provider (`ollama` or `openai`) |
| `MEM0_EMBED_MODEL` | `bge-m3` | Embedding model name |
| `MEM0_EMBED_URL` | _(cascades)_ | Ollama URL for embeddings. Cascades: `MEM0_EMBED_URL` → `MEM0_OLLAMA_URL` → `http://localhost:11434` |
| `MEM0_EMBED_DIMS` | `1024` | Embedding vector dimensions |

### Vector Store (Qdrant)

| Variable | Default | Description |
|----------|---------|-------------|
| `MEM0_QDRANT_URL` | `http://localhost:6333` | Qdrant REST API URL |
| `MEM0_QDRANT_API_KEY` | -- | Qdrant API key (for Qdrant Cloud) |
| `MEM0_QDRANT_ON_DISK` | `false` | Store vectors on disk (reduces RAM, slower search) |
| `MEM0_QDRANT_TIMEOUT` | _(client default)_ | Qdrant REST API timeout in seconds (e.g., `30`). Only set if you hit `ReadTimeout` during collection operations |
| `MEM0_COLLECTION` | `mem0_mcp_selfhosted` | Qdrant collection name |

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MEM0_TRANSPORT` | `stdio` | Transport: `stdio`, `sse`, or `streamable-http` |
| `MEM0_HOST` | `0.0.0.0` | Host for SSE/HTTP transports |
| `MEM0_PORT` | `8081` | Port for SSE/HTTP transports |
| `MEM0_USER_ID` | `user` | Default user ID for memory scoping |
| `MEM0_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MEM0_HISTORY_DB_PATH` | -- | SQLite path for memory change history |

## Architecture

```
Claude Code
  |
  ├── MCP stdio/SSE/streamable-http
  │     |
  │     ├── env.py               ← Centralized env var readers (whitespace-safe)
  │     ├── auth.py              ← Hybrid token fallback chain + OAT self-refresh
  │     ├── llm_anthropic.py     ← Custom Anthropic LLM provider (OAT + structured outputs)
  │     ├── llm_ollama.py        ← Custom Ollama LLM provider (restored tool-calling)
  │     ├── config.py            ← Env vars → MemoryConfig dict (provider + URL cascades)
  │     ├── helpers.py           ← Error wrapper, safe bulk-delete, entity listing
  │     ├── __init__.py          ← Telemetry suppression (before any mem0 import)
  │     └── server.py            ← FastMCP orchestrator (9 tools + prompt)
  │           |
  │           ├── mem0ai Memory class (>= 2.0)
  │           │     ├── Vector: LLM additive extraction → Ollama embed → Qdrant
  │           │     └── Entity linking: spaCy extraction → {collection}_entities (Qdrant)
  │           |
  │           └── Infrastructure
  │                 ├── Qdrant          ← Vector store + entity store
  │                 ├── Ollama          ← Embeddings
  │                 └── Anthropic/Ollama ← Main LLM (configurable)
  |
  └── Session Hooks (subprocess, not MCP)
        |
        └── hooks.py             ← Cross-session memory (SessionStart + Stop hooks)
              ├── context_main()   → Injects memories as additionalContext on startup/compact
              ├── stop_main()      → Saves session summary to mem0 on exit
              └── install_main()   → CLI to patch .claude/settings.json
```

## Entity Linking (replaces graph memory)

mem0ai >= 2.0 removed graph memory from OSS and replaced it with built-in
entity linking: every `add()` extracts entities (spaCy-based, no extra LLM
calls) into a parallel Qdrant collection named `{collection}_entities`,
created automatically. Search fuses semantic similarity, BM25 keyword
matching, and entity boosting — no configuration needed and no extra
Claude quota cost.

The Neo4j graph written by earlier versions of this server is not
migrated. The legacy read-only graph tools were removed once that graph
went stale; a `neo4j-admin database dump` backup is the recovery path.

## Transport Modes

| Mode | Use Case | Config |
|------|----------|--------|
| `stdio` (default) | Claude Code integration | `MEM0_TRANSPORT=stdio` |
| `sse` | Legacy remote clients | `MEM0_TRANSPORT=sse` |
| `streamable-http` | Modern remote clients | `MEM0_TRANSPORT=streamable-http` |

For remote deployments, MCP SDK >= 1.23.0 enables DNS rebinding protection by default.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run unit tests
python3 -m pytest tests/unit/ -v

# Run contract tests (validates mem0ai internal API assumptions)
python3 -m pytest tests/contract/ -v

# Run integration tests (requires live Qdrant + Ollama)
python3 -m pytest tests/integration/ -v

# Run all tests
python3 -m pytest tests/ -v
```

### Test Structure

- **`tests/unit/`** -- Pure unit tests with mocked dependencies (env, auth, config, config matrix, MCP protocol, helpers, hooks, LLM providers, server)
- **`tests/contract/`** -- Validates assumptions about mem0ai internals (additive extraction call shape, 2.x search/get_all/update signatures, `vector_store.client` access path, `LlmFactory` registration idempotency)
- **`tests/integration/`** -- Live infrastructure tests (memory lifecycle, bulk operations, hooks) against real Qdrant + Ollama. Marked with `@pytest.mark.integration`.

Contract tests catch breaking changes in `mem0ai` upgrades before they reach production.

## Telemetry

All mem0ai telemetry is suppressed. `os.environ["MEM0_TELEMETRY"] = "false"` is set at package import time, before any `mem0` module is loaded. No PostHog events are sent.

## License

MIT
