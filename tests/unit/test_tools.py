"""
Tests for ctk.core.tools module.

Covers:
- get_ask_tools(): returns a non-empty, well-formed list of tool dicts
- is_pass_through_tool(): correctly identifies pass-through tools
"""

import pytest

from ctk.core.tools import get_ask_tools, is_pass_through_tool
from ctk.core.tools_registry import PASS_THROUGH_TOOLS, TOOLS_REGISTRY


# ==================== get_ask_tools ====================


class TestGetAskTools:
    """Tests for get_ask_tools()."""

    @pytest.mark.unit
    def test_returns_list(self):
        """get_ask_tools() should return a list."""
        result = get_ask_tools()
        assert isinstance(result, list)

    @pytest.mark.unit
    def test_non_empty(self):
        """get_ask_tools() should return at least one tool."""
        result = get_ask_tools()
        assert len(result) > 0

    @pytest.mark.unit
    def test_each_tool_is_dict(self):
        """Every item in the tool list should be a dict."""
        for tool in get_ask_tools():
            assert isinstance(tool, dict), f"Expected dict, got {type(tool)}"

    @pytest.mark.unit
    def test_each_tool_has_name(self):
        """Every tool should have a 'name' key with a non-empty string value."""
        for tool in get_ask_tools():
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert isinstance(tool["name"], str)
            assert len(tool["name"]) > 0

    @pytest.mark.unit
    def test_each_tool_has_description(self):
        """Every tool should have a 'description' key."""
        for tool in get_ask_tools():
            assert "description" in tool, f"Tool missing 'description': {tool['name']}"
            assert isinstance(tool["description"], str)

    @pytest.mark.unit
    def test_each_tool_has_input_schema(self):
        """Every tool should have an 'input_schema' key with a dict value."""
        for tool in get_ask_tools():
            assert (
                "input_schema" in tool
            ), f"Tool missing 'input_schema': {tool['name']}"
            assert isinstance(tool["input_schema"], dict)

    @pytest.mark.unit
    def test_input_schema_has_type_object(self):
        """Every tool's input_schema should declare type 'object'."""
        for tool in get_ask_tools():
            schema = tool["input_schema"]
            assert (
                schema.get("type") == "object"
            ), f"Tool '{tool['name']}' input_schema.type is not 'object'"

    @pytest.mark.unit
    def test_input_schema_has_required_list(self):
        """Every tool's input_schema should have a 'required' list."""
        for tool in get_ask_tools():
            schema = tool["input_schema"]
            assert (
                "required" in schema
            ), f"Tool '{tool['name']}' missing 'required' in schema"
            assert isinstance(schema["required"], list)

    @pytest.mark.unit
    def test_tool_names_are_unique(self):
        """All tool names across the registry should be unique."""
        tools = get_ask_tools()
        names = [t["name"] for t in tools]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    @pytest.mark.unit
    def test_include_pass_through_true_keeps_flag(self):
        """With include_pass_through=True, pass-through tools include the flag."""
        tools = get_ask_tools(include_pass_through=True)
        pass_through_tools = [t for t in tools if t.get("pass_through") is True]
        # At least some tools have pass_through=True
        assert len(pass_through_tools) > 0

    @pytest.mark.unit
    def test_include_pass_through_false_removes_flag(self):
        """With include_pass_through=False, no tool should have 'pass_through' key."""
        tools = get_ask_tools(include_pass_through=False)
        for tool in tools:
            assert (
                "pass_through" not in tool
            ), f"Tool '{tool['name']}' still has 'pass_through' key when excluded"

    @pytest.mark.unit
    def test_include_pass_through_false_same_count(self):
        """Excluding pass_through flag should not reduce the number of tools."""
        tools_with = get_ask_tools(include_pass_through=True)
        tools_without = get_ask_tools(include_pass_through=False)
        assert len(tools_with) == len(tools_without)

    @pytest.mark.unit
    def test_include_pass_through_false_preserves_names(self):
        """Excluding pass_through flag should keep all tool names identical."""
        names_with = {t["name"] for t in get_ask_tools(include_pass_through=True)}
        names_without = {t["name"] for t in get_ask_tools(include_pass_through=False)}
        assert names_with == names_without

    @pytest.mark.unit
    def test_known_builtin_tool_present(self):
        """The 'search_conversations' tool should always be present."""
        names = {t["name"] for t in get_ask_tools()}
        assert "search_conversations" in names

    @pytest.mark.unit
    def test_get_statistics_tool_present(self):
        """The 'get_statistics' tool should always be present."""
        names = {t["name"] for t in get_ask_tools()}
        assert "get_statistics" in names

    @pytest.mark.unit
    def test_get_conversation_tool_present(self):
        """The 'get_conversation' tool should always be present."""
        names = {t["name"] for t in get_ask_tools()}
        assert "get_conversation" in names

    @pytest.mark.unit
    def test_count_at_least_registry_size(self):
        """Tool count should be at least as large as TOOLS_REGISTRY (builtin always loaded)."""
        tools = get_ask_tools()
        assert len(tools) >= len(TOOLS_REGISTRY)


# ==================== is_pass_through_tool ====================


class TestIsPassThroughTool:
    """Tests for is_pass_through_tool()."""

    @pytest.mark.unit
    def test_known_pass_through_returns_true(self):
        """Tools in PASS_THROUGH_TOOLS should return True."""
        for name in PASS_THROUGH_TOOLS:
            assert (
                is_pass_through_tool(name) is True
            ), f"Expected {name!r} to be a pass-through tool"

    @pytest.mark.unit
    def test_unknown_tool_returns_false(self):
        """An unregistered tool name should return False."""
        assert is_pass_through_tool("nonexistent_tool_xyz") is False

    @pytest.mark.unit
    def test_empty_string_returns_false(self):
        """Empty string should return False."""
        assert is_pass_through_tool("") is False

    @pytest.mark.unit
    def test_non_pass_through_tool_returns_false(self):
        """A known tool that is NOT pass-through should return False."""
        # 'star_conversation' has no pass_through key in the registry
        assert is_pass_through_tool("star_conversation") is False

    @pytest.mark.unit
    def test_search_conversations_is_pass_through(self):
        """search_conversations is documented as pass-through."""
        assert is_pass_through_tool("search_conversations") is True

    @pytest.mark.unit
    def test_get_statistics_is_pass_through(self):
        """get_statistics is documented as pass-through."""
        assert is_pass_through_tool("get_statistics") is True

    @pytest.mark.unit
    def test_execute_shell_command_is_pass_through(self):
        """execute_shell_command is documented as pass-through."""
        assert is_pass_through_tool("execute_shell_command") is True

    @pytest.mark.unit
    def test_returns_bool(self):
        """is_pass_through_tool should return a bool, not a truthy value."""
        result = is_pass_through_tool("search_conversations")
        assert isinstance(result, bool)
        result_false = is_pass_through_tool("delete_conversation")
        assert isinstance(result_false, bool)
