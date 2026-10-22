"""Regression tests: fluent QueryBuilder filters are never silently dropped (2.20.1)."""

import pytest

from ctk.api import CTK
from ctk.core.database import ConversationDB
from ctk.core.models import ConversationTree

pytestmark = pytest.mark.unit


@pytest.fixture
def ctk(tmp_path):
    path = str(tmp_path / "db")
    with ConversationDB(path) as db:
        for conv_id in ("a", "b", "c", "d"):
            db.save_conversation(ConversationTree(id=conv_id, title=conv_id))
        db.star_conversation("b")
    return CTK(path)


def test_where_starred_counts_only_starred(ctk):
    assert ctk.conversations().where(starred=True).count() == 1
    assert ctk.conversations().where(starred=False).count() == 3


def test_delete_all_with_flag_filter_deletes_only_matches(ctk):
    deleted = ctk.conversations().where(starred=True).delete_all()

    assert deleted == 1
    assert sorted(c.id for c in ctk.conversations().get()) == ["a", "c", "d"]


def test_unknown_filter_key_raises(ctk):
    with pytest.raises(ValueError, match="nonsense"):
        ctk.conversations().where(nonsense=1)


def test_column_filter_still_works(ctk):
    assert [c.id for c in ctk.conversations().where(title="c").get()] == ["c"]
