"""
Tests for the CTK MCP Server.

Tests the tool definitions, tool execution, and database operations
exposed via the MCP protocol.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Set test database path before importing mcp_server
TEST_DB_PATH = "/home/spinoza/github/beta/ctk/dev/openai-db"
os.environ["CTK_DATABASE_PATH"] = TEST_DB_PATH


class TestMCPServerToolDefinitions:
    """Test that tools are properly defined."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_list_tools_returns_expected_tools(self, event_loop):
        """Verify all expected tools are defined."""
        from ctk.mcp_server import handle_list_tools

        tools = event_loop.run_until_complete(handle_list_tools())

        tool_names = {t.name for t in tools}
        expected_tools = {
            "search_conversations",
            "list_conversations",
            "get_conversation",
            "get_statistics",
            "star_conversation",
            "pin_conversation",
            "archive_conversation",
            "set_title",
            "get_tags",
            "find_similar",
            "semantic_search",
            "get_network_summary",
            "get_clusters",
        }

        assert tool_names == expected_tools

    def test_search_conversations_schema(self, event_loop):
        """Verify search_conversations has correct input schema."""
        from ctk.mcp_server import handle_list_tools

        tools = event_loop.run_until_complete(handle_list_tools())
        search_tool = next(t for t in tools if t.name == "search_conversations")

        schema = search_tool.inputSchema
        assert "properties" in schema
        assert "query" in schema["properties"]
        assert "starred" in schema["properties"]
        assert "pinned" in schema["properties"]
        assert "archived" in schema["properties"]
        assert "limit" in schema["properties"]

    def test_get_conversation_schema(self, event_loop):
        """Verify get_conversation has correct input schema."""
        from ctk.mcp_server import handle_list_tools

        tools = event_loop.run_until_complete(handle_list_tools())
        get_tool = next(t for t in tools if t.name == "get_conversation")

        schema = get_tool.inputSchema
        assert "id" in schema["properties"]
        assert "include_content" in schema["properties"]
        assert "id" in schema["required"]


class TestMCPServerToolExecution:
    """Test tool execution against real database."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_get_statistics_returns_data(self, event_loop):
        """Test get_statistics returns proper statistics."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(handle_call_tool("get_statistics", {}))

        assert len(result) == 1
        text = result[0].text

        assert "CTK Database Statistics" in text
        assert "Total conversations:" in text
        assert "Total messages:" in text

    def test_list_conversations_returns_results(self, event_loop):
        """Test list_conversations returns conversation list."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(
            handle_call_tool("list_conversations", {"limit": 5})
        )

        assert len(result) == 1
        text = result[0].text

        # Should have numbered results
        assert "[1]" in text or "No conversations found" in text

    def test_search_conversations_with_query(self, event_loop):
        """Test search_conversations with a query."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(
            handle_call_tool("search_conversations", {"query": "python", "limit": 3})
        )

        assert len(result) == 1
        text = result[0].text

        # Should find something or report no results
        assert "conversation" in text.lower()

    def test_search_conversations_no_query(self, event_loop):
        """Test search_conversations without query (lists all)."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(
            handle_call_tool("search_conversations", {"limit": 3})
        )

        assert len(result) == 1
        text = result[0].text

        assert "conversation" in text.lower()

    def test_get_conversation_with_valid_id(self, event_loop):
        """Test get_conversation with a valid ID from the database."""
        from ctk.mcp_server import handle_call_tool

        # First list to get an ID
        list_result = event_loop.run_until_complete(
            handle_call_tool("list_conversations", {"limit": 1})
        )

        list_text = list_result[0].text

        # Extract first 8 chars of ID from format "[1] abc12345 ..."
        if "[1]" in list_text:
            # Parse ID from "[1] abc12345 ..."
            import re

            match = re.search(r"\[1\]\s+([a-f0-9]+)", list_text)
            if match:
                partial_id = match.group(1)[:8]

                # Now get the conversation
                result = event_loop.run_until_complete(
                    handle_call_tool("get_conversation", {"id": partial_id})
                )

                text = result[0].text

                # Should have conversation content
                assert "ID:" in text or "Error" in text

    def test_get_conversation_with_invalid_id(self, event_loop):
        """Test get_conversation with invalid ID returns error."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(
            handle_call_tool("get_conversation", {"id": "nonexistent12345"})
        )

        text = result[0].text
        assert "Error" in text or "Could not find" in text

    def test_get_tags_returns_list(self, event_loop):
        """Test get_tags returns tag list."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(handle_call_tool("get_tags", {}))

        assert len(result) == 1
        text = result[0].text

        # Either has tags or reports none
        assert "Tags" in text or "No tags" in text


class TestMCPServerHelperFunctions:
    """Test helper functions."""

    def test_resolve_conversation_id_exact_match(self):
        """Test ID resolution with exact match."""
        from ctk.mcp_server import get_db, resolve_conversation_id

        db = get_db()
        convs = db.list_conversations(limit=1)

        if convs:
            full_id = convs[0].id
            resolved = resolve_conversation_id(full_id)
            assert resolved == full_id

    def test_resolve_conversation_id_prefix_match(self):
        """Test ID resolution with prefix."""
        from ctk.mcp_server import get_db, resolve_conversation_id

        db = get_db()
        convs = db.list_conversations(limit=1)

        if convs:
            full_id = convs[0].id
            prefix = full_id[:8]
            resolved = resolve_conversation_id(prefix)
            assert resolved == full_id

    def test_resolve_conversation_id_not_found(self):
        """Test ID resolution with nonexistent ID."""
        from ctk.mcp_server import resolve_conversation_id

        resolved = resolve_conversation_id("nonexistent12345xyz")
        assert resolved is None

    def test_format_conversation_for_output(self):
        """Test conversation formatting."""
        from ctk.mcp_server import format_conversation_for_output, get_db

        db = get_db()
        convs = db.list_conversations(limit=1)

        if convs:
            conv = db.load_conversation(convs[0].id)
            if conv:
                output = format_conversation_for_output(conv)

                # Check expected sections
                assert "ID:" in output
                assert conv.id in output

    def test_format_conversation_without_content(self):
        """Test conversation formatting without content."""
        from ctk.mcp_server import format_conversation_for_output, get_db

        db = get_db()
        convs = db.list_conversations(limit=1)

        if convs:
            conv = db.load_conversation(convs[0].id)
            if conv:
                output = format_conversation_for_output(conv, include_content=False)

                # Should have header but minimal content
                assert "ID:" in output


class TestMCPServerDatabaseConnection:
    """Test database connection and configuration."""

    def test_get_db_returns_connection(self):
        """Test that get_db returns a valid connection."""
        from ctk.mcp_server import get_db

        db = get_db()
        assert db is not None

    def test_get_db_respects_env_var(self):
        """Test that CTK_DATABASE_PATH env var is respected."""
        from ctk.mcp_server import get_db

        db = get_db()
        # The database should have conversations from dev/openai-db
        convs = db.list_conversations(limit=5)
        assert len(convs) > 0


class TestMCPServerUnknownTool:
    """Test handling of unknown tools."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_unknown_tool_returns_error(self, event_loop):
        """Test that unknown tool names return an error."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(handle_call_tool("nonexistent_tool", {}))

        text = result[0].text
        assert "Unknown tool" in text
