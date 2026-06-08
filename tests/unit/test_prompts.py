"""
Unit tests for ctk/core/prompts.py.

Covers:
- get_ctk_system_prompt: context-aware prompt with db stats
- get_ctk_system_prompt_no_tools: simpler prompt without tool instructions
- generate_cli_prompt_from_argparse: argparse-based prompt builder
- generate_tui_prompt_from_help: COMMAND_HELP dict-based prompt builder
"""

import argparse

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.core.prompts import (
    generate_cli_prompt_from_argparse,
    generate_tui_prompt_from_help,
    get_ctk_system_prompt,
    get_ctk_system_prompt_no_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_memory_db() -> ConversationDB:
    """Return an in-memory ConversationDB."""
    return ConversationDB(":memory:")


def make_conversation(
    conv_id: str = "conv_001", title: str = "Test Conv"
) -> ConversationTree:
    """Build a minimal ConversationTree with one user message."""
    tree = ConversationTree(
        id=conv_id,
        title=title,
        metadata=ConversationMetadata(source="test", model="test-model"),
    )
    msg = Message(
        id=f"{conv_id}_msg1",
        role=MessageRole.USER,
        content=MessageContent(text="Hello"),
        parent_id=None,
    )
    tree.add_message(msg)
    return tree


def make_argparser_with_subcommands() -> argparse.ArgumentParser:
    """Return a realistic ArgumentParser that mirrors the CTK CLI structure."""
    parser = argparse.ArgumentParser(description="CTK test parser")
    subs = parser.add_subparsers(dest="command")

    # 'query' subcommand
    query_p = subs.add_parser("query", description="Search conversations")
    query_p.add_argument("--query", help="Search term")
    query_p.add_argument("--limit", type=int, help="Max results")

    # 'export' subcommand
    export_p = subs.add_parser("export", description="Export conversations")
    export_p.add_argument("--format", help="Output format")

    # 'ask' and 'chat' should be excluded from the prompt
    subs.add_parser("ask", description="Ask the LLM")
    subs.add_parser("chat", description="Chat mode")

    return parser


def make_tui_command_help() -> dict:
    """Return a minimal COMMAND_HELP-style dict."""
    return {
        "help": {
            "desc": "Show this help message",
            "usage": "/help",
        },
        "search": {
            "desc": "Search conversations",
            "usage": "/search <query>",
            "details": "Full-text search across all conversations.",
            "examples": ["/search python", "/search async"],
        },
        "tag": {
            "desc": "Tag a conversation",
            "usage": "/tag <tag>",
        },
        "star": {
            "desc": "Star current conversation",
            "usage": "/star",
            "examples": ["/star"],
        },
    }


# ---------------------------------------------------------------------------
# get_ctk_system_prompt
# ---------------------------------------------------------------------------


class TestGetCtkSystemPrompt:
    """Tests for get_ctk_system_prompt."""

    @pytest.mark.unit
    def test_returns_non_empty_string(self):
        """Prompt must be a non-empty string."""
        db = make_memory_db()
        result = get_ctk_system_prompt(db)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        db.close()

    @pytest.mark.unit
    def test_contains_tool_names(self):
        """Prompt must mention core tools by name."""
        db = make_memory_db()
        result = get_ctk_system_prompt(db)
        assert "search_conversations" in result
        assert "get_conversation" in result
        assert "get_statistics" in result
        db.close()

    @pytest.mark.unit
    def test_contains_no_fabricate_instruction(self):
        """Prompt must include a 'never fabricate' instruction."""
        db = make_memory_db()
        result = get_ctk_system_prompt(db)
        assert "fabricate" in result.lower() or "never" in result.lower()
        db.close()

    @pytest.mark.unit
    def test_default_path_is_slash(self):
        """Default current_path of '/' appears in the prompt."""
        db = make_memory_db()
        result = get_ctk_system_prompt(db)
        assert "/" in result
        db.close()

    @pytest.mark.unit
    def test_custom_path_appears(self):
        """A custom current_path is embedded in the prompt."""
        db = make_memory_db()
        result = get_ctk_system_prompt(db, current_path="/starred")
        assert "/starred" in result
        db.close()

    @pytest.mark.unit
    def test_empty_db_shows_zero_counts(self):
        """An empty database should show 0 conversations / 0 messages."""
        db = make_memory_db()
        result = get_ctk_system_prompt(db)
        assert "0 conversations" in result
        assert "0 messages" in result
        db.close()

    @pytest.mark.unit
    def test_reflects_populated_db_stats(self):
        """After saving conversations the counts should be reflected."""
        db = make_memory_db()
        db.save_conversation(make_conversation("c1"))
        db.save_conversation(make_conversation("c2"))
        result = get_ctk_system_prompt(db)
        # Exactly 2 conversations should appear somewhere in the prompt.
        assert "2 conversations" in result
        db.close()

    @pytest.mark.unit
    def test_starred_count_reflected(self):
        """Starred count from the database should appear in the prompt."""
        db = make_memory_db()
        tree = make_conversation("c_star")
        db.save_conversation(tree)
        db.star_conversation("c_star", star=True)
        result = get_ctk_system_prompt(db)
        assert "1 starred" in result
        db.close()

    @pytest.mark.unit
    def test_numbered_result_navigation_hint(self):
        """Prompt should include hint about numbered search results."""
        db = make_memory_db()
        result = get_ctk_system_prompt(db)
        assert "[1]" in result or "numbered" in result.lower()
        db.close()

    @pytest.mark.unit
    def test_db_error_fallback_is_non_empty(self):
        """Even if the DB raises, the function returns a valid non-empty string."""

        class BrokenDB:
            def get_statistics(self):
                raise RuntimeError("db failure")

            def list_conversations(self, **kwargs):
                raise RuntimeError("db failure")

        result = get_ctk_system_prompt(BrokenDB())  # type: ignore[arg-type]
        assert isinstance(result, str)
        assert len(result.strip()) > 0


# ---------------------------------------------------------------------------
# get_ctk_system_prompt_no_tools
# ---------------------------------------------------------------------------


class TestGetCtkSystemPromptNoTools:
    """Tests for get_ctk_system_prompt_no_tools."""

    @pytest.mark.unit
    def test_returns_non_empty_string(self):
        """No-tools prompt must be a non-empty string."""
        db = make_memory_db()
        result = get_ctk_system_prompt_no_tools(db)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        db.close()

    @pytest.mark.unit
    def test_contains_shell_command_hints(self):
        """Prompt must describe shell commands the user can type."""
        db = make_memory_db()
        result = get_ctk_system_prompt_no_tools(db)
        assert "find" in result or "show" in result or "ls" in result
        db.close()

    @pytest.mark.unit
    def test_no_tool_call_instruction(self):
        """No-tools variant should NOT mention tool calling."""
        db = make_memory_db()
        result = get_ctk_system_prompt_no_tools(db)
        # The prompt should guide the user toward commands, not LLM tool calls
        assert "search_conversations" not in result
        assert "get_conversation" not in result
        db.close()

    @pytest.mark.unit
    def test_default_path_embedded(self):
        """Default path '/' should appear in the no-tools prompt."""
        db = make_memory_db()
        result = get_ctk_system_prompt_no_tools(db)
        assert "/" in result
        db.close()

    @pytest.mark.unit
    def test_custom_path_embedded(self):
        """Custom path should be embedded in the no-tools prompt."""
        db = make_memory_db()
        result = get_ctk_system_prompt_no_tools(db, current_path="/pinned")
        assert "/pinned" in result
        db.close()

    @pytest.mark.unit
    def test_empty_db_zero_counts(self):
        """Empty DB should yield 0 conversations and 0 messages."""
        db = make_memory_db()
        result = get_ctk_system_prompt_no_tools(db)
        assert "0 conversations" in result
        assert "0 messages" in result
        db.close()

    @pytest.mark.unit
    def test_populated_db_counts(self):
        """Two saved conversations should appear in the count."""
        db = make_memory_db()
        db.save_conversation(make_conversation("nt1"))
        db.save_conversation(make_conversation("nt2"))
        result = get_ctk_system_prompt_no_tools(db)
        assert "2 conversations" in result
        db.close()

    @pytest.mark.unit
    def test_starred_conversations_stat_read(self):
        """Starring a conversation should not cause errors in the no-tools prompt."""
        db = make_memory_db()
        tree = make_conversation("nt_star")
        db.save_conversation(tree)
        db.star_conversation("nt_star", star=True)
        # The no-tools prompt still reads starred count internally (no error);
        # it just may not embed it in the text, so we only verify it is a valid string.
        result = get_ctk_system_prompt_no_tools(db)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        db.close()

    @pytest.mark.unit
    def test_never_fabricate_instruction(self):
        """Prompt must caution against making up data."""
        db = make_memory_db()
        result = get_ctk_system_prompt_no_tools(db)
        lower = result.lower()
        assert "never" in lower or "don't" in lower or "not" in lower
        db.close()

    @pytest.mark.unit
    def test_db_error_fallback(self):
        """Broken DB should still return a valid non-empty string."""

        class BrokenDB:
            def get_statistics(self):
                raise RuntimeError("broken")

            def list_conversations(self, **kwargs):
                raise RuntimeError("broken")

        result = get_ctk_system_prompt_no_tools(BrokenDB())  # type: ignore[arg-type]
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.unit
    def test_different_from_tools_variant(self):
        """The two prompt variants should produce different output."""
        db = make_memory_db()
        with_tools = get_ctk_system_prompt(db)
        without_tools = get_ctk_system_prompt_no_tools(db)
        assert with_tools != without_tools
        db.close()


# ---------------------------------------------------------------------------
# generate_cli_prompt_from_argparse
# ---------------------------------------------------------------------------


class TestGenerateCliPromptFromArgparse:
    """Tests for generate_cli_prompt_from_argparse."""

    @pytest.mark.unit
    def test_returns_non_empty_string(self):
        """Result must be a non-empty string."""
        parser = make_argparser_with_subcommands()
        result = generate_cli_prompt_from_argparse(parser)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.unit
    def test_contains_subcommand_names(self):
        """Known subcommand names must appear in the prompt."""
        parser = make_argparser_with_subcommands()
        result = generate_cli_prompt_from_argparse(parser)
        assert "query" in result
        assert "export" in result

    @pytest.mark.unit
    def test_excludes_ask_and_chat(self):
        """'ask' and 'chat' subcommands must be excluded."""
        parser = make_argparser_with_subcommands()
        result = generate_cli_prompt_from_argparse(parser)
        # They should NOT appear as headings
        assert "**ask**" not in result
        assert "**chat**" not in result

    @pytest.mark.unit
    def test_contains_argument_details(self):
        """Arguments like --query and --limit should appear."""
        parser = make_argparser_with_subcommands()
        result = generate_cli_prompt_from_argparse(parser)
        assert "--query" in result or "query" in result
        assert "--limit" in result or "limit" in result

    @pytest.mark.unit
    def test_contains_ctk_context(self):
        """Prompt must mention CTK or conversation toolkit."""
        parser = make_argparser_with_subcommands()
        result = generate_cli_prompt_from_argparse(parser)
        assert "CTK" in result or "Conversation Toolkit" in result

    @pytest.mark.unit
    def test_contains_instructions(self):
        """Prompt must include natural-language processing instructions."""
        parser = make_argparser_with_subcommands()
        result = generate_cli_prompt_from_argparse(parser)
        lower = result.lower()
        assert "tool" in lower or "function" in lower or "operation" in lower

    @pytest.mark.unit
    def test_parser_without_subparsers(self):
        """A parser with no subcommands must still return a non-empty string."""
        parser = argparse.ArgumentParser(description="Bare parser")
        result = generate_cli_prompt_from_argparse(parser)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.unit
    def test_subcommand_description_included(self):
        """Each subcommand's description should appear in the output."""
        parser = make_argparser_with_subcommands()
        result = generate_cli_prompt_from_argparse(parser)
        assert "Search conversations" in result
        assert "Export conversations" in result


# ---------------------------------------------------------------------------
# generate_tui_prompt_from_help
# ---------------------------------------------------------------------------


class TestGenerateTuiPromptFromHelp:
    """Tests for generate_tui_prompt_from_help."""

    @pytest.mark.unit
    def test_returns_non_empty_string(self):
        """Result must be a non-empty string."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.unit
    def test_contains_command_names(self):
        """Non-help commands must appear in the prompt."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        assert "/search" in result
        assert "/tag" in result
        assert "/star" in result

    @pytest.mark.unit
    def test_excludes_help_command(self):
        """The 'help' command itself should be excluded."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        assert "**/help**" not in result

    @pytest.mark.unit
    def test_includes_descriptions(self):
        """Command descriptions must appear."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        assert "Search conversations" in result
        assert "Tag a conversation" in result

    @pytest.mark.unit
    def test_includes_usage(self):
        """Usage strings must appear in the prompt."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        assert "/search <query>" in result

    @pytest.mark.unit
    def test_includes_details_when_present(self):
        """'details' field should be embedded if present."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        assert "Full-text search" in result

    @pytest.mark.unit
    def test_includes_examples_when_present(self):
        """'examples' entries should appear (up to 2)."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        assert "/search python" in result

    @pytest.mark.unit
    def test_empty_help_dict(self):
        """An empty command help dict must still return a valid non-empty string."""
        result = generate_tui_prompt_from_help({})
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    @pytest.mark.unit
    def test_only_help_key(self):
        """A dict with only 'help' must still produce valid output (no commands listed)."""
        result = generate_tui_prompt_from_help(
            {"help": {"desc": "show help", "usage": "/help"}}
        )
        assert isinstance(result, str)
        assert "**/help**" not in result

    @pytest.mark.unit
    def test_contains_tui_context(self):
        """Prompt must mention TUI or interactive session."""
        result = generate_tui_prompt_from_help(make_tui_command_help())
        lower = result.lower()
        assert "tui" in lower or "chat" in lower or "interactive" in lower

    @pytest.mark.unit
    def test_command_without_details_or_examples(self):
        """Commands lacking 'details' and 'examples' keys should not cause errors."""
        minimal = {
            "pin": {"desc": "Pin conversation", "usage": "/pin"},
        }
        result = generate_tui_prompt_from_help(minimal)
        assert "/pin" in result
        assert "Pin conversation" in result

    @pytest.mark.unit
    def test_examples_capped_at_two(self):
        """Only the first two examples should appear."""
        many_examples = {
            "search": {
                "desc": "Search",
                "usage": "/search <q>",
                "examples": ["/search a", "/search b", "/search c", "/search d"],
            }
        }
        result = generate_tui_prompt_from_help(many_examples)
        assert "/search a" in result
        assert "/search b" in result
        # Third example should be absent
        assert "/search c" not in result
