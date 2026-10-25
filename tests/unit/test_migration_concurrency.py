"""Migrations serialize through SQLite itself, so they need no OS file lock (2.20.2)."""

import subprocess
import sys
import threading
import time

import pytest
from sqlalchemy import create_engine, text

from ctk.core import migrations
from ctk.core.migrations import Migration, run_migrations

pytestmark = pytest.mark.unit


def test_database_module_imports_without_fcntl():
    """fcntl is Unix-only; importing it made ctk unusable on Windows."""
    code = "import sys; sys.modules['fcntl'] = None; import ctk.core.database"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_concurrent_runners_apply_each_migration_once(tmp_path, monkeypatch):
    db_file = tmp_path / "c.db"
    setup = create_engine(f"sqlite:///{db_file}")
    with setup.begin() as conn:
        conn.execute(text("CREATE TABLE applied (v INTEGER)"))

    def not_idempotent(conn):
        conn.execute(text("INSERT INTO applied VALUES (1)"))
        time.sleep(1.0)  # hold the write lock past the runners' busy timeout

    monkeypatch.setattr(
        migrations, "MIGRATIONS", [Migration(1, "once", not_idempotent)]
    )

    runners = 4
    barrier = threading.Barrier(runners)
    errors = []

    def runner():
        # A busy timeout shorter than the step: waiting must come from the
        # migration's own lock budget, not the connection's default.
        engine = create_engine(f"sqlite:///{db_file}", connect_args={"timeout": 0.5})
        barrier.wait()
        try:
            run_migrations(engine)
        except Exception as exc:  # collected and asserted below
            errors.append(exc)
        finally:
            engine.dispose()

    threads = [threading.Thread(target=runner) for _ in range(runners)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with setup.connect() as conn:
        applied = conn.execute(text("SELECT count(*) FROM applied")).scalar()
        version = conn.execute(text("PRAGMA user_version")).scalar()
    setup.dispose()

    assert errors == []
    assert (applied, version) == (1, 1)


def test_failed_step_rolls_back_and_keeps_version(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE applied (v INTEGER)"))

    def half_done(conn):
        conn.execute(text("INSERT INTO applied VALUES (1)"))
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "MIGRATIONS", [Migration(1, "bad", half_done)])

    with pytest.raises(migrations.MigrationError):
        run_migrations(engine)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM applied")).scalar() == 0
        assert conn.execute(text("PRAGMA user_version")).scalar() == 0
    engine.dispose()


def test_step_restores_connection_busy_timeout(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'c.db'}", connect_args={"timeout": 0.5}
    )
    monkeypatch.setattr(
        migrations, "MIGRATIONS", [Migration(1, "noop", lambda conn: None)]
    )
    run_migrations(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 500
    engine.dispose()
