"""Contract tests: entity linking must be functional, not silently disabled.

Entity linking is mem0ai 2.x's replacement for graph memory. Its extraction
path (mem0.utils.entity_extraction.extract_entities) returns [] when spaCy is
missing — a silent no-op, no error. That means a dependency regression (e.g.
dropping the mem0ai 'nlp' extra) would pass every other test while quietly
disabling the feature. These tests pin the dependency and the behavior.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


class TestEntityLinkingDependencies:
    def test_spacy_importable(self):
        """spaCy must be installed (via mem0ai[nlp]) or entity linking no-ops."""
        try:
            import spacy  # noqa: F401
        except ImportError:
            pytest.fail(
                "INVARIANT BROKEN: spaCy is not installed. Entity linking — "
                "the mem0ai 2.x replacement for graph memory — silently "
                "returns no entities without it. Ensure pyproject depends on "
                "mem0ai[llms,nlp]."
            )

    def test_extract_entities_returns_results(self):
        """extract_entities must yield entities for unambiguous proper nouns.

        Downloads en_core_web_sm on first run if missing (handled by
        mem0.utils.spacy_models); subsequent runs use the cached model.
        """
        from mem0.utils.entity_extraction import extract_entities

        entities = extract_entities(
            "Alice Johnson works at HouseSigma in Toronto on the Nova Scotia launch."
        )
        assert entities, (
            "INVARIANT BROKEN: extract_entities returned no entities for text "
            "with clear proper nouns. spaCy model load likely failed — entity "
            "linking is silently disabled."
        )
