"""
Read-only execution of user-supplied SQL.

``mode=ro`` alone is not enough: a read-only connection can still ``ATTACH``
the same file read-write, and ``PRAGMA query_only`` can be switched back off by
the next statement. Instead every connection handed to user SQL gets an
authorizer that allows only reads, plus a whitelist of introspection PRAGMAs.

SQLite consults the authorizer when a statement is prepared, so the connection
must be fresh (no cached statements); never install it on a pooled connection
that other code has used.
"""

import sqlite3
from typing import Optional

# PRAGMAs that take a table/index argument and only describe it.
_INTROSPECTION_PRAGMAS = frozenset(
    {
        "table_info",
        "table_xinfo",
        "table_list",
        "index_list",
        "index_info",
        "index_xinfo",
        "foreign_key_list",
    }
)

# PRAGMAs that read a setting; with an argument they would set it.
_READ_PRAGMAS = frozenset(
    {
        "user_version",
        "schema_version",
        "page_size",
        "page_count",
        "freelist_count",
        "compile_options",
        "database_list",
        "encoding",
    }
)

_ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_RECURSIVE,
    }
)

_DENIED_FUNCTIONS = frozenset({"load_extension"})

READ_ONLY_MESSAGE = "Only SELECT queries are allowed (database is read-only)."


def _authorize(
    action: int,
    arg1: Optional[str],
    arg2: Optional[str],
    db_name: Optional[str],
    trigger: Optional[str],
) -> int:
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        denied = (arg2 or "").lower() in _DENIED_FUNCTIONS
        return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA:
        name = (arg1 or "").lower()
        if name in _INTROSPECTION_PRAGMAS or (name in _READ_PRAGMAS and arg2 is None):
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def connect_read_only(db_file: str) -> sqlite3.Connection:
    """Open ``db_file`` read-only with the read-only authorizer installed."""
    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    conn.set_authorizer(_authorize)
    return conn


def is_read_only_violation(exc: BaseException) -> bool:
    """True if ``exc`` came from the authorizer or the read-only file mode."""
    message = str(exc).lower()
    return "not authorized" in message or "readonly" in message
