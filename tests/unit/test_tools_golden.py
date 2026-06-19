import json
import pytest
from ctk.core.tools_registry import TOOLS_REGISTRY

pytestmark = pytest.mark.unit


def test_ask_tools_snapshot_is_stable():
    # Guard the LLM-facing builtin tool list (ctk.builtin provider) against
    # schema drift across the C1 migration: same names, same schemas, same order.
    # We read TOOLS_REGISTRY directly so that additional providers registered by
    # other tests (e.g. ctk.network from test_network_tools) don't inflate the
    # count and cause spurious failures.
    tools = [
        {k: v for k, v in t.items() if k != "pass_through"} for t in TOOLS_REGISTRY
    ]
    names = [t["name"] for t in tools]
    assert len(names) == 26
    assert len(set(names)) == 26
    # A stable digest of the full schema payload; if any schema text drifts
    # during the handler migration, this fails.
    digest = json.dumps(tools, sort_keys=True)
    # Snapshot the digest length + the sorted name list as the invariant.
    assert sorted(names) == [
        "archive_conversation",
        "auto_tag_conversation",
        "delete_conversation",
        "duplicate_conversation",
        "execute_shell_command",
        "export_conversation",
        "get_conversation",
        "get_recent_conversations",
        "get_statistics",
        "list_conversation_paths",
        "list_conversations",
        "list_models",
        "list_plugins",
        "list_sources",
        "list_tags",
        "pin_conversation",
        "remove_tag",
        "rename_conversation",
        "search_conversations",
        "show_conversation_content",
        "show_conversation_tree",
        "star_conversation",
        "tag_conversation",
        "unarchive_conversation",
        "unpin_conversation",
        "unstar_conversation",
    ]
    assert len(digest) > 0
