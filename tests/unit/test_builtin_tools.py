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


def test_migrated_builtin_schemas_match_registry():
    """Every migrated BuiltinTool must be byte-identical to its TOOLS_REGISTRY entry.

    During the strangler phase, this catches description/schema drift across all
    migration batches. At Task 9, TOOLS_REGISTRY is removed and a golden digest
    test takes over this role.
    """
    import ctk.core.builtin_tools as bt
    from ctk.core.tools_registry import TOOLS_REGISTRY

    registry = {t["name"]: t for t in TOOLS_REGISTRY}
    mismatches = []
    for tool in bt._BUILTIN_TOOLS:
        ref = registry.get(tool.name)
        assert ref is not None, f"{tool.name} not in TOOLS_REGISTRY"
        if tool.description != ref["description"]:
            mismatches.append(f"{tool.name}: description differs")
        if tool.input_schema != ref["input_schema"]:
            mismatches.append(f"{tool.name}: input_schema differs")
    assert not mismatches, mismatches
