import pytest
from ctk.core.database import ConversationDB
from ctk.core.builtin_tools import (  # noqa: F401
    BuiltinTool,
    ToolContext,
    ToolResult,
    builtin_tool_names,
    execute_builtin_tool,
)
from ctk.core.models import ConversationTree, Message, MessageContent, MessageRole

pytestmark = pytest.mark.unit


def test_unknown_tool_returns_sentinel(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        assert (
            execute_builtin_tool(db, "nonsense_xyz", {}) == "Unknown tool: nonsense_xyz"
        )
    finally:
        db.close()


def test_handler_exception_wrapped(tmp_path):
    # A registered tool whose handler raises must surface the legacy wrapper string.
    db = ConversationDB(str(tmp_path))
    try:
        import ctk.core.builtin_tools as bt

        def boom(ctx):
            raise RuntimeError("kaboom")

        tool = BuiltinTool(name="_probe", description="", input_schema={}, handler=boom)
        bt._BUILTIN_TOOLS.append(tool)
        bt._rebuild_handlers()
        try:
            out = execute_builtin_tool(db, "_probe", {})
            assert out == "Error executing _probe: kaboom"
        finally:
            bt._BUILTIN_TOOLS.remove(tool)
            bt._rebuild_handlers()
    finally:
        db.close()


def test_tool_result_message():
    assert ToolResult.message("hi").text == "hi"


def test_list_tags_empty_db(tmp_path):
    """list_tags on an empty db returns the exact legacy sentinel string."""
    db = ConversationDB(str(tmp_path))
    try:
        result = execute_builtin_tool(db, "list_tags", {})
        assert result == "No tags found in database."
    finally:
        db.close()


def test_list_tags_seeded_db(tmp_path):
    """list_tags with tags in the db.

    The legacy handler reads stats.get("by_tag", {}) but get_statistics()
    returns "top_tags" (list of dicts), never "by_tag". So the legacy code
    always falls through to the empty-sentinel path. This test guards that
    the migrated handler reproduces that exact behavior verbatim.
    """
    db = ConversationDB(str(tmp_path))
    try:
        tree = ConversationTree(
            id="aaaaaaaa-0000-0000-0000-000000000000", title="Tagged"
        )
        tree.add_message(
            Message(
                id="m1",
                role=MessageRole.USER,
                content=MessageContent(text="hello"),
                parent_id=None,
            )
        )
        tree.metadata.tags = ["python", "ai"]
        db.save_conversation(tree)

        # Legacy behavior: by_tag key is absent from get_statistics(), so even
        # a seeded db returns the "No tags found" string.
        result = execute_builtin_tool(db, "list_tags", {})
        assert result == "No tags found in database."
    finally:
        db.close()


def test_tag_tools_in_builtin_tool_names():
    """All 4 tag tools are registered in builtin_tool_names()."""
    names = builtin_tool_names()
    for tool in (
        "tag_conversation",
        "remove_tag",
        "list_tags",
        "auto_tag_conversation",
    ):
        assert tool in names, f"{tool!r} not found in builtin_tool_names()"


def _seed_db(db):
    """Helper: save two conversations and return them."""
    import uuid

    trees = []
    for title in ("Alpha conversation", "Beta conversation"):
        tree = ConversationTree(id=str(uuid.uuid4()), title=title)
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="hello"),
                parent_id=None,
            )
        )
        db.save_conversation(tree)
        trees.append(tree)
    return trees


def test_listing_tools_in_builtin_tool_names():
    """All 5 listing tools are registered."""
    names = builtin_tool_names()
    for tool in (
        "get_statistics",
        "list_sources",
        "list_models",
        "get_recent_conversations",
        "list_conversations",
    ):
        assert tool in names, f"{tool!r} not found in builtin_tool_names()"


def test_list_conversations_seeded_smoke(tmp_path):
    """list_conversations returns prefix 'Conversations (' and no error prefix."""
    db = ConversationDB(str(tmp_path))
    try:
        _seed_db(db)
        result = execute_builtin_tool(db, "list_conversations", {})
        assert not result.startswith("Error executing"), result
        assert result.startswith("Conversations ("), repr(result)
    finally:
        db.close()


def test_get_recent_conversations_seeded_smoke(tmp_path):
    """get_recent_conversations returns prefix 'Recent conversations' and no error prefix."""
    db = ConversationDB(str(tmp_path))
    try:
        _seed_db(db)
        result = execute_builtin_tool(db, "get_recent_conversations", {})
        assert not result.startswith("Error executing"), result
        assert result.startswith("Recent conversations"), repr(result)
    finally:
        db.close()


def test_get_statistics_smoke(tmp_path):
    """get_statistics returns prefix 'Database Statistics:'."""
    db = ConversationDB(str(tmp_path))
    try:
        _seed_db(db)
        result = execute_builtin_tool(db, "get_statistics", {})
        assert not result.startswith("Error executing"), result
        assert result.startswith("Database Statistics:"), repr(result)
    finally:
        db.close()


def test_task5_tools_in_builtin_tool_names():
    """All 4 Task-5 single-conversation-read tools are registered."""
    names = builtin_tool_names()
    for tool in (
        "get_conversation",
        "show_conversation_content",
        "list_conversation_paths",
        "export_conversation",
    ):
        assert tool in names, f"{tool!r} not found in builtin_tool_names()"


def test_export_conversation_smoke(tmp_path):
    """export_conversation with an 8-char prefix returns an export string, not an error."""
    import uuid

    db = ConversationDB(str(tmp_path))
    try:
        conv_id = str(uuid.uuid4())
        tree = ConversationTree(id=conv_id, title="Export smoke")
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="hello export"),
                parent_id=None,
            )
        )
        db.save_conversation(tree)

        result = execute_builtin_tool(
            db,
            "export_conversation",
            {"conversation_id": conv_id[:8], "format": "markdown"},
        )
        assert not result.startswith("Error executing"), result
        assert "Export smoke" in result or "markdown" in result.lower(), repr(result)
    finally:
        db.close()


def test_get_conversation_prefix_smoke(tmp_path):
    """get_conversation with an 8-char prefix resolves and returns conversation detail."""
    import uuid

    db = ConversationDB(str(tmp_path))
    try:
        conv_id = str(uuid.uuid4())
        tree = ConversationTree(id=conv_id, title="GetConv smoke")
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="hi there"),
                parent_id=None,
            )
        )
        db.save_conversation(tree)

        result = execute_builtin_tool(
            db,
            "get_conversation",
            {"conversation_id": conv_id[:8]},
        )
        assert not result.startswith("Error executing"), result
        assert "No conversation found" not in result, repr(result)
        assert "GetConv smoke" in result, repr(result)
    finally:
        db.close()


def test_task6_tools_in_builtin_tool_names():
    """Both Task-6 tools are registered in builtin_tool_names()."""
    names = builtin_tool_names()
    for tool in ("duplicate_conversation", "list_plugins"):
        assert tool in names, f"{tool!r} not found in builtin_tool_names()"


def test_duplicate_conversation_smoke(tmp_path):
    """duplicate_conversation creates a copy and returns 'Created copy:' prefix."""
    import uuid

    db = ConversationDB(str(tmp_path))
    try:
        conv_id = str(uuid.uuid4())
        tree = ConversationTree(id=conv_id, title="Original")
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="hello"),
                parent_id=None,
            )
        )
        db.save_conversation(tree)

        before = db.get_statistics().get("total_conversations", 0)
        result = execute_builtin_tool(
            db,
            "duplicate_conversation",
            {"conversation_id": conv_id[:8], "new_title": "Copy X"},
        )
        after = db.get_statistics().get("total_conversations", 0)

        assert not result.startswith("Error executing"), result
        assert result.startswith("Created copy:"), repr(result)
        assert after == before + 1, f"expected {before + 1} conversations, got {after}"
    finally:
        db.close()


def test_list_plugins_smoke(tmp_path):
    """list_plugins returns 'Available Plugins:' prefix and no error prefix."""
    db = ConversationDB(str(tmp_path))
    try:
        result = execute_builtin_tool(db, "list_plugins", {})
        assert not result.startswith("Error executing"), result
        assert result.startswith("Available Plugins:"), repr(result)
    finally:
        db.close()


def test_execute_shell_command_with_fake_executor(tmp_path):
    """R5 guard: execute_shell_command surfaces .output from a fake executor."""
    from collections import namedtuple

    FakeResult = namedtuple("FakeResult", ["output", "success", "error"])

    def fake_executor(cmd):
        return FakeResult(output=f"ran: {cmd}", success=True, error="")

    db = ConversationDB(str(tmp_path))
    try:
        result = execute_builtin_tool(
            db, "execute_shell_command", {"command": "ls"}, shell_executor=fake_executor
        )
        assert result == "ran: ls", repr(result)
    finally:
        db.close()


def test_execute_shell_command_none_executor_returns_not_available(tmp_path):
    """R5 guard: execute_shell_command with shell_executor=None returns the exact sentinel."""
    db = ConversationDB(str(tmp_path))
    try:
        result = execute_builtin_tool(
            db, "execute_shell_command", {"command": "ls"}, shell_executor=None
        )
        assert result == (
            "Error: Shell command execution not available in this context."
            " Use the TUI shell mode."
        ), repr(result)
    finally:
        db.close()


def test_show_conversation_tree_prefers_executor(tmp_path):
    """R5 guard: show_conversation_tree prefers shell_executor when present."""
    from collections import namedtuple

    FakeResult = namedtuple("FakeResult", ["output", "success", "error"])

    def fake_executor(cmd):
        return FakeResult(output=f"tree-output:{cmd}", success=True, error="")

    db = ConversationDB(str(tmp_path))
    try:
        result = execute_builtin_tool(
            db,
            "show_conversation_tree",
            {"conversation_id": "abc123"},
            shell_executor=fake_executor,
        )
        assert result == "tree-output:tree abc123", repr(result)
    finally:
        db.close()


def test_show_conversation_tree_stub_fallback(tmp_path):
    """R5 guard: show_conversation_tree falls back to stub when shell_executor=None."""
    db = ConversationDB(str(tmp_path))
    try:
        conv_id = "aaaabbbb-0000-0000-0000-000000000000"
        tree = ConversationTree(id=conv_id, title="My Chat")
        tree.add_message(
            Message(
                id="m1",
                role=MessageRole.USER,
                content=MessageContent(text="hello"),
                parent_id=None,
            )
        )
        db.save_conversation(tree)

        result = execute_builtin_tool(
            db,
            "show_conversation_tree",
            {"conversation_id": conv_id},
            shell_executor=None,
        )
        assert result == (
            "Tree for My Chat:\n(Use TUI shell mode for full tree visualization)"
        ), repr(result)
    finally:
        db.close()


def test_search_conversations_in_builtin_tool_names():
    """R1 guard (name): search_conversations must be registered in builtin_tool_names()."""
    assert "search_conversations" in builtin_tool_names()


def test_search_conversations_match_returns_found_prefix(tmp_path):
    """R1 guard: matching search returns 'Found N ...' string, NEVER the empty sentinel."""
    import uuid

    db = ConversationDB(str(tmp_path))
    try:
        tree = ConversationTree(id=str(uuid.uuid4()), title="Python tutorial")
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="python functions"),
                parent_id=None,
            )
        )
        db.save_conversation(tree)

        result = execute_builtin_tool(
            db, "search_conversations", {"query": "python"}, use_rich=False
        )
        assert result != "", "empty sentinel must be gone"
        assert result.startswith("Found "), repr(result)
    finally:
        db.close()


def test_search_conversations_empty_returns_no_found(tmp_path):
    """R1 guard: empty-result search returns exact sentinel, NEVER the empty string."""
    db = ConversationDB(str(tmp_path))
    try:
        result = execute_builtin_tool(
            db,
            "search_conversations",
            {"query": "xyzzy-no-match-ever"},
            use_rich=False,
        )
        assert result != "", "empty string sentinel must be gone"
        assert result == "No conversations found.", repr(result)
    finally:
        db.close()


def test_search_conversations_use_rich_true_also_returns_string(tmp_path):
    """R1 guard: use_rich=True no longer prints or returns '' -- returns plain string."""
    import uuid

    db = ConversationDB(str(tmp_path))
    try:
        tree = ConversationTree(id=str(uuid.uuid4()), title="Rich test conv")
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="rich render check"),
                parent_id=None,
            )
        )
        db.save_conversation(tree)

        result = execute_builtin_tool(
            db, "search_conversations", {"query": "rich render"}, use_rich=True
        )
        # The dead use_rich=True stdout path is gone: result must be non-empty string
        assert result != "", "empty sentinel must be gone even with use_rich=True"
        assert result.startswith("Found "), repr(result)
    finally:
        db.close()


def test_builtin_provider_wired_into_registry():
    """R6: importing builtin_tools registers the ctk.builtin provider.

    The provider must own the builtin tool names (routing derives from
    ownership) and expose exactly the 27 migrated tools.
    """
    import ctk.core.builtin_tools  # noqa: F401  (registers the provider on import)
    from ctk.core.tools_registry import iter_providers, provider_for_tool

    assert provider_for_tool("search_conversations") == "ctk.builtin"

    builtin = [p for p in iter_providers() if p.name == "ctk.builtin"]
    assert len(builtin) == 1, "ctk.builtin provider must be registered exactly once"
    assert len(builtin[0].tools) == 27
