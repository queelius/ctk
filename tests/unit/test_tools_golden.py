import hashlib
import json

import pytest

import ctk.core.builtin_tools  # noqa: F401  -- import registers the ctk.builtin provider
from ctk.core.tools_registry import iter_providers

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# C1 baseline digest (captured 2026-06-19 before any handler migration).
#
# The view is {name, description, input_schema} for every tool in the
# ctk.builtin provider, sorted by name. pass_through is stripped so that
# the Task-4 list_conversations pass_through addition does not invalidate
# this guard. The digest must stay equal through Task 9 (the schemas move
# verbatim from TOOLS_REGISTRY into builtin_tools, so the re-registered
# provider produces the same bytes).
#
# If this fails and the change is intentional, re-run:
#   python -c "
#   import hashlib, json
#   from ctk.core.tools_registry import iter_providers
#   view = sorted(
#       ({'name': t['name'], 'description': t['description'],
#         'input_schema': t['input_schema']} for p in iter_providers()
#        if p.name == 'ctk.builtin' for t in p.tools),
#       key=lambda t: t['name'])
#   print(hashlib.sha256(json.dumps(view, sort_keys=True).encode()).hexdigest())
#   "
# and update _EXPECTED_DIGEST below.
# ---------------------------------------------------------------------------
_EXPECTED_DIGEST = "af510d8a88e918a135b55ce8bcf647ddd449bc89ec55c152475eea7f61f87651"

_EXPECTED_NAMES = [
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


def _builtin_schema_view():
    """Return the {name, description, input_schema} view of ctk.builtin, sorted."""
    for p in iter_providers():
        if p.name == "ctk.builtin":
            # Strip pass_through so the Task-4 list_conversations pass_through
            # addition does not invalidate this guard.
            return sorted(
                (
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "input_schema": t["input_schema"],
                    }
                    for t in p.tools
                ),
                key=lambda t: t["name"],
            )
    raise AssertionError("ctk.builtin provider not registered")


def test_builtin_schemas_are_byte_stable():
    """Guard the ctk.builtin tool schemas against drift across the C1 migration.

    Reads the registered ctk.builtin provider (not TOOLS_REGISTRY directly),
    so it is immune to test-ordering effects from ctk.network registration.
    Filtering to name == 'ctk.builtin' means network tools never inflate the
    count. The sha256 over {name, description, input_schema} catches any text
    change to a tool description or parameter spec. If the change is
    intentional, update _EXPECTED_DIGEST with the freshly computed value.
    """
    view = _builtin_schema_view()
    names = [t["name"] for t in view]

    assert len(names) == 26
    assert names == _EXPECTED_NAMES

    digest = hashlib.sha256(json.dumps(view, sort_keys=True).encode()).hexdigest()
    assert digest == _EXPECTED_DIGEST, (
        "ctk.builtin tool schemas drifted from the C1 baseline. If this change is "
        "intentional, update _EXPECTED_DIGEST; otherwise a batch copied a schema "
        "non-verbatim."
    )
