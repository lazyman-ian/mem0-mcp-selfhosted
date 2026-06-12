"""Shared utilities for mem0-mcp-selfhosted.

- _mem0_call(): Error wrapper for all mem0ai calls
- safe_bulk_delete(): Iterate + individual delete (never memory.delete_all())
- get_default_user_id(): Default user_id injection
- list_entities_facet(): Qdrant Facet API entity listing with scroll fallback
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from mem0_mcp_selfhosted.env import env

logger = logging.getLogger(__name__)


def get_default_user_id() -> str:
    """Get the default user_id from MEM0_USER_ID env var."""
    return env("MEM0_USER_ID", "user")


def _mem0_call(func: Callable, *args: Any, **kwargs: Any) -> str:
    """Wrap a mem0ai call with structured error handling.

    Returns a JSON string in all cases (success or error).
    """
    try:
        result = func(*args, **kwargs)
    except Exception as exc:
        # Check if it's a MemoryError (imported lazily to avoid import issues)
        exc_type = type(exc).__name__
        is_memory_error = any(
            cls.__name__ == "MemoryError" for cls in type(exc).__mro__
        )
        if is_memory_error:
            logger.error("Mem0 call failed: %s", exc)
            return json.dumps(
                {
                    "error": str(exc),
                    "error_code": getattr(exc, "error_code", None),
                    "details": getattr(exc, "details", None),
                    "suggestion": getattr(exc, "suggestion", None),
                },
                ensure_ascii=False,
            )
        else:
            logger.error("Unexpected error: %s", exc)
            return json.dumps(
                {
                    "error": exc_type,
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
    return json.dumps(result, ensure_ascii=False)


def safe_bulk_delete(memory: Any, filters: dict[str, Any]) -> int:
    """Safely delete all memories matching filters.

    NEVER calls memory.delete_all() (which triggers vector_store.reset()).
    Instead: iterate + individual delete. memory.delete() also removes the
    memory's links from the entity store (mem0ai >= 2.0 built-in behavior).

    Returns the count of deleted memories.
    """
    # Get all memories matching the filters
    # Qdrant.list() returns raw scroll result: (records, next_page_offset)
    result = memory.vector_store.list(filters=filters)
    memories = result[0] if isinstance(result, tuple) else result

    count = 0
    for item in memories:
        # Extract memory_id from the Qdrant point
        memory_id = item.id if hasattr(item, "id") else item.get("id") if isinstance(item, dict) else str(item)
        try:
            memory.delete(memory_id)
            count += 1
        except Exception as exc:
            logger.warning("Failed to delete memory %s: %s", memory_id, exc)

    return count


def list_entities_facet(memory: Any) -> dict[str, list[dict]]:
    """List entities using Qdrant Facet API with scroll fallback.

    Primary: Facet API (Qdrant v1.12+) — server-side distinct value aggregation.
    Fallback: scroll+dedupe for older Qdrant versions.

    Returns: {"users": [{"value": ..., "count": ...}], "agents": [...], "runs": [...]}
    """
    client = memory.vector_store.client
    collection = memory.vector_store.collection_name

    result: dict[str, list[dict]] = {"users": [], "agents": [], "runs": []}
    entity_keys = {"users": "user_id", "agents": "agent_id", "runs": "run_id"}

    try:
        for result_key, payload_key in entity_keys.items():
            facet_response = client.facet(
                collection_name=collection,
                key=payload_key,
            )
            result[result_key] = [
                {"value": hit.value, "count": hit.count}
                for hit in facet_response.hits
            ]
        return result
    except Exception as exc:
        # Facet API unavailable — fall back to scroll+dedupe
        logger.warning(
            "Qdrant Facet API unavailable (%s). Falling back to scroll+dedupe. "
            "Upgrade to Qdrant v1.12+ for better performance.",
            exc,
        )
        return _list_entities_scroll_fallback(memory)


def _list_entities_scroll_fallback(memory: Any) -> dict[str, list[dict]]:
    """Fallback entity listing via scroll+dedupe."""
    entities: dict[str, dict[str, int]] = {
        "user_id": {},
        "agent_id": {},
        "run_id": {},
    }

    # Scroll through all memories in batches
    # Qdrant.list() returns raw scroll result: (records, next_page_offset)
    result = memory.vector_store.list(filters={}, top_k=500)
    all_memories = result[0] if isinstance(result, tuple) else result
    for item in all_memories:
        payload = item.payload if hasattr(item, "payload") else item
        if isinstance(payload, dict):
            for key in entities:
                val = payload.get(key)
                if val:
                    entities[key][val] = entities[key].get(val, 0) + 1

    return {
        "users": [{"value": v, "count": c} for v, c in entities["user_id"].items()],
        "agents": [{"value": v, "count": c} for v, c in entities["agent_id"].items()],
        "runs": [{"value": v, "count": c} for v, c in entities["run_id"].items()],
    }
