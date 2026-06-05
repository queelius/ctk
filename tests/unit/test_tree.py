"""
Unit tests for ctk/core/tree.py.

Covers:
- TreeMessage: construction, parent-child linking, path-to-root, depth, is_leaf,
  format_tree, format_message, print_message, __repr__
- ConversationTreeNavigator: build_tree, get_all_paths, get_longest_path,
  get_latest_path, get_path, get_path_count, get_all_leaves, has_branches,
  format_path_summary, format_path, format_tree, print_tree, print_path,
  print_path_summary, to_conversation_tree
- Edge cases: empty tree, single node, linear chain, branching tree, orphan detection
"""

from __future__ import annotations

import time
from datetime import datetime
from io import StringIO
from typing import List
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.core.tree import ConversationTreeNavigator, TreeMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_msg(mid: str, parent: str | None = None, role: MessageRole = MessageRole.USER,
             text: str = "", metadata: dict | None = None) -> Message:
    """Build a Message with an explicit id for deterministic tests."""
    return Message(
        id=mid,
        parent_id=parent,
        role=role,
        content=MessageContent(text=text or mid),
        metadata=metadata or {},
    )


def _linear_tree(ids: list[str]) -> ConversationTree:
    """Create a ConversationTree with a single linear chain of messages."""
    tree = ConversationTree()
    parent: str | None = None
    for mid in ids:
        tree.add_message(_db_msg(mid, parent=parent))
        parent = mid
    return tree


def _branching_tree() -> ConversationTree:
    """Create a ConversationTree with this shape:
        a
        b (child of a)
        c (child of b)  d (child of b)
    Paths: a->b->c  and  a->b->d
    """
    tree = ConversationTree()
    tree.add_message(_db_msg("a"))
    tree.add_message(_db_msg("b", parent="a"))
    tree.add_message(_db_msg("c", parent="b"))
    tree.add_message(_db_msg("d", parent="b"))
    return tree


def _deep_branching_tree() -> ConversationTree:
    """Create a deeper tree:
        root
        |- left  -> left2
        |- right -> right2 -> right3
    """
    tree = ConversationTree()
    tree.add_message(_db_msg("root"))
    tree.add_message(_db_msg("left", parent="root"))
    tree.add_message(_db_msg("left2", parent="left"))
    tree.add_message(_db_msg("right", parent="root"))
    tree.add_message(_db_msg("right2", parent="right"))
    tree.add_message(_db_msg("right3", parent="right2"))
    return tree


def _navigator(tree: ConversationTree) -> ConversationTreeNavigator:
    return ConversationTreeNavigator(tree)


# ---------------------------------------------------------------------------
# TreeMessage direct construction tests
# ---------------------------------------------------------------------------

class TestTreeMessageConstruction:
    @pytest.mark.unit
    def test_basic_attributes(self):
        msg = TreeMessage(role=MessageRole.USER, content="hello")
        assert msg.content == "hello"
        assert msg.role is MessageRole.USER
        assert msg.parent is None
        assert msg.children == []
        assert msg.model is None
        assert msg.user is None
        assert isinstance(msg.id, str)
        assert len(msg.id) == 36  # UUID format

    @pytest.mark.unit
    def test_optional_metadata(self):
        msg = TreeMessage(role=MessageRole.ASSISTANT, content="reply",
                          model="gpt-4", user="alice")
        assert msg.model == "gpt-4"
        assert msg.user == "alice"

    @pytest.mark.unit
    def test_parent_child_linking(self):
        parent = TreeMessage(role=MessageRole.USER, content="question")
        child = TreeMessage(role=MessageRole.ASSISTANT, content="answer", parent=parent)
        assert child.parent is parent
        assert child in parent.children
        assert len(parent.children) == 1

    @pytest.mark.unit
    def test_multiple_children(self):
        root = TreeMessage(role=MessageRole.USER, content="root")
        c1 = TreeMessage(role=MessageRole.ASSISTANT, content="c1", parent=root)
        c2 = TreeMessage(role=MessageRole.ASSISTANT, content="c2", parent=root)
        assert len(root.children) == 2
        assert c1 in root.children
        assert c2 in root.children

    @pytest.mark.unit
    def test_timestamp_set(self):
        before = datetime.now()
        msg = TreeMessage(role=MessageRole.USER, content="t")
        after = datetime.now()
        assert before <= msg.timestamp <= after

    @pytest.mark.unit
    def test_metadata_dict_initialized(self):
        msg = TreeMessage(role=MessageRole.USER, content="x")
        assert isinstance(msg.metadata, dict)

    @pytest.mark.unit
    def test_repr_contains_id_and_role(self):
        msg = TreeMessage(role=MessageRole.USER, content="hi")
        r = repr(msg)
        assert msg.id[:8] in r
        assert "user" in r


# ---------------------------------------------------------------------------
# TreeMessage navigation methods
# ---------------------------------------------------------------------------

class TestTreeMessageNavigation:
    @pytest.mark.unit
    def test_get_path_to_root_single(self):
        msg = TreeMessage(role=MessageRole.USER, content="only")
        path = msg.get_path_to_root()
        assert path == [msg]

    @pytest.mark.unit
    def test_get_path_to_root_chain(self):
        a = TreeMessage(role=MessageRole.USER, content="a")
        b = TreeMessage(role=MessageRole.ASSISTANT, content="b", parent=a)
        c = TreeMessage(role=MessageRole.USER, content="c", parent=b)
        path = c.get_path_to_root()
        assert path == [a, b, c]

    @pytest.mark.unit
    def test_get_depth_root(self):
        msg = TreeMessage(role=MessageRole.USER, content="root")
        assert msg.get_depth() == 0

    @pytest.mark.unit
    def test_get_depth_chain(self):
        a = TreeMessage(role=MessageRole.USER, content="a")
        b = TreeMessage(role=MessageRole.ASSISTANT, content="b", parent=a)
        c = TreeMessage(role=MessageRole.USER, content="c", parent=b)
        assert a.get_depth() == 0
        assert b.get_depth() == 1
        assert c.get_depth() == 2

    @pytest.mark.unit
    def test_is_leaf_no_children(self):
        msg = TreeMessage(role=MessageRole.USER, content="leaf")
        assert msg.is_leaf() is True

    @pytest.mark.unit
    def test_is_leaf_with_child(self):
        parent = TreeMessage(role=MessageRole.USER, content="parent")
        TreeMessage(role=MessageRole.ASSISTANT, content="child", parent=parent)
        assert parent.is_leaf() is False


# ---------------------------------------------------------------------------
# TreeMessage formatting methods
# ---------------------------------------------------------------------------

class TestTreeMessageFormatting:
    @pytest.mark.unit
    def test_format_message_no_index(self):
        msg = TreeMessage(role=MessageRole.USER, content="hello world")
        text = msg.format_message()
        assert "USER" in text
        assert "hello world" in text

    @pytest.mark.unit
    def test_format_message_with_index(self):
        msg = TreeMessage(role=MessageRole.USER, content="hello world")
        text = msg.format_message(index=3)
        assert "[3]" in text
        assert "USER" in text

    @pytest.mark.unit
    def test_format_message_with_metadata(self):
        msg = TreeMessage(role=MessageRole.ASSISTANT, content="reply",
                          model="gpt-4", user="bob")
        text = msg.format_message(show_metadata=True)
        assert "model: gpt-4" in text
        assert "user: bob" in text

    @pytest.mark.unit
    def test_format_message_no_metadata_when_absent(self):
        msg = TreeMessage(role=MessageRole.USER, content="hi")
        text = msg.format_message(show_metadata=True)
        assert "model:" not in text
        assert "user:" not in text

    @pytest.mark.unit
    def test_format_tree_single_node(self):
        msg = TreeMessage(role=MessageRole.USER, content="root")
        text = msg.format_tree()
        assert "U" in text  # First letter of "user"

    @pytest.mark.unit
    def test_format_tree_with_children(self):
        root = TreeMessage(role=MessageRole.USER, content="root")
        TreeMessage(role=MessageRole.ASSISTANT, content="child", parent=root)
        text = root.format_tree()
        assert "U" in text
        assert "A" in text

    @pytest.mark.unit
    def test_format_tree_truncates_content(self):
        long_content = "x" * 100
        msg = TreeMessage(role=MessageRole.USER, content=long_content)
        text = msg.format_tree(max_content_length=10)
        assert "..." in text

    @pytest.mark.unit
    def test_format_tree_empty_content(self):
        msg = TreeMessage(role=MessageRole.USER, content="")
        # Should not raise
        text = msg.format_tree()
        assert isinstance(text, str)

    @pytest.mark.unit
    def test_print_message_user_role(self, capsys):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.USER, content="hello")
        msg.print_message(console=console)
        # No exception raised is the primary assertion

    @pytest.mark.unit
    def test_print_message_assistant_role(self):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.ASSISTANT, content="reply")
        msg.print_message(console=console)

    @pytest.mark.unit
    def test_print_message_system_role(self):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.SYSTEM, content="system prompt")
        msg.print_message(console=console)

    @pytest.mark.unit
    def test_print_message_tool_role(self):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.TOOL, content="tool output")
        msg.print_message(console=console)

    @pytest.mark.unit
    def test_print_message_with_markdown(self):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.ASSISTANT, content="```python\nprint('hi')\n```")
        msg.print_message(console=console, render_markdown=True)

    @pytest.mark.unit
    def test_print_message_metadata(self):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.ASSISTANT, content="reply",
                          model="gpt-4", user="alice")
        msg.print_message(console=console, show_metadata=True)

    @pytest.mark.unit
    def test_print_message_no_render_markdown(self):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.ASSISTANT, content="just text")
        msg.print_message(console=console, render_markdown=False)

    @pytest.mark.unit
    def test_print_message_with_index(self):
        console = Console(file=StringIO(), width=80, highlight=False)
        msg = TreeMessage(role=MessageRole.USER, content="hello")
        msg.print_message(console=console, index=5)


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: empty tree
# ---------------------------------------------------------------------------

class TestNavigatorEmptyTree:
    @pytest.mark.unit
    def test_empty_tree_no_root(self):
        tree = ConversationTree()
        nav = _navigator(tree)
        assert nav.root is None

    @pytest.mark.unit
    def test_empty_tree_no_message_map(self):
        tree = ConversationTree()
        nav = _navigator(tree)
        assert nav.message_map == {}

    @pytest.mark.unit
    def test_get_all_paths_empty(self):
        nav = _navigator(ConversationTree())
        assert nav.get_all_paths() == []

    @pytest.mark.unit
    def test_get_longest_path_empty(self):
        nav = _navigator(ConversationTree())
        assert nav.get_longest_path() == []

    @pytest.mark.unit
    def test_get_latest_path_empty(self):
        nav = _navigator(ConversationTree())
        assert nav.get_latest_path() == []

    @pytest.mark.unit
    def test_get_path_empty(self):
        nav = _navigator(ConversationTree())
        assert nav.get_path(0) is None

    @pytest.mark.unit
    def test_get_path_count_empty(self):
        nav = _navigator(ConversationTree())
        assert nav.get_path_count() == 0

    @pytest.mark.unit
    def test_get_all_leaves_empty(self):
        nav = _navigator(ConversationTree())
        assert nav.get_all_leaves() == []

    @pytest.mark.unit
    def test_has_branches_empty(self):
        nav = _navigator(ConversationTree())
        assert nav.has_branches() is False

    @pytest.mark.unit
    def test_format_path_summary_empty(self):
        nav = _navigator(ConversationTree())
        text = nav.format_path_summary()
        assert "No paths" in text

    @pytest.mark.unit
    def test_format_tree_empty(self):
        nav = _navigator(ConversationTree())
        text = nav.format_tree()
        assert "No messages" in text

    @pytest.mark.unit
    def test_print_tree_empty(self):
        nav = _navigator(ConversationTree())
        console = Console(file=StringIO(), width=80)
        nav.print_tree(console=console)

    @pytest.mark.unit
    def test_print_path_summary_empty(self):
        nav = _navigator(ConversationTree())
        console = Console(file=StringIO(), width=80)
        nav.print_path_summary(console=console)

    @pytest.mark.unit
    def test_to_conversation_tree_empty(self):
        tree = ConversationTree()
        nav = _navigator(tree)
        result = nav.to_conversation_tree()
        assert isinstance(result, ConversationTree)
        assert len(result.message_map) == 0


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: single node tree
# ---------------------------------------------------------------------------

class TestNavigatorSingleNode:
    @pytest.mark.unit
    def test_root_set(self):
        tree = _linear_tree(["only"])
        nav = _navigator(tree)
        assert nav.root is not None
        assert nav.root.id == "only"

    @pytest.mark.unit
    def test_message_map_populated(self):
        tree = _linear_tree(["only"])
        nav = _navigator(tree)
        assert "only" in nav.message_map

    @pytest.mark.unit
    def test_single_path(self):
        tree = _linear_tree(["only"])
        nav = _navigator(tree)
        paths = nav.get_all_paths()
        assert len(paths) == 1
        assert len(paths[0]) == 1
        assert paths[0][0].id == "only"

    @pytest.mark.unit
    def test_path_count_single(self):
        nav = _navigator(_linear_tree(["only"]))
        assert nav.get_path_count() == 1

    @pytest.mark.unit
    def test_longest_path_single(self):
        nav = _navigator(_linear_tree(["only"]))
        path = nav.get_longest_path()
        assert len(path) == 1
        assert path[0].id == "only"

    @pytest.mark.unit
    def test_latest_path_single(self):
        nav = _navigator(_linear_tree(["only"]))
        path = nav.get_latest_path()
        assert len(path) == 1
        assert path[0].id == "only"

    @pytest.mark.unit
    def test_leaf_is_root_for_single(self):
        nav = _navigator(_linear_tree(["only"]))
        leaves = nav.get_all_leaves()
        assert len(leaves) == 1
        assert leaves[0].id == "only"

    @pytest.mark.unit
    def test_no_branches_single(self):
        nav = _navigator(_linear_tree(["only"]))
        assert nav.has_branches() is False

    @pytest.mark.unit
    def test_get_path_valid_index(self):
        nav = _navigator(_linear_tree(["only"]))
        path = nav.get_path(0)
        assert path is not None
        assert path[0].id == "only"

    @pytest.mark.unit
    def test_get_path_invalid_index(self):
        nav = _navigator(_linear_tree(["only"]))
        assert nav.get_path(1) is None
        assert nav.get_path(-1) is None


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: linear (multi-node) tree
# ---------------------------------------------------------------------------

class TestNavigatorLinearTree:
    @pytest.mark.unit
    def test_root_is_first(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        assert nav.root.id == "a"

    @pytest.mark.unit
    def test_all_messages_in_map(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        assert set(nav.message_map.keys()) == {"a", "b", "c"}

    @pytest.mark.unit
    def test_single_path_for_linear(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        paths = nav.get_all_paths()
        assert len(paths) == 1
        assert [m.id for m in paths[0]] == ["a", "b", "c"]

    @pytest.mark.unit
    def test_longest_path_is_full_chain(self):
        nav = _navigator(_linear_tree(["a", "b", "c", "d"]))
        path = nav.get_longest_path()
        assert [m.id for m in path] == ["a", "b", "c", "d"]

    @pytest.mark.unit
    def test_leaf_is_last_in_chain(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        leaves = nav.get_all_leaves()
        assert len(leaves) == 1
        assert leaves[0].id == "c"

    @pytest.mark.unit
    def test_no_branches_linear(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        assert nav.has_branches() is False

    @pytest.mark.unit
    def test_parent_linking_correct(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        b_node = nav.message_map["b"]
        c_node = nav.message_map["c"]
        assert b_node.parent is nav.root
        assert c_node.parent is b_node

    @pytest.mark.unit
    def test_children_correct(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        a_node = nav.message_map["a"]
        b_node = nav.message_map["b"]
        assert len(a_node.children) == 1
        assert a_node.children[0] is b_node

    @pytest.mark.unit
    def test_path_to_root_leaf(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        c_node = nav.message_map["c"]
        path = c_node.get_path_to_root()
        assert [m.id for m in path] == ["a", "b", "c"]

    @pytest.mark.unit
    def test_format_path_summary_contains_count(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        summary = nav.format_path_summary()
        assert "Total paths: 1" in summary
        assert "3 messages" in summary

    @pytest.mark.unit
    def test_format_path_contains_messages(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        paths = nav.get_all_paths()
        text = nav.format_path(paths[0])
        # Each message id is the text content, so "a", "b", "c" should appear
        assert "a" in text
        assert "b" in text
        assert "c" in text

    @pytest.mark.unit
    def test_format_path_with_metadata(self):
        nav = _navigator(_linear_tree(["a", "b"]))
        paths = nav.get_all_paths()
        text = nav.format_path(paths[0], show_metadata=True)
        assert isinstance(text, str)

    @pytest.mark.unit
    def test_format_tree_linear(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        text = nav.format_tree()
        assert "=" * 10 in text

    @pytest.mark.unit
    def test_print_tree_linear(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        console = Console(file=StringIO(), width=80)
        nav.print_tree(console=console)

    @pytest.mark.unit
    def test_print_tree_custom_max_length(self):
        nav = _navigator(_linear_tree(["a", "b"]))
        console = Console(file=StringIO(), width=80)
        nav.print_tree(console=console, max_content_length=5)

    @pytest.mark.unit
    def test_print_tree_creates_console_if_none(self):
        nav = _navigator(_linear_tree(["a"]))
        # Should not raise when console is None
        nav.print_tree(console=None)

    @pytest.mark.unit
    def test_print_path_linear(self):
        nav = _navigator(_linear_tree(["a", "b"]))
        console = Console(file=StringIO(), width=80)
        path = nav.get_longest_path()
        nav.print_path(path, console=console)

    @pytest.mark.unit
    def test_print_path_no_console(self):
        nav = _navigator(_linear_tree(["a", "b"]))
        path = nav.get_longest_path()
        nav.print_path(path, console=None)

    @pytest.mark.unit
    def test_print_path_metadata(self):
        nav = _navigator(_linear_tree(["a", "b"]))
        console = Console(file=StringIO(), width=80)
        path = nav.get_longest_path()
        nav.print_path(path, console=console, show_metadata=True)

    @pytest.mark.unit
    def test_print_path_no_markdown(self):
        nav = _navigator(_linear_tree(["a", "b"]))
        console = Console(file=StringIO(), width=80)
        path = nav.get_longest_path()
        nav.print_path(path, console=console, render_markdown=False)

    @pytest.mark.unit
    def test_print_path_summary_linear(self):
        nav = _navigator(_linear_tree(["a", "b"]))
        console = Console(file=StringIO(), width=80)
        nav.print_path_summary(console=console)

    @pytest.mark.unit
    def test_print_path_summary_no_console(self):
        nav = _navigator(_linear_tree(["a"]))
        nav.print_path_summary(console=None)


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: branching tree
# ---------------------------------------------------------------------------

class TestNavigatorBranchingTree:
    @pytest.mark.unit
    def test_has_branches(self):
        nav = _navigator(_branching_tree())
        assert nav.has_branches() is True

    @pytest.mark.unit
    def test_path_count(self):
        nav = _navigator(_branching_tree())
        # a -> b -> c  and  a -> b -> d
        assert nav.get_path_count() == 2

    @pytest.mark.unit
    def test_all_paths_ids(self):
        nav = _navigator(_branching_tree())
        paths = nav.get_all_paths()
        path_ids = [tuple(m.id for m in p) for p in paths]
        assert ("a", "b", "c") in path_ids
        assert ("a", "b", "d") in path_ids

    @pytest.mark.unit
    def test_longest_path_length(self):
        nav = _navigator(_branching_tree())
        path = nav.get_longest_path()
        assert len(path) == 3

    @pytest.mark.unit
    def test_leaves(self):
        nav = _navigator(_branching_tree())
        leaf_ids = {m.id for m in nav.get_all_leaves()}
        assert leaf_ids == {"c", "d"}

    @pytest.mark.unit
    def test_root_is_a(self):
        nav = _navigator(_branching_tree())
        assert nav.root.id == "a"

    @pytest.mark.unit
    def test_get_path_both_branches(self):
        nav = _navigator(_branching_tree())
        p0 = nav.get_path(0)
        p1 = nav.get_path(1)
        assert p0 is not None
        assert p1 is not None
        ids0 = [m.id for m in p0]
        ids1 = [m.id for m in p1]
        all_ids = {tuple(ids0), tuple(ids1)}
        assert ("a", "b", "c") in all_ids
        assert ("a", "b", "d") in all_ids

    @pytest.mark.unit
    def test_get_path_out_of_range(self):
        nav = _navigator(_branching_tree())
        assert nav.get_path(2) is None

    @pytest.mark.unit
    def test_deep_longest_path(self):
        nav = _navigator(_deep_branching_tree())
        path = nav.get_longest_path()
        assert len(path) == 4  # root -> right -> right2 -> right3

    @pytest.mark.unit
    def test_deep_path_count(self):
        nav = _navigator(_deep_branching_tree())
        assert nav.get_path_count() == 2  # left branch + right branch

    @pytest.mark.unit
    def test_children_of_branching_node(self):
        nav = _navigator(_branching_tree())
        b_node = nav.message_map["b"]
        child_ids = {c.id for c in b_node.children}
        assert child_ids == {"c", "d"}

    @pytest.mark.unit
    def test_format_path_summary_shows_paths(self):
        nav = _navigator(_branching_tree())
        summary = nav.format_path_summary()
        assert "Total paths: 2" in summary

    @pytest.mark.unit
    def test_format_tree_branching(self):
        nav = _navigator(_branching_tree())
        text = nav.format_tree()
        assert "=" * 10 in text
        # Node a is the root, should appear at top of tree
        assert "a" in text


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: latest path (timestamp ordering)
# ---------------------------------------------------------------------------

class TestNavigatorLatestPath:
    @pytest.mark.unit
    def test_latest_path_picks_newer_leaf(self):
        """The path to the more recent leaf should be returned."""
        tree = ConversationTree()
        earlier = datetime(2024, 1, 1, 12, 0, 0)
        later = datetime(2024, 6, 1, 12, 0, 0)

        # Build tree with explicit timestamps
        root_msg = Message(
            id="root", parent_id=None, role=MessageRole.USER,
            content=MessageContent(text="root"), timestamp=earlier,
        )
        left_msg = Message(
            id="left", parent_id="root", role=MessageRole.ASSISTANT,
            content=MessageContent(text="left"), timestamp=earlier,
        )
        right_msg = Message(
            id="right", parent_id="root", role=MessageRole.ASSISTANT,
            content=MessageContent(text="right"), timestamp=later,
        )
        tree.add_message(root_msg)
        tree.add_message(left_msg)
        tree.add_message(right_msg)

        nav = _navigator(tree)
        path = nav.get_latest_path()
        assert path[-1].id == "right"

    @pytest.mark.unit
    def test_latest_path_single_leaf(self):
        nav = _navigator(_linear_tree(["a", "b", "c"]))
        path = nav.get_latest_path()
        assert path[-1].id == "c"


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: metadata propagation
# ---------------------------------------------------------------------------

class TestNavigatorMetadata:
    @pytest.mark.unit
    def test_model_metadata_extracted(self):
        tree = ConversationTree()
        msg = Message(
            id="m1", parent_id=None, role=MessageRole.ASSISTANT,
            content=MessageContent(text="hi"),
            metadata={"model": "gpt-4", "user": "alice"},
        )
        tree.add_message(msg)
        nav = _navigator(tree)
        node = nav.message_map["m1"]
        assert node.model == "gpt-4"
        assert node.user == "alice"

    @pytest.mark.unit
    def test_no_metadata_is_none(self):
        nav = _navigator(_linear_tree(["a"]))
        node = nav.message_map["a"]
        assert node.model is None
        assert node.user is None

    @pytest.mark.unit
    def test_timestamp_preserved(self):
        tree = ConversationTree()
        ts = datetime(2024, 3, 15, 9, 0, 0)
        msg = Message(
            id="m1", parent_id=None, role=MessageRole.USER,
            content=MessageContent(text="hi"), timestamp=ts,
        )
        tree.add_message(msg)
        nav = _navigator(tree)
        node = nav.message_map["m1"]
        assert node.timestamp == ts

    @pytest.mark.unit
    def test_role_preserved(self):
        tree = ConversationTree()
        tree.add_message(Message(
            id="sys", parent_id=None, role=MessageRole.SYSTEM,
            content=MessageContent(text="system"),
        ))
        nav = _navigator(tree)
        assert nav.message_map["sys"].role is MessageRole.SYSTEM


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: to_conversation_tree round-trip
# ---------------------------------------------------------------------------

class TestNavigatorToConversationTree:
    @pytest.mark.unit
    def test_round_trip_preserves_ids(self):
        original = _linear_tree(["a", "b", "c"])
        nav = _navigator(original)
        result = nav.to_conversation_tree()
        assert set(result.message_map.keys()) == {"a", "b", "c"}

    @pytest.mark.unit
    def test_round_trip_preserves_content(self):
        original = _linear_tree(["a", "b", "c"])
        nav = _navigator(original)
        result = nav.to_conversation_tree()
        # Content is set to the id in _linear_tree helper
        assert result.message_map["a"].content.text == "a"
        assert result.message_map["b"].content.text == "b"

    @pytest.mark.unit
    def test_round_trip_preserves_parent_links(self):
        original = _linear_tree(["a", "b", "c"])
        nav = _navigator(original)
        result = nav.to_conversation_tree()
        assert result.message_map["b"].parent_id == "a"
        assert result.message_map["c"].parent_id == "b"
        assert result.message_map["a"].parent_id is None

    @pytest.mark.unit
    def test_round_trip_preserves_conversation_id(self):
        original = ConversationTree(id="conv-123")
        original.add_message(_db_msg("a"))
        nav = _navigator(original)
        result = nav.to_conversation_tree()
        assert result.id == "conv-123"

    @pytest.mark.unit
    def test_round_trip_preserves_title(self):
        original = ConversationTree(id="x", title="My Chat")
        original.add_message(_db_msg("a"))
        nav = _navigator(original)
        result = nav.to_conversation_tree()
        assert result.title == "My Chat"

    @pytest.mark.unit
    def test_round_trip_branching(self):
        original = _branching_tree()
        nav = _navigator(original)
        result = nav.to_conversation_tree()
        # Both branches preserved
        assert "c" in result.message_map
        assert "d" in result.message_map
        assert result.message_map["c"].parent_id == "b"
        assert result.message_map["d"].parent_id == "b"

    @pytest.mark.unit
    def test_round_trip_with_model_metadata(self):
        tree = ConversationTree()
        tree.add_message(Message(
            id="m1", parent_id=None, role=MessageRole.ASSISTANT,
            content=MessageContent(text="hi"),
            metadata={"model": "gpt-4", "user": "alice"},
        ))
        nav = _navigator(tree)
        result = nav.to_conversation_tree()
        meta = result.message_map["m1"].metadata
        assert meta.get("model") == "gpt-4"
        assert meta.get("user") == "alice"

    @pytest.mark.unit
    def test_round_trip_no_metadata_empty_dict(self):
        nav = _navigator(_linear_tree(["a"]))
        result = nav.to_conversation_tree()
        # metadata should be empty dict when no model/user
        meta = result.message_map["a"].metadata
        assert isinstance(meta, dict)
        # model and user should not be present (or None)
        assert meta.get("model") is None or "model" not in meta

    @pytest.mark.unit
    def test_navigator_preserves_original_conversation(self):
        original = _linear_tree(["a", "b"])
        nav = _navigator(original)
        assert nav.conversation is original


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: orphan / disconnected message handling
# ---------------------------------------------------------------------------

class TestNavigatorOrphanMessages:
    @pytest.mark.unit
    def test_orphan_picks_earliest_as_root(self):
        """When there are multiple root candidates, the earliest timestamp wins."""
        tree = ConversationTree()
        # Two messages with no parent (both are orphans)
        early = Message(
            id="early", parent_id=None, role=MessageRole.USER,
            content=MessageContent(text="early"),
            timestamp=datetime(2024, 1, 1),
        )
        late = Message(
            id="late", parent_id=None, role=MessageRole.USER,
            content=MessageContent(text="late"),
            timestamp=datetime(2024, 6, 1),
        )
        tree.add_message(early)
        tree.add_message(late)
        nav = _navigator(tree)
        assert nav.root is not None
        assert nav.root.id == "early"

    @pytest.mark.unit
    def test_dangling_parent_id_treated_as_orphan(self):
        """A message whose parent_id references a non-existent id becomes orphan."""
        tree = ConversationTree()
        tree.add_message(Message(
            id="m1", parent_id="nonexistent", role=MessageRole.USER,
            content=MessageContent(text="orphan"),
        ))
        nav = _navigator(tree)
        # m1 should become root since its parent doesn't resolve
        assert nav.root is not None
        assert nav.root.id == "m1"


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: print_path_summary with roles
# ---------------------------------------------------------------------------

class TestNavigatorPrintPathSummaryRoles:
    @pytest.mark.unit
    def test_assistant_leaf_color_path(self):
        tree = ConversationTree()
        tree.add_message(_db_msg("q", role=MessageRole.USER, text="question"))
        tree.add_message(_db_msg("a", parent="q", role=MessageRole.ASSISTANT, text="answer"))
        nav = _navigator(tree)
        console = Console(file=StringIO(), width=80)
        nav.print_path_summary(console=console)

    @pytest.mark.unit
    def test_user_leaf_path_summary(self):
        tree = ConversationTree()
        tree.add_message(_db_msg("u", role=MessageRole.USER, text="query"))
        nav = _navigator(tree)
        console = Console(file=StringIO(), width=80)
        nav.print_path_summary(console=console)

    @pytest.mark.unit
    def test_system_leaf_path_summary(self):
        tree = ConversationTree()
        tree.add_message(_db_msg("s", role=MessageRole.SYSTEM, text="sys"))
        nav = _navigator(tree)
        console = Console(file=StringIO(), width=80)
        nav.print_path_summary(console=console)

    @pytest.mark.unit
    def test_long_content_preview_truncated(self):
        tree = ConversationTree()
        long_text = "x" * 200
        tree.add_message(Message(
            id="m1", parent_id=None, role=MessageRole.USER,
            content=MessageContent(text=long_text),
        ))
        nav = _navigator(tree)
        summary = nav.format_path_summary()
        assert "..." in summary


# ---------------------------------------------------------------------------
# ConversationTreeNavigator: roles in print_tree
# ---------------------------------------------------------------------------

class TestNavigatorPrintTreeRoles:
    @pytest.mark.unit
    def test_print_tree_assistant_role(self):
        tree = ConversationTree()
        tree.add_message(_db_msg("a", role=MessageRole.ASSISTANT, text="reply"))
        nav = _navigator(tree)
        console = Console(file=StringIO(), width=80)
        nav.print_tree(console=console)

    @pytest.mark.unit
    def test_print_tree_system_role(self):
        tree = ConversationTree()
        tree.add_message(_db_msg("s", role=MessageRole.SYSTEM, text="system"))
        nav = _navigator(tree)
        console = Console(file=StringIO(), width=80)
        nav.print_tree(console=console)

    @pytest.mark.unit
    def test_print_tree_tool_role(self):
        tree = ConversationTree()
        tree.add_message(_db_msg("t", role=MessageRole.TOOL, text="tool"))
        nav = _navigator(tree)
        console = Console(file=StringIO(), width=80)
        nav.print_tree(console=console)

    @pytest.mark.unit
    def test_print_tree_long_content_truncated(self):
        tree = ConversationTree()
        tree.add_message(Message(
            id="m1", parent_id=None, role=MessageRole.USER,
            content=MessageContent(text="x" * 200),
        ))
        nav = _navigator(tree)
        console = Console(file=StringIO(), width=80)
        nav.print_tree(console=console, max_content_length=10)
