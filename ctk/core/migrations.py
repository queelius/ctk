"""Versioned, SQLite-only schema migrations using PRAGMA user_version.

Each Migration carries a target version and an idempotent apply() that runs
under its own transaction; user_version advances only when a step commits.
Adding a schema change means appending a Migration, never editing an old one.
"""

import logging
import sqlite3
from dataclasses import dataclass
from typing import Callable, List, Optional, cast

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ctk.core.constants import MIGRATION_LOCK_TIMEOUT

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


def _m4_rebuild_list_index(conn: Connection) -> None:
    conn.execute(text("DROP INDEX IF EXISTS idx_conv_list"))
    conn.execute(
        text(
            "CREATE INDEX idx_conv_list "
            "ON conversations(archived_at, updated_at DESC, id) "
            "WHERE archived_at IS NULL"
        )
    )


def _m3_is_branching(conn: Connection) -> None:
    cols = _columns(conn, "conversations")
    if "is_branching" not in cols:
        conn.execute(
            text("ALTER TABLE conversations ADD COLUMN is_branching BOOLEAN DEFAULT 0")
        )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_conv_is_branching ON conversations(is_branching)"
        )
    )


def _m5_normalize_timestamp_format(conn: Connection) -> None:
    # Rows stamped by the old func.now() defaults hold whole-second UTC text
    # ("YYYY-MM-DD HH:MM:SS"); ORM-written values carry ".ffffff". Keyset
    # cursors compare these as strings, so give every value the ORM format.
    for column in ("created_at", "updated_at"):
        conn.execute(
            text(
                f"UPDATE conversations SET {column} = {column} || '.000000' "
                f"WHERE length({column}) = 19"
            )
        )


MIGRATIONS: List[Migration] = [
    Migration(1, "slug_summary_index", _m1_slug_summary_index),
    Migration(2, "keyset_list_index", _m2_keyset_list_index),
    Migration(3, "is_branching_column", _m3_is_branching),
    Migration(4, "rebuild_list_index", _m4_rebuild_list_index),
    Migration(5, "normalize_timestamp_format", _m5_normalize_timestamp_format),
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

    if _user_version(engine) >= max((m.version for m in MIGRATIONS), default=0):
        return

    ran_any = False
    for migration in MIGRATIONS:
        try:
            ran_any |= _apply_once(engine, migration)
        except Exception as exc:
            raise MigrationError(
                f"migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc

    if ran_any and generate_slugs is not None:
        generate_slugs()


def _user_version(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("PRAGMA user_version")).scalar() or 0


def _apply_once(engine: Engine, migration: Migration) -> bool:
    """Apply ``migration`` unless already applied, holding SQLite's write lock.

    ``BEGIN IMMEDIATE`` takes the database's single write lock before the
    version check, so concurrent processes serialize here and each step runs
    exactly once, with no OS-specific file lock. Waiting for that lock uses
    MIGRATION_LOCK_TIMEOUT rather than the connection's (shorter) busy timeout,
    since another process's migration can legitimately take a while. pysqlite's
    legacy mode opens transactions implicitly (and never before DDL), so the
    driver connection is switched to manual transaction control for the step.
    Both settings are restored afterwards.
    """
    with engine.connect() as conn:
        # run_migrations only proceeds on SQLite, so this is a sqlite3 connection.
        driver = cast(sqlite3.Connection, conn.connection.driver_connection)
        saved_isolation = driver.isolation_level
        saved_busy_ms = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        driver.isolation_level = None
        conn.exec_driver_sql(
            f"PRAGMA busy_timeout = {int(MIGRATION_LOCK_TIMEOUT * 1000)}"
        )
        try:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                current = conn.execute(text("PRAGMA user_version")).scalar() or 0
                if migration.version <= current:
                    conn.exec_driver_sql("ROLLBACK")
                    return False
                migration.apply(conn)
                conn.execute(text(f"PRAGMA user_version = {migration.version}"))
                conn.exec_driver_sql("COMMIT")
            except BaseException:
                conn.exec_driver_sql("ROLLBACK")
                raise
        finally:
            conn.exec_driver_sql(f"PRAGMA busy_timeout = {int(saved_busy_ms or 0)}")
            driver.isolation_level = saved_isolation
    logger.info("Applied migration %s (%s)", migration.version, migration.name)
    return True
