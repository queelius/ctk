"""The round-trip fidelity contract: one rich fixture must survive
(1) ctk JSON export then auto-detected re-import, and
(2) DB save then load,
with tree shape, roles, text, media, tool calls, and reasoning intact."""

import json

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ContentType,
    ConversationTree,
    MediaContent,
    Message,
    MessageContent,
    MessageRole,
    ReasoningBlock,
)
from ctk.core.plugin import registry


def _rich_fixture() -> ConversationTree:
    tree = ConversationTree(id="fid-1", title="Fidelity fixture")
    tree.metadata.source = "test"
    tree.metadata.tags = ["fidelity"]

    u1 = MessageContent(text="Question with media")
    u1.add_image(path="pic.png", mime_type="image/png")
    u1.audio.append(MediaContent(type=ContentType.AUDIO, path="clip.mp3"))
    u1.video.append(MediaContent(type=ContentType.VIDEO, path="movie.mp4"))
    u1.documents.append(
        MediaContent(
            type=ContentType.DOCUMENT, path="doc.pdf", mime_type="application/pdf"
        )
    )
    tree.add_message(
        Message(id="u1", role=MessageRole.USER, content=u1, parent_id=None)
    )

    a1 = MessageContent(text="Answer v1")
    a1.reasoning.append(
        ReasoningBlock(text="thinking hard", summary="Plan", extra={"budget": 1024})
    )
    tc = a1.add_tool_call(name="search", arguments={"q": "x"}, tool_id="t1")
    tc.result = "found it"
    tc.status = "completed"
    tree.add_message(
        Message(
            id="a1",
            role=MessageRole.ASSISTANT,
            content=a1,
            parent_id="u1",
            metadata={"k": "v"},
        )
    )

    tree.add_message(
        Message(
            id="a2",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Answer v2"),
            parent_id="u1",
        )
    )
    return tree


def _assert_equal_trees(got: ConversationTree, want: ConversationTree):
    assert got.id == want.id
    assert got.title == want.title
    assert set(got.message_map) == set(want.message_map)
    assert got.root_message_ids == want.root_message_ids
    assert len(got.get_all_paths()) == len(want.get_all_paths())
    for mid, w in want.message_map.items():
        g = got.message_map[mid]
        assert g.parent_id == w.parent_id, mid
        assert g.role == w.role, mid
        assert g.content.text == w.content.text, mid
        assert len(g.content.images) == len(w.content.images), mid
        assert len(g.content.audio) == len(w.content.audio), mid
        assert len(g.content.video) == len(w.content.video), mid
        assert len(g.content.documents) == len(w.content.documents), mid
        assert len(g.content.tool_calls) == len(w.content.tool_calls), mid
        for gt, wt in zip(g.content.tool_calls, w.content.tool_calls):
            assert (gt.id, gt.name, gt.result) == (wt.id, wt.name, wt.result)
        assert len(g.content.reasoning) == len(w.content.reasoning), mid
        for gr, wr in zip(g.content.reasoning, w.content.reasoning):
            assert (gr.text, gr.summary, gr.extra) == (wr.text, wr.summary, wr.extra)


class TestFidelityMatrixExportReimport:
    """Leg 1: ctk JSON export then auto-detected re-import must be lossless."""

    @pytest.mark.unit
    def test_ctk_export_then_autodetect_reimport_is_lossless(self):
        original = _rich_fixture()
        registry.discover_plugins()
        raw = registry.get_exporter("json").export_conversations([original])
        parsed = json.loads(raw)
        importer = registry.auto_detect_importer(parsed)
        assert importer is not None and importer.name == "ctk"
        _assert_equal_trees(importer.import_data(parsed)[0], original)


class TestFidelityMatrixDBRoundTrip:
    """Leg 2: DB save then load must be lossless."""

    @pytest.mark.unit
    def test_db_save_then_load_is_lossless(self):
        original = _rich_fixture()
        db = ConversationDB(":memory:")
        db.save_conversation(original)
        loaded = db.load_conversation("fid-1")
        assert loaded is not None
        _assert_equal_trees(loaded, original)
        db.close()
