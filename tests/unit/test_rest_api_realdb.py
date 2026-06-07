import pytest

pytest.importorskip("flask_cors")  # only runs where the rest extra is installed

from ctk.core.database import ConversationDB  # noqa: E402
from ctk.core.models import (  # noqa: E402
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.interfaces.rest.api import RestInterface  # noqa: E402


@pytest.fixture
def db_dir(tmp_path):
    db = ConversationDB(str(tmp_path / "db"))
    tree = ConversationTree(id="conv-1", title="Hello world")
    tree.metadata.source = "openai"
    tree.add_message(
        Message(
            id="m1",
            role=MessageRole.USER,
            content=MessageContent(text="hi"),
            parent_id=None,
        )
    )
    db.save_conversation(tree)
    db.close()
    return str(tmp_path / "db")


def test_list_conversations_uses_public_api(db_dir):
    iface = RestInterface(db_path=db_dir)
    resp = iface.list_conversations(limit=10, offset=0)
    # Must not raise AttributeError on db.session / db.ConversationModel.
    assert resp.status.value == "success" or resp.status == "success"
    titles = [c["title"] for c in resp.data["conversations"]]
    assert "Hello world" in titles


def test_update_conversation_uses_public_api(db_dir):
    iface = RestInterface(db_path=db_dir)
    resp = iface.update_conversation("conv-1", {"title": "Renamed"})
    assert "updated" in (resp.message or "").lower()


def test_export_conversations_uses_public_api(db_dir):
    iface = RestInterface(db_path=db_dir)
    # No conversation_ids: exercises the rewritten else-branch that previously
    # called the non-existent db.session / db._model_to_tree.
    resp = iface.export_conversations(output=None, format="json")
    assert resp.status.value == "success" or resp.status == "success"
    assert "export" in (resp.message or "").lower()


def test_list_multitag_total_matches_page(tmp_path):
    # Regression: a conversation carrying several of the filtered tags must be
    # counted once (count_conversations COUNT(DISTINCT id) and a DISTINCT page),
    # so the REST `total` matches the returned page instead of over-counting.
    db = ConversationDB(str(tmp_path / "db2"))
    tree = ConversationTree(id="c-multi", title="Multi tag")
    tree.metadata.tags = ["python", "ml", "data"]
    tree.add_message(
        Message(
            id="m1",
            role=MessageRole.USER,
            content=MessageContent(text="hi"),
            parent_id=None,
        )
    )
    db.save_conversation(tree)
    db.close()

    iface = RestInterface(db_path=str(tmp_path / "db2"))
    resp = iface.list_conversations(
        limit=10, offset=0, filters={"tags": ["python", "ml"]}
    )
    assert resp.status.value == "success" or resp.status == "success"
    convs = resp.data["conversations"]
    assert resp.data["total"] == len(convs) == 1
