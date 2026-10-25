"""Regression tests: user-supplied SQL must be read-only and side-effect free (2.20.1)."""

from argparse import Namespace

import pytest

from ctk.core.builtin_tools import execute_builtin_tool
from ctk.core.database import ConversationDB
from ctk.core.models import ConversationTree

pytestmark = pytest.mark.unit

WRITES = [
    "DELETE FROM conversations",
    "UPDATE conversations SET title = 'x'",
    "CREATE TABLE x (a INTEGER)",
    "PRAGMA query_only = OFF",
    "PRAGMA writable_schema = ON",
]


@pytest.fixture
def db(tmp_path):
    db = ConversationDB(str(tmp_path / "db"))
    db.save_conversation(ConversationTree(id="c1", title="hello"))
    yield db
    db.close()


def _sql(db, sql, **extra):
    return execute_builtin_tool(db, "execute_sql", {"sql": sql, **extra})


class TestExecuteSqlTool:
    def test_db_stays_writable_after_execute_sql(self, db):
        _sql(db, "SELECT count(*) FROM conversations")

        db.star_conversation("c1")
        db.save_conversation(ConversationTree(id="c2", title="later"))

        assert db.load_conversation("c2") is not None

    @pytest.mark.parametrize("stmt", WRITES)
    def test_writes_rejected(self, db, stmt):
        out = _sql(db, stmt)
        assert "Only SELECT queries are allowed" in out
        assert db.load_conversation("c1").title == "hello"

    def test_attach_rejected_and_creates_no_file(self, db, tmp_path):
        target = tmp_path / "evil.db"
        out = _sql(db, f"ATTACH DATABASE '{target}' AS w")
        assert "Only SELECT queries are allowed" in out
        assert not target.exists()

    def test_qmark_params_bind(self, db):
        out = _sql(db, "SELECT title FROM conversations WHERE id = ?", params=["c1"])
        assert "hello" in out

    def test_colon_in_string_literal_is_not_a_bind_param(self, db):
        out = _sql(db, "SELECT 'a:b' AS v")
        assert "a:b" in out

    def test_introspection_pragma_allowed(self, db):
        out = _sql(db, "PRAGMA table_info(conversations)")
        assert "title" in out


class TestCliSql:
    def _args(self, db, query):
        return Namespace(
            db=str(db.db_dir),
            query=query,
            schema=False,
            interactive=False,
            format="table",
            limit=None,
        )

    def test_attach_then_delete_rejected(self, db, tmp_path):
        from ctk.cli import cmd_sql

        target = tmp_path / "evil.db"
        assert cmd_sql(self._args(db, f"ATTACH DATABASE '{target}' AS w")) == 1
        assert not target.exists()

    def test_select_works(self, db):
        from ctk.cli import cmd_sql

        assert cmd_sql(self._args(db, "SELECT id FROM conversations")) == 0


class TestReadOnlyConnection:
    def test_attach_of_live_db_cannot_delete(self, db):
        """`mode=ro` alone allowed ATTACHing the same file read-write."""
        import sqlite3

        from ctk.core.readonly_sql import connect_read_only

        conn = connect_read_only(db.db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute(f"ATTACH DATABASE '{db.db_path}' AS w")
        finally:
            conn.close()
        assert db.load_conversation("c1") is not None


class TestSlashSql:
    def test_attach_rejected(self, db, tmp_path):
        from types import SimpleNamespace

        from ctk.tui.slash import cmd_sql

        target = tmp_path / "evil.db"
        out = cmd_sql(SimpleNamespace(db=db), f"ATTACH DATABASE '{target}' AS w")
        assert out.startswith("SQL error")
        assert not target.exists()


class TestReadOnlyConnectionCompat:
    """2.20.2 follow-ups from an external review of the 2.20.1 authorizer."""

    def test_fts5_match_query_allowed(self, db):
        out = _sql(
            db,
            "SELECT count(*) AS n FROM conversations_fts "
            "WHERE conversations_fts MATCH 'hello'",
        )
        assert "SQL error" not in out and "not allowed" not in out, out

    @pytest.mark.parametrize("dirname", ["db#one", "db?mode=rwc", "db%41"])
    def test_uri_special_characters_in_path(self, tmp_path, dirname):
        special = ConversationDB(str(tmp_path / dirname))
        try:
            special.save_conversation(ConversationTree(id="c1", title="hello"))
            out = _sql(special, "SELECT title FROM conversations")
            assert "hello" in out, out
        finally:
            special.close()
        assert sorted(p.name for p in tmp_path.iterdir()) == [dirname]

    def test_fts5_vtable_schema_check_allowed_on_old_sqlite(self):
        """SQLite < 3.41 checks UPDATE on sqlite_master while building an FTS5 table.

        Newer SQLite skips the check, so the end-to-end MATCH test cannot see it
        here; it failed on CI's macOS Python 3.10 (SQLite 3.40).
        """
        import sqlite3

        from ctk.core.readonly_sql import _authorize

        for column in ("type", "name", "tbl_name", "rootpage", "sql"):
            verdict = _authorize(
                sqlite3.SQLITE_UPDATE, "sqlite_master", column, "main", None
            )
            assert verdict == sqlite3.SQLITE_OK
        assert (
            _authorize(sqlite3.SQLITE_UPDATE, "sqlite_master", "sql", "temp", None)
            == sqlite3.SQLITE_DENY
        )
        assert (
            _authorize(sqlite3.SQLITE_UPDATE, "conversations", "title", "main", None)
            == sqlite3.SQLITE_DENY
        )

    def test_user_update_of_schema_table_still_rejected(self, db):
        before = db.load_conversation("c1").title
        out = _sql(db, "UPDATE sqlite_master SET sql = '' WHERE name = 'conversations'")
        assert out.startswith(("SQL error", "Only SELECT")), out
        assert db.load_conversation("c1").title == before
        assert "hello" in _sql(db, "SELECT title FROM conversations")
