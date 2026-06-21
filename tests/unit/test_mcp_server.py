"""
Tests for the CTK MCP projection layer (Task 6).

Verifies:
- ``project_tools()`` returns exactly the 7 curated canonical tools plus the
  ``find_similar`` legacy alias (8 total), each a ``types.Tool`` with
  ``inputSchema`` set and no ``pass_through`` attribute.
- Legacy alias dispatch: ``find_similar`` with old param names routes to
  ``find_similar_conversations`` and returns a TextContent (not "Unknown tool").
- Canonical ``get_conversation`` with legacy ``id`` param (alias) works.
- A non-curated name (``star_conversation``) returns "Unknown tool".
- ``get_statistics`` works end-to-end.
- ``search_conversations`` works end-to-end.
- ``execute_sql`` SELECT works.
- Legacy ``update_conversation`` with ``id`` alias returns "No changes" when no
  optional fields are provided.
"""

import asyncio
import os

import pytest
import mcp.types as types

# Set test database path before importing anything that triggers get_db
TEST_DB_PATH = "/home/spinoza/github/beta/ctk/dev/openai-db"
os.environ["CTK_DATABASE_PATH"] = TEST_DB_PATH

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def db():
    from ctk.mcp_server import get_db

    return get_db()


@pytest.fixture(scope="module")
def first_conv_prefix(db):
    """Return an 8-char prefix of the first conversation in the DB, or None."""
    convs = db.list_conversations(limit=1)
    if not convs:
        return None
    return convs[0].id[:8]


# ---------------------------------------------------------------------------
# project_tools() contract
# ---------------------------------------------------------------------------


class TestProjectTools:
    """Assert the curated MCP tool set is derived correctly from the registry."""

    def test_returns_exactly_eight_tools(self):
        from ctk.interfaces.mcp.projection import project_tools

        tools = project_tools()
        assert (
            len(tools) == 8
        ), f"Expected 8 tools, got {len(tools)}: {[t.name for t in tools]}"

    def test_contains_seven_canonical_names(self):
        from ctk.interfaces.mcp.projection import project_tools, _CURATED_MCP_TOOLS

        names = {t.name for t in project_tools()}
        assert _CURATED_MCP_TOOLS <= names

    def test_contains_find_similar_alias(self):
        from ctk.interfaces.mcp.projection import project_tools

        names = {t.name for t in project_tools()}
        assert "find_similar" in names

    def test_sorted_by_name(self):
        from ctk.interfaces.mcp.projection import project_tools

        tools = project_tools()
        names = [t.name for t in tools]
        assert names == sorted(names)

    def test_each_tool_has_input_schema(self):
        from ctk.interfaces.mcp.projection import project_tools

        for t in project_tools():
            assert hasattr(t, "inputSchema"), f"Tool {t.name} missing inputSchema"
            assert isinstance(
                t.inputSchema, dict
            ), f"Tool {t.name} inputSchema not a dict"
            assert (
                "properties" in t.inputSchema
            ), f"Tool {t.name} inputSchema missing 'properties'"

    def test_no_pass_through_attribute(self):
        from ctk.interfaces.mcp.projection import project_tools

        for t in project_tools():
            assert not hasattr(
                t, "pass_through"
            ), f"Tool {t.name} has pass_through (registry-only key leaked into types.Tool)"

    def test_get_conversation_uses_camel_input_schema(self):
        from ctk.interfaces.mcp.projection import project_tools

        t = next(x for x in project_tools() if x.name == "get_conversation")
        # camelCase attribute from mcp types
        assert hasattr(t, "inputSchema")
        # canonical schema uses conversation_id
        assert "conversation_id" in t.inputSchema["properties"]

    def test_find_similar_alias_has_legacy_param_names(self):
        from ctk.interfaces.mcp.projection import project_tools

        t = next(x for x in project_tools() if x.name == "find_similar")
        props = t.inputSchema["properties"]
        assert "id" in props, "find_similar alias should expose 'id' (legacy name)"
        assert (
            "top_k" in props
        ), "find_similar alias should expose 'top_k' (legacy name)"
        assert (
            "threshold" in props
        ), "find_similar alias should expose 'threshold' (legacy name)"
        # must NOT expose the canonical names in the alias schema
        assert "conversation_id" not in props
        assert "min_similarity" not in props


# ---------------------------------------------------------------------------
# canonical_name / normalize_aliases helpers
# ---------------------------------------------------------------------------


class TestAliasHelpers:
    def test_canonical_name_identity(self):
        from ctk.interfaces.mcp.projection import canonical_name

        assert canonical_name("search_conversations") == "search_conversations"
        assert canonical_name("get_statistics") == "get_statistics"

    def test_canonical_name_find_similar(self):
        from ctk.interfaces.mcp.projection import canonical_name

        assert canonical_name("find_similar") == "find_similar_conversations"

    def test_normalize_aliases_find_similar(self):
        from ctk.interfaces.mcp.projection import normalize_aliases

        args = {"id": "abc12345", "top_k": 5, "threshold": 0.2}
        out = normalize_aliases("find_similar", args)
        assert out == {"conversation_id": "abc12345", "limit": 5, "min_similarity": 0.2}

    def test_normalize_aliases_get_conversation(self):
        from ctk.interfaces.mcp.projection import normalize_aliases

        args = {"id": "abc12345", "include_content": True}
        out = normalize_aliases("get_conversation", args)
        assert out == {"conversation_id": "abc12345", "show_messages": True}

    def test_normalize_aliases_update_conversation(self):
        from ctk.interfaces.mcp.projection import normalize_aliases

        args = {"id": "abc12345", "starred": True}
        out = normalize_aliases("update_conversation", args)
        assert out == {"conversation_id": "abc12345", "starred": True}

    def test_normalize_aliases_no_change_for_unknown_tool(self):
        from ctk.interfaces.mcp.projection import normalize_aliases

        args = {"query": "python", "limit": 5}
        out = normalize_aliases("search_conversations", args)
        assert out == args

    def test_normalize_aliases_does_not_mutate_input(self):
        from ctk.interfaces.mcp.projection import normalize_aliases

        args = {"id": "abc12345"}
        orig = dict(args)
        normalize_aliases("get_conversation", args)
        assert args == orig


# ---------------------------------------------------------------------------
# handle_tool dispatch
# ---------------------------------------------------------------------------


class TestHandleTool:
    """Verify handle_tool routes correctly, applies aliases, returns TextContent."""

    def test_unknown_tool_returns_unknown_message(self, event_loop, db):
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("star_conversation", {}, db)
        )
        assert len(result) == 1
        assert result[0].text.startswith("Unknown tool:")

    def test_nonexistent_tool_returns_unknown_message(self, event_loop, db):
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("totally_fake_tool_xyz", {}, db)
        )
        assert len(result) == 1
        assert "Unknown tool" in result[0].text

    def test_get_statistics_returns_text_content(self, event_loop, db):
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(handle_tool("get_statistics", {}, db))
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)
        assert "Total conversations:" in result[0].text

    def test_search_conversations_returns_text_content(self, event_loop, db):
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("search_conversations", {"limit": 3}, db)
        )
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)
        assert "conversation" in result[0].text.lower()

    def test_execute_sql_select(self, event_loop, db):
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("execute_sql", {"sql": "SELECT COUNT(*) as cnt FROM conversations"}, db)
        )
        assert len(result) == 1
        assert "cnt" in result[0].text

    def test_find_similar_alias_dispatches_via_handle_tool(
        self, event_loop, db, first_conv_prefix
    ):
        """find_similar (legacy name + legacy params) must NOT return 'Unknown tool'."""
        if first_conv_prefix is None:
            pytest.skip("No conversations in test DB")
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("find_similar", {"id": first_conv_prefix, "top_k": 5}, db)
        )
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)
        # Must not be "Unknown tool"
        assert "Unknown tool" not in result[0].text

    def test_get_conversation_alias_id_param(self, event_loop, db, first_conv_prefix):
        """get_conversation with legacy 'id' alias must work."""
        if first_conv_prefix is None:
            pytest.skip("No conversations in test DB")
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("get_conversation", {"id": first_conv_prefix}, db)
        )
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)
        assert "Unknown tool" not in result[0].text

    def test_update_conversation_alias_id_param(self, event_loop, db, first_conv_prefix):
        """update_conversation with legacy 'id' alias and no changes returns 'No changes'."""
        if first_conv_prefix is None:
            pytest.skip("No conversations in test DB")
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("update_conversation", {"id": first_conv_prefix}, db)
        )
        assert len(result) == 1
        assert "No changes" in result[0].text


# ---------------------------------------------------------------------------
# server.py integration (via ctk.mcp_server backward-compat entry point)
# ---------------------------------------------------------------------------


class TestMCPServerIntegration:
    """Smoke-tests through the ctk.mcp_server entry point."""

    def test_handle_list_tools_returns_eight(self, event_loop):
        from ctk.mcp_server import handle_list_tools

        tools = event_loop.run_until_complete(handle_list_tools())
        assert len(tools) == 8

    def test_handle_list_tools_expected_names(self, event_loop):
        from ctk.mcp_server import handle_list_tools

        tools = event_loop.run_until_complete(handle_list_tools())
        names = {t.name for t in tools}
        expected = {
            "search_conversations",
            "get_conversation",
            "update_conversation",
            "get_statistics",
            "find_similar_conversations",
            "find_similar",
            "semantic_search",
            "execute_sql",
        }
        assert names == expected

    def test_handle_call_tool_unknown_returns_error(self, event_loop):
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(handle_call_tool("nonexistent_tool", {}))
        assert "Unknown tool" in result[0].text

    def test_handle_call_tool_get_statistics(self, event_loop):
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(handle_call_tool("get_statistics", {}))
        assert "Total conversations:" in result[0].text

    def test_handle_call_tool_star_conversation_not_exposed(self, event_loop):
        """star_conversation is a builtin tool but NOT in the MCP curated set."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(handle_call_tool("star_conversation", {}))
        assert "Unknown tool" in result[0].text
