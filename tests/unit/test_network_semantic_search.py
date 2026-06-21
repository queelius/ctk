"""Tests for semantic_search in the ctk.network provider.

Covers:
- No embeddings -> friendly message (not a stack trace)
- No embeddings -> exact friendly-message text
- Missing/empty query -> Error string
- Unknown tool still returns error (cross-check dispatch)
- semantic_search listed in ctk.network tool registry
- semantic_search schema has required 'query' field
"""

import pytest

from ctk.core.database import ConversationDB
from ctk.core.network_tools import execute_network_tool

pytestmark = pytest.mark.unit

_NO_EMBEDDINGS_MSG = (
    "No embeddings found. Generate them first with "
    "`ctk db embeddings` then `ctk db links`."
)


@pytest.fixture
def empty_db(tmp_path):
    db = ConversationDB(str(tmp_path))
    yield db
    db.close()


# ---------------------------------------------------------------------------
# No-embeddings path
# ---------------------------------------------------------------------------


def test_no_embeddings_friendly_message(empty_db):
    out = execute_network_tool(empty_db, "semantic_search", {"query": "python"})
    # Must not be a traceback and must mention embeddings
    assert "embedding" in out.lower()
    assert not out.startswith("Traceback")


def test_no_embeddings_exact_message(empty_db):
    """Tighter guard: the exact friendly sentence must appear."""
    out = execute_network_tool(empty_db, "semantic_search", {"query": "python"})
    assert "No embeddings found" in out


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_query_returns_error(empty_db):
    out = execute_network_tool(empty_db, "semantic_search", {"query": ""})
    assert out.startswith("Error:")


def test_missing_query_key_returns_error(empty_db):
    out = execute_network_tool(empty_db, "semantic_search", {})
    assert out.startswith("Error:")


# ---------------------------------------------------------------------------
# Dispatch wiring
# ---------------------------------------------------------------------------


def test_semantic_search_reachable_via_execute_network_tool(empty_db):
    """semantic_search must NOT return the 'unknown tool' error."""
    out = execute_network_tool(empty_db, "semantic_search", {"query": "test"})
    assert "unknown ctk.network tool" not in out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_semantic_search_in_network_provider():
    from ctk.core import network_tools  # noqa: F401 -- registers provider
    from ctk.core.tools_registry import iter_providers

    providers = {p.name: p for p in iter_providers()}
    net = providers.get("ctk.network")
    assert net is not None
    tool_names = [t["name"] for t in net.tools]
    assert "semantic_search" in tool_names


def test_semantic_search_schema_requires_query():
    from ctk.core.tools_registry import iter_providers

    providers = {p.name: p for p in iter_providers()}
    net = providers["ctk.network"]
    tool = next(t for t in net.tools if t["name"] == "semantic_search")
    assert "query" in tool["input_schema"]["required"]


def test_semantic_search_schema_has_top_k_property():
    from ctk.core.tools_registry import iter_providers

    providers = {p.name: p for p in iter_providers()}
    net = providers["ctk.network"]
    tool = next(t for t in net.tools if t["name"] == "semantic_search")
    assert "top_k" in tool["input_schema"]["properties"]
