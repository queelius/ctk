import pytest
from ctk.core.database import ConversationDB
from ctk.core.builtin_tools import execute_builtin_tool

pytestmark = pytest.mark.unit


def test_select_returns_table(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        out = execute_builtin_tool(db, "execute_sql", {"sql": "SELECT 1 AS one"})
        assert "one" in out and "1" in out and not out.startswith("Error")
    finally:
        db.close()


def test_write_is_read_only_rejected(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        out = execute_builtin_tool(
            db,
            "execute_sql",
            {"sql": "CREATE TABLE x (a INTEGER)"},
        )
        # read-only DB rejects writes with the exact friendly message
        assert "Only SELECT queries are allowed (database is read-only)." in out
    finally:
        db.close()


def test_missing_sql_errors(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        assert execute_builtin_tool(db, "execute_sql", {}).startswith("Error")
    finally:
        db.close()
