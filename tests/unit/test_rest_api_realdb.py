import pytest

pytest.importorskip("flask_cors")  # only runs where the rest extra is installed

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole,
)
from ctk.interfaces.rest.api import RestInterface


@pytest.fixture
def db_dir(tmp_path):
    db = ConversationDB(str(tmp_path / "db"))
    tree = ConversationTree(id="conv-1", title="Hello world")
    tree.metadata.source = "openai"
    tree.add_message(
        Message(id="m1", role=MessageRole.USER,
                content=MessageContent(text="hi"), parent_id=None)
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
