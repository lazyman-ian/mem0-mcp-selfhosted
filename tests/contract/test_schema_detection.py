"""Contract test: additive extraction call shape (mem0ai >= 2.0).

mem0ai 2.x makes a single JSON-mode LLM call per add(): the additive
extraction prompt (system + user messages, response_format json_object)
whose response is parsed as ``{"memory": [...]}``. Our AnthropicOATLLM
forces this shape via structured outputs (ADDITIVE_EXTRACTION_SCHEMA), so
if mem0ai changes the call structure or the expected response key, the
schema must be updated.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.contract


class TestAdditiveExtractionContract:
    def test_additive_extraction_prompt_exists(self):
        """mem0ai exposes the additive extraction prompt pair we rely on."""
        try:
            from mem0.configs.prompts import (
                ADDITIVE_EXTRACTION_PROMPT,
                generate_additive_extraction_prompt,
            )
        except ImportError:
            pytest.skip("mem0ai not installed")

        assert ADDITIVE_EXTRACTION_PROMPT.strip()
        assert callable(generate_additive_extraction_prompt)

    def test_extraction_call_uses_system_plus_user_json_mode(self):
        """The add() pipeline sends system+user messages with json_object format.

        Our structured-output path applies ADDITIVE_EXTRACTION_SCHEMA whenever
        response_format is set — valid only while this is the sole JSON-mode
        call in the pipeline.
        """
        try:
            from mem0.memory.main import Memory
        except ImportError:
            pytest.skip("mem0ai not installed")

        source = inspect.getsource(Memory._add_to_vector_store)
        assert '"role": "system", "content": system_prompt' in source, (
            "INVARIANT BROKEN: extraction call no longer sends a system message."
        )
        assert '"type": "json_object"' in source, (
            "INVARIANT BROKEN: extraction call no longer uses json_object response_format."
        )

    def test_extraction_response_parsed_via_memory_key(self):
        """mem0ai parses the extraction response with .get("memory", [...])."""
        try:
            from mem0.memory.main import Memory
        except ImportError:
            pytest.skip("mem0ai not installed")

        source = inspect.getsource(Memory._add_to_vector_store)
        assert '.get("memory", [])' in source, (
            "INVARIANT BROKEN: extraction response is no longer parsed via the "
            "'memory' key — update ADDITIVE_EXTRACTION_SCHEMA in llm_anthropic.py."
        )

    def test_prompt_output_format_matches_schema_fields(self):
        """The prompt's documented output fields match our schema fields."""
        try:
            from mem0.configs.prompts import ADDITIVE_EXTRACTION_PROMPT
        except ImportError:
            pytest.skip("mem0ai not installed")

        from mem0_mcp_selfhosted.llm_anthropic import ADDITIVE_EXTRACTION_SCHEMA

        item_props = set(
            ADDITIVE_EXTRACTION_SCHEMA["properties"]["memory"]["items"]["properties"]
        )
        for field in item_props:
            assert field in ADDITIVE_EXTRACTION_PROMPT, (
                f"Schema field {field!r} not mentioned in ADDITIVE_EXTRACTION_PROMPT — "
                "schema may be out of sync with the upstream prompt."
            )
