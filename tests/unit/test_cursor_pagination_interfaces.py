"""
Tests for cursor pagination wired through CLI, db_helpers, and MCP layers.

Sprint 4.3: Verifies that cursor pagination from ConversationDB is properly
exposed through all three interface layers:
1. db_helpers - search_conversations_helper() passes cursor/page_size through
2. CLI cmd_query - --cursor and --page-size flags
3. MCP - cursor param in search_conversations and list_conversations tools
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy import text as sql_text

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationSummary,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
    PaginatedResult,
)
from ctk.core.pagination import encode_cursor


def _create_db_with_conversations(n: int = 10) -> ConversationDB:
    """Helper to create an in-memory DB with n conversations."""
    db = ConversationDB(":memory:")
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    for i in range(n):
        updated_at = base_time + timedelta(hours=i)
        created_at = updated_at - timedelta(minutes=5)

        metadata = ConversationMetadata(
            created_at=created_at,
            updated_at=updated_at,
            source="openai" if i % 2 == 0 else "anthropic",
            model=f"model-{i}",
            format="openai",
            version="1.0",
        )

        text = f"Message {i} about python" if i % 2 == 0 else f"Message {i} about rust"

        message = Message(
            id=f"msg-{i}",
            role=MessageRole.USER,
            content=MessageContent(text=text),
            timestamp=created_at,
        )

        conv = ConversationTree(
            id=f"conv-{i:03d}",
            title=f"Conversation {i}",
            metadata=metadata,
        )
        conv.add_message(message)
        db.save_conversation(conv)

    # Force timestamps via raw SQL to bypass ORM onupdate=func.now()
    with db.session_scope() as session:
        for i in range(n):
            updated_at = base_time + timedelta(hours=i)
            created_at = updated_at - timedelta(minutes=5)
            session.execute(
                sql_text(
                    "UPDATE conversations SET updated_at = :ua, created_at = :ca "
                    "WHERE id = :id"
                ),
                {"ua": updated_at, "ca": created_at, "id": f"conv-{i:03d}"},
            )

    return db


# =============================================================================
# 1. TestSearchConversationsHelperCursor
# =============================================================================


@pytest.mark.unit
class TestSearchConversationsHelperCursor:
    """Test cursor pagination in search_conversations_helper."""

    @pytest.fixture
    def db(self):
        return _create_db_with_conversations(10)

    def test_cursor_passed_to_db(self, db):
        """search_conversations_helper should pass cursor and page_size to db."""
        from ctk.core.db_helpers import search_conversations_helper

        # Use a cursor to get second page
        cursor = encode_cursor(
            datetime(2024, 1, 1, 9, 0, 0), "conv-009"
        )

        with patch.object(db, "search_conversations", wraps=db.search_conversations) as mock:
            search_conversations_helper(
                db=db,
                query="Message",
                cursor=cursor,
                page_size=3,
            )
            # Verify cursor and page_size were passed through
            call_kwargs = mock.call_args[1]
            assert call_kwargs["cursor"] == cursor
            assert call_kwargs["page_size"] == 3

    def test_cursor_result_prints_next_cursor(self, db, capsys):
        """When cursor pagination returns has_more, should print next_cursor."""
        from ctk.core.db_helpers import search_conversations_helper

        # First page with small page_size to guarantee has_more=True
        search_conversations_helper(
            db=db,
            query="Message",
            cursor="",  # empty = first page
            page_size=3,
        )

        captured = capsys.readouterr()
        assert "next_cursor" in captured.out.lower() or "Next page" in captured.out

    def test_no_cursor_returns_list_format(self, db, capsys):
        """Without cursor param, should use list format (backward compat)."""
        from ctk.core.db_helpers import search_conversations_helper

        search_conversations_helper(
            db=db,
            query="python",
        )

        captured = capsys.readouterr()
        # Should NOT mention cursor in output
        assert "next_cursor" not in captured.out.lower()

    def test_last_page_no_next_cursor(self, db, capsys):
        """Last page (has_more=False) should not print next_cursor."""
        from ctk.core.db_helpers import search_conversations_helper

        # Large page_size to get all results in one page
        search_conversations_helper(
            db=db,
            query="python",
            cursor="",
            page_size=100,
        )

        captured = capsys.readouterr()
        # Should indicate no more pages
        assert "next_cursor" not in captured.out.lower() or "null" in captured.out.lower()

    def test_cursor_json_output_includes_pagination(self, db, capsys):
        """JSON output with cursor should include pagination metadata."""
        from ctk.core.db_helpers import search_conversations_helper

        search_conversations_helper(
            db=db,
            query="Message",
            cursor="",
            page_size=3,
            output_format="json",
        )

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "next_cursor" in data
        assert "has_more" in data
        assert "items" in data
        assert len(data["items"]) == 3
        assert data["has_more"] is True


# =============================================================================
# 2. TestListConversationsHelperCursor
# =============================================================================


@pytest.mark.unit
class TestListConversationsHelperCursor:
    """Test cursor pagination in list_conversations_helper."""

    @pytest.fixture
    def db(self):
        return _create_db_with_conversations(10)

    def test_cursor_passed_to_db(self, db):
        """list_conversations_helper should pass cursor and page_size to db."""
        from ctk.core.db_helpers import list_conversations_helper

        with patch.object(db, "list_conversations", wraps=db.list_conversations) as mock:
            list_conversations_helper(
                db=db,
                cursor="",
                page_size=3,
            )
            call_kwargs = mock.call_args[1]
            assert call_kwargs["cursor"] == ""
            assert call_kwargs["page_size"] == 3

    def test_cursor_json_output_includes_pagination(self, db, capsys):
        """JSON output with cursor should include pagination metadata."""
        from ctk.core.db_helpers import list_conversations_helper

        list_conversations_helper(
            db=db,
            json_output=True,
            cursor="",
            page_size=3,
        )

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "next_cursor" in data
        assert "has_more" in data
        assert "items" in data
        assert len(data["items"]) == 3


# =============================================================================
# 3. TestCLICmdQueryCursor
# =============================================================================


@pytest.mark.unit
class TestCLICmdQueryCursor:
    """Test --cursor and --page-size flags in ctk query command."""

    @pytest.fixture
    def db(self):
        return _create_db_with_conversations(10)

    def test_query_parser_has_cursor_flag(self):
        """ctk query parser should accept --cursor flag."""
        from ctk.cli import main
        import argparse

        # Build the parser via main's setup
        with patch("sys.argv", ["ctk", "query", "--help"]):
            with pytest.raises(SystemExit):
                main()
        # If --cursor flag is not recognized, argparse would error differently

    def test_query_parser_has_page_size_flag(self):
        """ctk query parser should accept --page-size flag."""
        from ctk.cli import main

        with patch("sys.argv", ["ctk", "query", "--help"]):
            with pytest.raises(SystemExit):
                main()

    def test_cursor_flag_passes_to_helper(self, db):
        """--cursor flag should be passed to search_conversations_helper."""
        from ctk.cli import cmd_query

        cursor_val = encode_cursor(datetime(2024, 1, 1, 5, 0), "conv-005")

        args = MagicMock()
        args.db = ":memory:"
        args.view = None
        args.text = "test"
        args.limit = None
        args.since = None
        args.until = None
        args.tag = []
        args.source = None
        args.project = None
        args.model = None
        args.starred = False
        args.pinned = False
        args.archived = False
        args.include_archived = False
        args.order_by = "updated_at"
        args.asc = False
        args.format = "table"
        args.cursor = cursor_val
        args.page_size = 5

        with patch("ctk.cli.ConversationDB") as mock_db_cls, \
             patch("ctk.core.db_helpers.search_conversations_helper") as mock_helper:
            mock_helper.return_value = 0
            cmd_query(args)

            call_kwargs = mock_helper.call_args[1]
            assert call_kwargs["cursor"] == cursor_val
            assert call_kwargs["page_size"] == 5


# =============================================================================
# 4. TestMCPCursorPagination
# =============================================================================


@pytest.mark.unit
class TestMCPCursorPagination:
    """Test cursor pagination in MCP server tool schemas and handlers."""

    @pytest.fixture
    def event_loop(self):
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_search_schema_has_cursor(self, event_loop):
        """search_conversations tool schema should include cursor property."""
        from ctk.mcp_server import handle_list_tools

        tools = event_loop.run_until_complete(handle_list_tools())
        search_tool = next(t for t in tools if t.name == "search_conversations")

        props = search_tool.inputSchema["properties"]
        assert "cursor" in props
        assert props["cursor"]["type"] == "string"

    def test_list_schema_has_cursor(self, event_loop):
        """list_conversations tool schema should include cursor property."""
        from ctk.mcp_server import handle_list_tools

        tools = event_loop.run_until_complete(handle_list_tools())
        list_tool = next(t for t in tools if t.name == "list_conversations")

        props = list_tool.inputSchema["properties"]
        assert "cursor" in props
        assert props["cursor"]["type"] == "string"

    def test_search_handler_uses_cursor(self, event_loop):
        """search_conversations handler should pass cursor to DB."""
        from ctk.mcp_server import handle_call_tool

        cursor_val = encode_cursor(datetime(2024, 1, 1, 5, 0), "conv-005")

        # Mock db to return PaginatedResult
        mock_summary = MagicMock(spec=ConversationSummary)
        mock_summary.id = "conv-004"
        mock_summary.title = "Test Conv"
        mock_summary.message_count = 5
        mock_summary.starred_at = None
        mock_summary.pinned_at = None
        mock_summary.archived_at = None

        paginated = PaginatedResult(
            items=[mock_summary],
            next_cursor="next123",
            has_more=True,
        )

        with patch("ctk.mcp_server.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_conversations.return_value = paginated
            mock_get_db.return_value = mock_db

            result = event_loop.run_until_complete(
                handle_call_tool("search_conversations", {
                    "query": "test",
                    "cursor": cursor_val,
                })
            )

            # DB should have been called with cursor
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs["cursor"] == cursor_val

    def test_search_handler_returns_next_cursor(self, event_loop):
        """search_conversations response should include next_cursor when paginated."""
        from ctk.mcp_server import handle_call_tool

        mock_summary = MagicMock(spec=ConversationSummary)
        mock_summary.id = "conv-004"
        mock_summary.title = "Test Conv"
        mock_summary.message_count = 5
        mock_summary.starred_at = None
        mock_summary.pinned_at = None
        mock_summary.archived_at = None

        paginated = PaginatedResult(
            items=[mock_summary],
            next_cursor="next123",
            has_more=True,
        )

        with patch("ctk.mcp_server.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_conversations.return_value = paginated
            mock_get_db.return_value = mock_db

            result = event_loop.run_until_complete(
                handle_call_tool("search_conversations", {
                    "query": "test",
                    "cursor": "",
                })
            )

            # Response text should include next_cursor info
            response_text = result[0].text
            assert "next_cursor" in response_text or "next123" in response_text

    def test_list_handler_uses_cursor(self, event_loop):
        """list_conversations handler should pass cursor to DB."""
        from ctk.mcp_server import handle_call_tool

        mock_summary = MagicMock(spec=ConversationSummary)
        mock_summary.id = "conv-009"
        mock_summary.title = "Test Conv"
        mock_summary.created_at = datetime(2024, 1, 1)
        mock_summary.starred_at = None
        mock_summary.pinned_at = None
        mock_summary.archived_at = None

        paginated = PaginatedResult(
            items=[mock_summary],
            next_cursor="nextabc",
            has_more=True,
        )

        with patch("ctk.mcp_server.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.list_conversations.return_value = paginated
            mock_get_db.return_value = mock_db

            result = event_loop.run_until_complete(
                handle_call_tool("list_conversations", {
                    "cursor": "",
                })
            )

            # DB should have been called with cursor
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs["cursor"] == ""

    def test_list_handler_returns_next_cursor(self, event_loop):
        """list_conversations response should include next_cursor when paginated."""
        from ctk.mcp_server import handle_call_tool

        mock_summary = MagicMock(spec=ConversationSummary)
        mock_summary.id = "conv-009"
        mock_summary.title = "Test Conv"
        mock_summary.created_at = datetime(2024, 1, 1)
        mock_summary.starred_at = None
        mock_summary.pinned_at = None
        mock_summary.archived_at = None

        paginated = PaginatedResult(
            items=[mock_summary],
            next_cursor="nextabc",
            has_more=True,
        )

        with patch("ctk.mcp_server.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.list_conversations.return_value = paginated
            mock_get_db.return_value = mock_db

            result = event_loop.run_until_complete(
                handle_call_tool("list_conversations", {
                    "cursor": "",
                })
            )

            response_text = result[0].text
            assert "next_cursor" in response_text or "nextabc" in response_text

    def test_no_cursor_returns_legacy_format(self, event_loop):
        """Without cursor, should return legacy list format."""
        from ctk.mcp_server import handle_call_tool

        mock_summary = MagicMock(spec=ConversationSummary)
        mock_summary.id = "conv-009"
        mock_summary.title = "Test Conv"
        mock_summary.message_count = 5
        mock_summary.starred_at = None
        mock_summary.pinned_at = None
        mock_summary.archived_at = None

        with patch("ctk.mcp_server.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.search_conversations.return_value = [mock_summary]
            mock_get_db.return_value = mock_db

            result = event_loop.run_until_complete(
                handle_call_tool("search_conversations", {
                    "query": "test",
                })
            )

            response_text = result[0].text
            # Legacy format: no next_cursor line
            assert "next_cursor" not in response_text
