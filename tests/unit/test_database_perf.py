"""Performance guard: list_conversations must not issue N+1 queries."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import event

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)

pytestmark = pytest.mark.unit


def _seed(db, n, msgs_per=3):
    for i in range(n):
        tree = ConversationTree(
            id=str(uuid.uuid4()),
            title=f"conv {i}",
            metadata=ConversationMetadata(
                created_at=datetime.now(), updated_at=datetime.now()
            ),
        )
        parent = None
        for j in range(msgs_per):
            m = Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER if j % 2 == 0 else MessageRole.ASSISTANT,
                content=MessageContent(text=f"m{j}"),
                parent_id=parent,
                timestamp=datetime.now(),
            )
            tree.add_message(m)
            parent = m.id
        db.save_conversation(tree)


def test_list_conversations_is_not_n_plus_1(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _seed(db, 20, msgs_per=4)
        counter = {"n": 0}

        @event.listens_for(db.engine, "before_cursor_execute")
        def _count(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                counter["n"] += 1

        results = db.list_conversations(limit=20)
        assert len(results) == 20
        # Bounded, not ~1 + 20 + 20. Allow a small constant for the page +
        # one batched tag load + the message-count aggregate.
        assert (
            counter["n"] <= 6
        ), f"list_conversations issued {counter['n']} SELECTs (N+1)"
    finally:
        db.close()
