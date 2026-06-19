import uuid
from datetime import datetime
import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)

pytestmark = pytest.mark.unit


def _save_one(db):
    tree = ConversationTree(
        id=str(uuid.uuid4()),
        title="m",
        metadata=ConversationMetadata(
            created_at=datetime.now(), updated_at=datetime.now()
        ),
    )
    tree.add_message(
        Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text="x"),
            timestamp=datetime.now(),
        )
    )
    db.save_conversation(tree)
    return tree.id


def test_star_then_reload_reflects_flag(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        cid = _save_one(db)
        db.star_conversation(cid)
        loaded = db.load_conversation(cid)
        assert loaded.metadata.starred_at is not None
    finally:
        db.close()


def test_to_blob_holds_only_overflow():
    md = ConversationMetadata(
        created_at=datetime.now(),
        updated_at=datetime.now(),
        source="openai",
        model="gpt-4",
        custom_data={"k": "v"},
    )
    blob = md.to_blob()
    assert blob.get("custom_data") == {"k": "v"}
    # column-backed fields are NOT duplicated into the persistence blob
    assert "source" not in blob and "model" not in blob and "starred_at" not in blob


def test_to_dict_still_full_for_exporters():
    md = ConversationMetadata(
        created_at=datetime.now(),
        updated_at=datetime.now(),
        source="openai",
        model="gpt-4",
    )
    full = md.to_dict()
    assert full.get("source") == "openai" and full.get("model") == "gpt-4"


def test_version_format_survive_round_trip(tmp_path):
    """version and format must survive save/load even though blob no longer carries them."""
    db = ConversationDB(str(tmp_path))
    try:
        cid = str(uuid.uuid4())
        md = ConversationMetadata(
            created_at=datetime.now(),
            updated_at=datetime.now(),
            version="3.0.0",
            format="myformat",
        )
        tree = ConversationTree(id=cid, title="v-test", metadata=md)
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="hi"),
                timestamp=datetime.now(),
            )
        )
        db.save_conversation(tree)
        loaded = db.load_conversation(cid)
        assert loaded.metadata.version == "3.0.0"
        assert loaded.metadata.format == "myformat"
    finally:
        db.close()


def test_custom_data_survives_round_trip(tmp_path):
    """custom_data (the only blob field) must also survive save/load."""
    db = ConversationDB(str(tmp_path))
    try:
        cid = str(uuid.uuid4())
        md = ConversationMetadata(
            created_at=datetime.now(),
            updated_at=datetime.now(),
            custom_data={"foo": "bar", "num": 42},
        )
        tree = ConversationTree(id=cid, title="cd-test", metadata=md)
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="hi"),
                timestamp=datetime.now(),
            )
        )
        db.save_conversation(tree)
        loaded = db.load_conversation(cid)
        assert loaded.metadata.custom_data == {"foo": "bar", "num": 42}
    finally:
        db.close()
