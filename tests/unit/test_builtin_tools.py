import pytest
from ctk.core.database import ConversationDB
from ctk.core.builtin_tools import (  # noqa: F401
    BuiltinTool,
    ToolContext,
    ToolResult,
    builtin_tool_names,
    execute_builtin_tool,
)

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
