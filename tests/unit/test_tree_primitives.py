"""Unit tests for ConversationTree primitives.

Six primitives form the algebra: ``delete_subtree``, ``prune_to``,
``copy``, ``copy_subtree``, ``graft`` (in-tree ops), and the DB-level
``delete_conversation`` (covered separately). Every TUI / CLI
operation on conversation trees ultimately reduces to a composition
of these.
"""

from __future__ import annotations

import pytest

from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)


def _msg(mid: str, parent: str | None = None, role: MessageRole = MessageRole.USER, text: str = "") -> Message:
    """Build a Message with explicit id + parent for deterministic tests."""
    return Message(
        id=mid,
        parent_id=parent,
        role=role,
        content=MessageContent(text=text or mid),
    )


def _linear(ids: list[str]) -> ConversationTree:
    """A tree with a single root-to-leaf chain in the given id order."""
    tree = ConversationTree()
    parent = None
    for mid in ids:
        tree.add_message(_msg(mid, parent=parent))
        parent = mid
    return tree


def _branching() -> ConversationTree:
    """A small tree with a branch:

        a
        └── b
            ├── c
            │   └── d
            └── e
                └── f
    """
    tree = ConversationTree()
    tree.add_message(_msg("a"))
    tree.add_message(_msg("b", parent="a"))
    tree.add_message(_msg("c", parent="b"))
    tree.add_message(_msg("d", parent="c"))
    tree.add_message(_msg("e", parent="b"))
    tree.add_message(_msg("f", parent="e"))
    return tree


# ---------------------------------------------------------------------------
# descendants_of / ancestors_of (helpers used by the primitives)
# ---------------------------------------------------------------------------


class TestDescendantsAndAncestors:
    @pytest.mark.unit
    def test_descendants_of_branching(self):
        tree = _branching()
        assert set(tree.descendants_of("b")) == {"c", "d", "e", "f"}
        assert set(tree.descendants_of("c")) == {"d"}
        assert tree.descendants_of("d") == []
        assert tree.descendants_of("missing") == []

    @pytest.mark.unit
    def test_ancestors_of_branching(self):
        tree = _branching()
        assert tree.ancestors_of("d") == ["c", "b", "a"]
        assert tree.ancestors_of("a") == []
        assert tree.ancestors_of("missing") == []


# ---------------------------------------------------------------------------
# delete_subtree
# ---------------------------------------------------------------------------


class TestDeleteSubtree:
    @pytest.mark.unit
    def test_delete_leaf_drops_one(self):
        tree = _linear(["a", "b", "c"])
        removed = tree.delete_subtree("c")
        assert removed == 1
        assert set(tree.message_map) == {"a", "b"}

    @pytest.mark.unit
    def test_delete_internal_drops_branch(self):
        tree = _branching()
        removed = tree.delete_subtree("e")
        # e and f gone; the c-d branch survives
        assert removed == 2
        assert set(tree.message_map) == {"a", "b", "c", "d"}

    @pytest.mark.unit
    def test_delete_root_drops_everything_and_clears_root_ids(self):
        tree = _branching()
        removed = tree.delete_subtree("a")
        assert removed == 6
        assert tree.message_map == {}
        assert tree.root_message_ids == []

    @pytest.mark.unit
    def test_delete_missing_raises(self):
        tree = _branching()
        with pytest.raises(KeyError):
            tree.delete_subtree("nope")

    @pytest.mark.unit
    def test_delete_invalidates_path_cache(self):
        tree = _branching()
        # Prime the cache
        tree.get_all_paths()
        assert tree._paths_cache is not None
        tree.delete_subtree("e")
        assert tree._paths_cache is None


# ---------------------------------------------------------------------------
# prune_to
# ---------------------------------------------------------------------------


class TestPruneTo:
    @pytest.mark.unit
    def test_prune_to_leaf_keeps_chain(self):
        tree = _branching()
        removed = tree.prune_to("d")
        # Drops e, f (sibling branch) — keeps a, b, c, d
        assert removed == 2
        assert set(tree.message_map) == {"a", "b", "c", "d"}

    @pytest.mark.unit
    def test_prune_to_internal_drops_descendants(self):
        tree = _branching()
        removed = tree.prune_to("b")
        # Drops c, d, e, f — keeps a, b
        assert removed == 4
        assert set(tree.message_map) == {"a", "b"}

    @pytest.mark.unit
    def test_prune_to_root_keeps_only_root(self):
        tree = _branching()
        removed = tree.prune_to("a")
        assert removed == 5
        assert set(tree.message_map) == {"a"}
        assert tree.root_message_ids == ["a"]

    @pytest.mark.unit
    def test_prune_missing_raises(self):
        tree = _branching()
        with pytest.raises(KeyError):
            tree.prune_to("nope")

    @pytest.mark.unit
    def test_prune_invalidates_cache(self):
        tree = _branching()
        tree.get_all_paths()
        assert tree._paths_cache is not None
        tree.prune_to("b")
        assert tree._paths_cache is None


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------


class TestCopy:
    @pytest.mark.unit
    def test_copy_produces_new_id_by_default(self):
        tree = _branching()
        clone = tree.copy()
        assert clone.id != tree.id
        assert set(clone.message_map) == set(tree.message_map)

    @pytest.mark.unit
    def test_copy_can_preserve_id(self):
        tree = _branching()
        clone = tree.copy(new_id=False)
        assert clone.id == tree.id

    @pytest.mark.unit
    def test_copy_is_deep_independent(self):
        tree = _branching()
        clone = tree.copy()
        # Mutate the clone — original is untouched
        clone.delete_subtree("b")
        assert set(tree.message_map) == {"a", "b", "c", "d", "e", "f"}
        assert set(clone.message_map) == {"a"}

    @pytest.mark.unit
    def test_copy_metadata_is_independent(self):
        tree = _branching()
        tree.metadata.tags = ["original"]
        clone = tree.copy()
        clone.metadata.tags.append("clone")
        assert tree.metadata.tags == ["original"]
        assert clone.metadata.tags == ["original", "clone"]


# ---------------------------------------------------------------------------
# copy_subtree
# ---------------------------------------------------------------------------


class TestCopySubtree:
    @pytest.mark.unit
    def test_copy_subtree_root_becomes_new_root(self):
        tree = _branching()
        sub = tree.copy_subtree("e")
        # Just e and f survive; e's parent pointer is cleared
        assert set(sub.message_map) == {"e", "f"}
        assert sub.message_map["e"].parent_id is None
        assert sub.root_message_ids == ["e"]

    @pytest.mark.unit
    def test_copy_subtree_does_not_mutate_source(self):
        tree = _branching()
        before = set(tree.message_map)
        tree.copy_subtree("e")
        assert set(tree.message_map) == before

    @pytest.mark.unit
    def test_copy_subtree_gets_new_conv_id(self):
        tree = _branching()
        sub = tree.copy_subtree("b")
        assert sub.id != tree.id

    @pytest.mark.unit
    def test_copy_subtree_missing_raises(self):
        tree = _branching()
        with pytest.raises(KeyError):
            tree.copy_subtree("nope")


# ---------------------------------------------------------------------------
# graft
# ---------------------------------------------------------------------------


class TestGraft:
    @pytest.mark.unit
    def test_graft_attaches_under_parent(self):
        target = _linear(["a", "b"])
        donor = _linear(["x", "y"])
        added = target.graft("b", donor)
        # All of donor's nodes are added; donor's root is reparented to b
        assert added == 2
        # Original ids are gone; new uuids replace them. Find children of b.
        children_of_b = target.get_children("b")
        assert len(children_of_b) == 1
        # The grafted root should have donor's content
        grafted_root = children_of_b[0]
        assert grafted_root.content.get_text() == "x"

    @pytest.mark.unit
    def test_graft_preserves_donor(self):
        target = _linear(["a", "b"])
        donor = _linear(["x", "y"])
        donor_ids_before = set(donor.message_map)
        target.graft("b", donor)
        assert set(donor.message_map) == donor_ids_before

    @pytest.mark.unit
    def test_graft_remaps_internal_parent_pointers(self):
        target = _linear(["a", "b"])
        donor = _linear(["x", "y", "z"])
        target.graft("b", donor)
        # Walk from a leaf back through b — should find x (donor root)
        # whose parent is b, then x's child y, then y's child z.
        # We can't predict new ids, but the chain length and content
        # should be preserved.
        paths = target.get_all_paths()
        assert len(paths) == 1
        path_text = [m.content.get_text() for m in paths[0]]
        assert path_text == ["a", "b", "x", "y", "z"]

    @pytest.mark.unit
    def test_graft_missing_parent_raises(self):
        target = _linear(["a", "b"])
        donor = _linear(["x"])
        with pytest.raises(KeyError):
            target.graft("nope", donor)

    @pytest.mark.unit
    def test_graft_no_id_collisions(self):
        # Donor and target both use "a","b" — graft must not collide.
        target = _linear(["a", "b"])
        donor = _linear(["a", "b"])
        added = target.graft("b", donor)
        assert added == 2
        assert len(target.message_map) == 4  # a, b, plus 2 grafted under fresh ids


# ---------------------------------------------------------------------------
# Composition: derived ops in terms of primitives
# ---------------------------------------------------------------------------


class TestDerivedOps:
    """Check that the documented composites reduce correctly."""

    @pytest.mark.unit
    def test_fork_equals_copy_then_prune(self):
        """fork(n) = copy().prune_to(n)"""
        tree = _branching()
        forked = tree.copy()
        forked.prune_to("d")
        assert set(forked.message_map) == {"a", "b", "c", "d"}
        assert forked.id != tree.id
        # Source untouched
        assert set(tree.message_map) == {"a", "b", "c", "d", "e", "f"}

    @pytest.mark.unit
    def test_detach_equals_copy_subtree_then_delete(self):
        """detach(n) = copy_subtree(n) followed by delete_subtree(n)"""
        tree = _branching()
        extracted = tree.copy_subtree("e")
        tree.delete_subtree("e")
        assert set(extracted.message_map) == {"e", "f"}
        assert set(tree.message_map) == {"a", "b", "c", "d"}

    @pytest.mark.unit
    def test_promote_equals_prune_to_leaf(self):
        """promote_path(leaf) = prune_to(leaf)"""
        tree = _branching()
        # Pick the c→d path; promote it
        tree.prune_to("d")
        # Only the c-d ancestor chain remains
        assert set(tree.message_map) == {"a", "b", "c", "d"}
