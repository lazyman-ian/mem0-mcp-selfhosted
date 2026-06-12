"""Tests for helpers.py — error wrapper, bulk delete, user_id, entity listing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from mem0_mcp_selfhosted.helpers import (
    _mem0_call,
    get_default_user_id,
    list_entities_facet,
    safe_bulk_delete,
)


class TestMem0Call:
    def test_success_returns_json(self):
        result = _mem0_call(lambda: {"status": "ok"})
        parsed = json.loads(result)
        assert parsed == {"status": "ok"}

    def test_memory_error_caught(self):
        """MemoryError subclass returns structured error JSON."""
        # Create a mock MemoryError-like exception
        class FakeMemoryError(Exception):
            pass

        FakeMemoryError.__name__ = "MemoryError"

        exc = FakeMemoryError("something failed")
        exc.error_code = "VALIDATION_ERROR"
        exc.details = "missing field"
        exc.suggestion = "add user_id"

        # Patch the MRO check
        def _raise():
            raise exc

        result = _mem0_call(_raise)
        parsed = json.loads(result)
        assert "error" in parsed

    def test_generic_exception_caught(self):
        """Generic Exception returns type name and detail."""
        def _raise():
            raise ValueError("bad input")

        result = _mem0_call(_raise)
        parsed = json.loads(result)
        assert parsed["error"] == "ValueError"
        assert parsed["detail"] == "bad input"

    def test_ensure_ascii_false(self):
        """Non-ASCII characters preserved in output."""
        result = _mem0_call(lambda: {"text": "Alice prefiere TypeScript"})
        assert "prefiere" in result


class TestSafeBulkDelete:
    def test_iterates_and_deletes(self):
        memory = MagicMock()

        # Mock vector_store.list returning items with .id
        item1 = MagicMock()
        item1.id = "id-1"
        item2 = MagicMock()
        item2.id = "id-2"
        memory.vector_store.list.return_value = [item1, item2]

        count = safe_bulk_delete(memory, {"user_id": "testuser"})

        assert count == 2
        assert memory.delete.call_count == 2
        memory.delete.assert_any_call("id-1")
        memory.delete.assert_any_call("id-2")

    def test_handles_tuple_scroll_result(self):
        """Qdrant.list() returns (records, next_page_offset) — first element used."""
        memory = MagicMock()
        item = MagicMock()
        item.id = "id-1"
        memory.vector_store.list.return_value = ([item], None)

        count = safe_bulk_delete(memory, {"user_id": "testuser"})

        assert count == 1
        memory.delete.assert_called_once_with("id-1")

    def test_continues_after_individual_delete_failure(self):
        """A failing delete is logged and skipped; remaining items still deleted."""
        memory = MagicMock()
        item1 = MagicMock()
        item1.id = "id-1"
        item2 = MagicMock()
        item2.id = "id-2"
        memory.vector_store.list.return_value = [item1, item2]
        memory.delete.side_effect = [RuntimeError("boom"), None]

        count = safe_bulk_delete(memory, {"user_id": "testuser"})

        assert count == 1
        assert memory.delete.call_count == 2

    def test_never_calls_delete_all(self):
        """safe_bulk_delete must never use memory.delete_all() (vector reset)."""
        memory = MagicMock()
        memory.vector_store.list.return_value = []

        safe_bulk_delete(memory, {"user_id": "testuser"})

        memory.delete_all.assert_not_called()


class TestGetDefaultUserId:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("MEM0_USER_ID", raising=False)
        assert get_default_user_id() == "user"

    def test_custom(self, monkeypatch):
        monkeypatch.setenv("MEM0_USER_ID", "bob")
        assert get_default_user_id() == "bob"


class TestListEntitiesScrollFallback:
    def test_fallback_uses_top_k_param(self):
        """When Facet API fails, the scroll fallback must pass top_k
        (the 2.x Qdrant.list keyword), not the removed 'limit'."""
        memory = MagicMock()
        memory.vector_store.client.facet.side_effect = RuntimeError("no facet API")
        item = MagicMock()
        item.payload = {"user_id": "alice"}
        memory.vector_store.list.return_value = ([item], None)

        result = list_entities_facet(memory)

        memory.vector_store.list.assert_called_once_with(filters={}, top_k=500)
        assert result["users"] == [{"value": "alice", "count": 1}]
