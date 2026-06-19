import pytest
import ctk.core.builtin_tools  # noqa: F401  -- import registers the ctk.builtin provider
import ctk.core.network_tools  # noqa: F401  -- import registers the ctk.network provider
from ctk.core.tools_registry import provider_for_tool

pytestmark = pytest.mark.unit


def test_builtin_tool_resolves_to_builtin_provider():
    assert provider_for_tool("search_conversations") == "ctk.builtin"


def test_network_tool_resolves_to_network_provider():
    assert provider_for_tool("find_similar_conversations") == "ctk.network"
    assert provider_for_tool("list_neighbors") == "ctk.network"


def test_unknown_tool_resolves_to_none():
    assert provider_for_tool("does_not_exist") is None
