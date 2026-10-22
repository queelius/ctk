"""Regression tests for destructive / wrong-target `ctk db` path handling (2.20.1)."""

from argparse import Namespace

import pytest

from ctk.cli_db import cmd_info, cmd_init, resolve_db_path


@pytest.mark.unit
class TestInitForceIsScoped:
    def test_force_keeps_unrelated_files_in_db_dir(self, tmp_path):
        (tmp_path / "notes.txt").write_text("important")
        assert cmd_init(Namespace(path=str(tmp_path), force=False)) == 0

        assert cmd_init(Namespace(path=str(tmp_path), force=True)) == 0

        assert (tmp_path / "notes.txt").read_text() == "important"
        assert (tmp_path / "conversations.db").exists()

    def test_force_replaces_existing_database(self, tmp_path):
        from ctk.core.database import ConversationDB
        from ctk.core.models import ConversationTree

        with ConversationDB(str(tmp_path)) as db:
            db.save_conversation(ConversationTree(id="old", title="old"))

        assert cmd_init(Namespace(path=str(tmp_path), force=True)) == 0

        with ConversationDB(str(tmp_path)) as db:
            assert db.load_conversation("old") is None

    def test_force_on_foreign_db_filename_is_refused(self, tmp_path):
        (tmp_path / "notes.txt").write_text("important")
        (tmp_path / "mydata.db").write_text("not ours")

        assert cmd_init(Namespace(path=str(tmp_path / "mydata.db"), force=True)) == 1

        assert (tmp_path / "notes.txt").read_text() == "important"
        assert (tmp_path / "mydata.db").read_text() == "not ours"


@pytest.mark.unit
class TestResolveDbPath:
    def test_directory(self, tmp_path):
        assert resolve_db_path(str(tmp_path)) == (
            tmp_path,
            tmp_path / "conversations.db",
        )

    def test_conversations_db_file(self, tmp_path):
        assert resolve_db_path(str(tmp_path / "conversations.db")) == (
            tmp_path,
            tmp_path / "conversations.db",
        )

    def test_other_db_filename_rejected(self, tmp_path):
        # ConversationDB always opens <dir>/conversations.db, so accepting
        # <dir>/snap.db silently targets a different database.
        with pytest.raises(ValueError, match="conversations.db"):
            resolve_db_path(str(tmp_path / "snap.db"))

    def test_info_on_other_db_filename_fails_instead_of_reading_sibling(self, tmp_path):
        import shutil

        assert cmd_init(Namespace(path=str(tmp_path), force=False)) == 0
        shutil.copy(tmp_path / "conversations.db", tmp_path / "snap.db")  # a backup
        assert cmd_info(Namespace(path=str(tmp_path / "snap.db"), json=True)) == 1
