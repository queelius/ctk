"""
Unit tests for CTKImporter: lossless round-trip of the canonical JSON export.
"""

import json

import pytest

from ctk.core.models import (
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
    ReasoningBlock,
)
from ctk.core.plugin import registry


def _rich_tree():
    tree = ConversationTree(id="rt-1", title="RT Title")
    tree.metadata.source = "test"
    tree.add_message(
        Message(
            id="u1",
            role=MessageRole.USER,
            content=MessageContent(text="Q"),
            parent_id=None,
        )
    )
    a1 = MessageContent(text="A-v1")
    a1.reasoning.append(ReasoningBlock(text="thinking", summary="Plan"))
    a1.add_tool_call(name="calc", arguments={"x": 1}, tool_id="t1")
    tree.add_message(
        Message(id="a1", role=MessageRole.ASSISTANT, content=a1, parent_id="u1")
    )
    tree.add_message(
        Message(
            id="a2",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="A-v2"),
            parent_id="u1",
        )
    )
    return tree


def _export_ctk(tree) -> str:
    registry.discover_plugins()
    return registry.get_exporter("json").export_conversations([tree])


class TestCTKImporterAutoDetect:
    """Tests for auto-detect routing of CTK envelope to CTKImporter."""

    @pytest.mark.unit
    def test_auto_detect_routes_ctk_envelope_to_ctk_importer(self):
        """auto_detect_importer must return the ctk importer for ctk-format JSON."""
        parsed = json.loads(_export_ctk(_rich_tree()))
        registry.discover_plugins()
        importer = registry.auto_detect_importer(parsed)
        assert importer is not None and importer.name == "ctk"


class TestCTKImporterRoundTrip:
    """Tests for lossless round-trip via CTKImporter."""

    @pytest.mark.unit
    def test_ctk_export_reimports_to_equal_tree(self):
        """Importing a CTK export reproduces an identical ConversationTree."""
        original = _rich_tree()
        parsed = json.loads(_export_ctk(original))
        importer = registry.get_importer("ctk")
        restored = importer.import_data(parsed)[0]

        assert restored.id == original.id
        assert restored.title == original.title
        assert set(restored.message_map) == set(original.message_map)
        assert restored.root_message_ids == original.root_message_ids
        for mid, orig in original.message_map.items():
            got = restored.message_map[mid]
            assert got.parent_id == orig.parent_id
            assert got.role == orig.role
            assert got.content.text == orig.content.text
        a1 = restored.message_map["a1"].content
        assert len(a1.reasoning) == 1 and a1.reasoning[0].summary == "Plan"
        assert len(a1.tool_calls) == 1 and a1.tool_calls[0].name == "calc"
        assert len(restored.get_all_paths()) == 2

    @pytest.mark.unit
    def test_ctk_importer_accepts_string_input(self):
        """CTKImporter.validate and import_data both accept a raw JSON string."""
        raw = _export_ctk(_rich_tree())
        importer = registry.get_importer("ctk")
        assert importer.validate(raw)
        assert len(importer.import_data(raw)) == 1


class TestCTKImporterRobustness:
    """Tests that CTKImporter skips bad entries and keeps valid ones."""

    @pytest.mark.unit
    def test_non_dict_entries_skipped_valid_ones_survive(self):
        valid = json.loads(_export_ctk(_rich_tree()))["conversations"][0]
        envelope = {"format": "ctk", "conversations": ["garbage", None, valid, 42]}
        importer = registry.get_importer("ctk")
        trees = importer.import_data(envelope)
        assert len(trees) == 1
        assert trees[0].id == "rt-1"

    @pytest.mark.unit
    def test_malformed_message_timestamp_skips_only_that_conversation(self):
        valid = json.loads(_export_ctk(_rich_tree()))["conversations"][0]
        broken = json.loads(json.dumps(valid))
        broken["id"] = "broken-1"
        first_msg = next(iter(broken["messages"].values()))
        first_msg["timestamp"] = "not-a-date"
        envelope = {"format": "ctk", "conversations": [broken, valid]}
        importer = registry.get_importer("ctk")
        trees = importer.import_data(envelope)
        assert [t.id for t in trees] == ["rt-1"]
