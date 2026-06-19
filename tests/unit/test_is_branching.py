import uuid
from datetime import datetime
import pytest
from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)

pytestmark = pytest.mark.unit


def _linear(db):
    tree = ConversationTree(
        id=str(uuid.uuid4()),
        title="linear",
        metadata=ConversationMetadata(
            created_at=datetime.now(), updated_at=datetime.now()
        ),
    )
    p = None
    for j in range(3):
        m = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text=f"m{j}"),
            parent_id=p,
            timestamp=datetime.now(),
        )
        tree.add_message(m)
        p = m.id
    db.save_conversation(tree)
    return tree.id


def _branched(db):
    tree = ConversationTree(
        id=str(uuid.uuid4()),
        title="branched",
        metadata=ConversationMetadata(
            created_at=datetime.now(), updated_at=datetime.now()
        ),
    )
    root = Message(
        id=str(uuid.uuid4()),
        role=MessageRole.USER,
        content=MessageContent(text="root"),
        timestamp=datetime.now(),
    )
    tree.add_message(root)
    for j in range(2):  # two children of root -> branch
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.ASSISTANT,
                content=MessageContent(text=f"b{j}"),
                parent_id=root.id,
                timestamp=datetime.now(),
            )
        )
    db.save_conversation(tree)
    return tree.id


def test_is_branching_column_set_correctly(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        lin = _linear(db)
        br = _branched(db)
        with db.engine.connect() as conn:

            def flag(cid):
                return conn.execute(
                    text("SELECT is_branching FROM conversations WHERE id = :i"),
                    {"i": cid},
                ).scalar()

            assert not flag(lin)
            assert flag(br)
    finally:
        db.close()


def test_has_branches_filter_uses_column(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _linear(db)
        br = _branched(db)
        results = db.list_conversations(has_branches=True)
        ids = {r.id for r in results}
        assert br in ids
        assert all(r.id == br for r in results)
    finally:
        db.close()
