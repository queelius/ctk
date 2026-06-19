import os
import sqlite3
import pytest

from ctk.core.database import ConversationDB
from ctk.core.db_discovery import discover_ctk_databases

pytestmark = pytest.mark.unit


def _make_ctk_db(dirpath):
    # ConversationDB creates conversations.db with the real schema.
    db = ConversationDB(str(dirpath))
    db.close()


def _make_non_ctk_sqlite(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    conn = sqlite3.connect(os.path.join(str(dirpath), "conversations.db"))
    conn.execute("CREATE TABLE not_ctk (id INTEGER)")
    conn.commit()
    conn.close()


def test_finds_only_valid_ctk_databases(tmp_path):
    good = tmp_path / "good"
    _make_ctk_db(good)
    bad = tmp_path / "bad"
    _make_non_ctk_sqlite(bad)
    (tmp_path / "empty").mkdir()

    found = discover_ctk_databases(str(tmp_path))
    assert os.path.abspath(str(good)) in found
    assert os.path.abspath(str(bad)) not in found
    assert len(found) == 1


def test_depth_bound(tmp_path):
    nested = tmp_path / "level1" / "deepdb"
    nested.mkdir(parents=True)
    _make_ctk_db(nested)  # two levels below tmp_path
    found = discover_ctk_databases(str(tmp_path), max_depth=1)
    assert os.path.abspath(str(nested)) not in found


def test_root_itself_counts(tmp_path):
    _make_ctk_db(tmp_path)
    found = discover_ctk_databases(str(tmp_path))
    assert os.path.abspath(str(tmp_path)) in found


def test_unreadable_candidate_is_skipped_not_raised(tmp_path):
    d = tmp_path / "garbage"
    d.mkdir()
    with open(d / "conversations.db", "wb") as fh:
        fh.write(b"this is not a sqlite file at all")
    # must not raise
    found = discover_ctk_databases(str(tmp_path))
    assert os.path.abspath(str(d)) not in found
