"""Versioned, SQLite-only schema migrations using PRAGMA user_version.

Each Migration carries a target version and an idempotent apply() that runs
under its own transaction; user_version advances only when a step commits.
Adding a schema change means appending a Migration, never editing an old one.
"""

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """Raised when a schema migration step fails; aborts loudly."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[Connection], None]


def _columns(conn: Connection, table: str) -> set:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _m1_slug_summary_index(conn: Connection) -> None:
    cols = _columns(conn, "conversations")
    if "slug" not in cols:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN slug VARCHAR"))
    if "summary" not in cols:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN summary TEXT"))
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_conv_slug ON conversations(slug)")
    )


def _m2_keyset_list_index(conn: Connection) -> None:
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_conv_list "
            "ON conversations(updated_at DESC, id) WHERE archived_at IS NULL"
        )
    )


MIGRATIONS: List[Migration] = [
    Migration(1, "slug_summary_index", _m1_slug_summary_index),
    Migration(2, "keyset_list_index", _m2_keyset_list_index),
]


def run_migrations(
    engine: Engine, generate_slugs: Optional[Callable[[], None]] = None
) -> None:
    """Apply pending migrations to a SQLite engine. No-op (warn) on other dialects."""
    if engine.dialect.name != "sqlite":
        logger.warning(
            "Schema migrations are SQLite-only; skipping on %s", engine.dialect.name
        )
        return

    with engine.connect() as conn:
        current = conn.execute(text("PRAGMA user_version")).scalar() or 0

    ran_any = False
    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        try:
            with engine.begin() as conn:
                migration.apply(conn)
                conn.execute(text(f"PRAGMA user_version = {migration.version}"))
        except Exception as exc:
            raise MigrationError(
                f"migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc
        logger.info("Applied migration %s (%s)", migration.version, migration.name)
        ran_any = True

    if ran_any and generate_slugs is not None:
        generate_slugs()
