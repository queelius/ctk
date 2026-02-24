"""
Unit tests for the FilesystemCoding importer.

Tests cover:
- Validation (path checking, agent detection)
- Agent type detection from path names and file presence
- Copilot import (SQLite databases, JSON files, row parsing, JSON parsing)
- Cursor import (SQLite with conversation tables, placeholder parser)
- Generic import (JSON file scanning, conversation detection heuristic)
- Placeholder methods (claude_code, codeium)
- Edge cases (corrupt databases, invalid JSON, unicode paths, empty directories)
"""

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from ctk.core.models import ConversationTree, MessageRole
from ctk.integrations.importers.filesystem_coding import \
    FilesystemCodingImporter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_db(db_path, table_name, columns, rows):
    """Create a test SQLite database with given table, columns, and rows."""
    col_defs = ", ".join(f"{c} TEXT" for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    conn = sqlite3.connect(str(db_path))
    conn.execute(f"CREATE TABLE {table_name} ({col_defs})")
    for row in rows:
        conn.execute(f"INSERT INTO {table_name} VALUES ({placeholders})", row)
    conn.commit()
    conn.close()


# ===========================================================================
# Validation tests
# ===========================================================================


class TestFilesystemCodingValidation:
    """Tests for FilesystemCodingImporter.validate()"""

    @pytest.mark.unit
    def test_validate_copilot_vscode_directory(self, tmp_path):
        """A directory whose path contains '.vscode' should validate as True."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer.validate(str(vscode_dir)) is True

    @pytest.mark.unit
    def test_validate_cursor_directory(self, tmp_path):
        """A directory whose path contains '.cursor' should validate as True."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer.validate(str(cursor_dir)) is True

    @pytest.mark.unit
    def test_validate_claude_code_directory(self, tmp_path):
        """A directory whose path contains '.claude' should validate as True."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer.validate(str(claude_dir)) is True

    @pytest.mark.unit
    def test_validate_codeium_directory(self, tmp_path):
        """A directory whose path contains '.codeium' should validate as True."""
        codeium_dir = tmp_path / ".codeium"
        codeium_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer.validate(str(codeium_dir)) is True

    @pytest.mark.unit
    def test_validate_path_with_copilot_db(self, tmp_path):
        """A directory containing copilot.db should validate as True."""
        # The directory path itself has no agent keyword, so detection falls
        # through to file-based checks.
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "copilot.db").touch()
        importer = FilesystemCodingImporter()
        assert importer.validate(str(agent_dir)) is True

    @pytest.mark.unit
    def test_validate_path_with_conversations_db(self, tmp_path):
        """A directory containing conversations.db should validate as True (cursor)."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "conversations.db").touch()
        importer = FilesystemCodingImporter()
        assert importer.validate(str(agent_dir)) is True

    @pytest.mark.unit
    def test_validate_path_with_chat_history_json(self, tmp_path):
        """A directory containing chat_history.json should validate as True (generic)."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "chat_history.json").write_text("{}")
        importer = FilesystemCodingImporter()
        assert importer.validate(str(agent_dir)) is True

    @pytest.mark.unit
    def test_validate_path_with_sessions_json(self, tmp_path):
        """A directory containing sessions.json should validate as True (generic)."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "sessions.json").write_text("{}")
        importer = FilesystemCodingImporter()
        assert importer.validate(str(agent_dir)) is True

    @pytest.mark.unit
    def test_validate_nonexistent_path(self, tmp_path):
        """A path that does not exist should return False."""
        importer = FilesystemCodingImporter()
        assert importer.validate(str(tmp_path / "does_not_exist")) is False

    @pytest.mark.unit
    def test_validate_file_not_directory(self, tmp_path):
        """A path that is a file (not a directory) should return False."""
        file_path = tmp_path / "somefile.txt"
        file_path.write_text("hello")
        importer = FilesystemCodingImporter()
        assert importer.validate(str(file_path)) is False

    @pytest.mark.unit
    def test_validate_non_string_data(self):
        """Non-string data should return False."""
        importer = FilesystemCodingImporter()
        assert importer.validate(12345) is False
        assert importer.validate(None) is False
        assert importer.validate(["/tmp"]) is False
        assert importer.validate({"path": "/tmp"}) is False

    @pytest.mark.unit
    def test_validate_very_long_string(self):
        """A string longer than 4096 characters should return False."""
        importer = FilesystemCodingImporter()
        long_string = "a" * 5000
        assert importer.validate(long_string) is False

    @pytest.mark.unit
    def test_validate_empty_directory_no_agent(self, tmp_path):
        """An empty directory with no agent indicators should return False."""
        empty_dir = tmp_path / "emptydata"
        empty_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer.validate(str(empty_dir)) is False

    @pytest.mark.unit
    def test_validate_empty_string(self):
        """An empty string should return False."""
        importer = FilesystemCodingImporter()
        assert importer.validate("") is False


# ===========================================================================
# Agent type detection tests
# ===========================================================================


class TestAgentTypeDetection:
    """Tests for FilesystemCodingImporter._detect_agent_type()"""

    @pytest.mark.unit
    def test_detect_copilot_from_vscode_path(self, tmp_path):
        """Path containing '.vscode' should detect as copilot."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(vscode_dir) == "copilot"

    @pytest.mark.unit
    def test_detect_copilot_from_copilot_keyword(self, tmp_path):
        """Path containing 'copilot' should detect as copilot."""
        copilot_dir = tmp_path / "copilot_data"
        copilot_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(copilot_dir) == "copilot"

    @pytest.mark.unit
    def test_detect_cursor_from_cursor_path(self, tmp_path):
        """Path containing '.cursor' should detect as cursor."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(cursor_dir) == "cursor"

    @pytest.mark.unit
    def test_detect_cursor_from_cursor_keyword(self, tmp_path):
        """Path containing 'cursor' (without dot) should detect as cursor."""
        cursor_dir = tmp_path / "cursor_sessions"
        cursor_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(cursor_dir) == "cursor"

    @pytest.mark.unit
    def test_detect_claude_code_from_claude_path(self, tmp_path):
        """Path containing '.claude' should detect as claude_code."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(claude_dir) == "claude_code"

    @pytest.mark.unit
    def test_detect_claude_code_from_claude_keyword(self, tmp_path):
        """Path containing 'claude' should detect as claude_code."""
        claude_dir = tmp_path / "claude_sessions"
        claude_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(claude_dir) == "claude_code"

    @pytest.mark.unit
    def test_detect_codeium_from_codeium_path(self, tmp_path):
        """Path containing '.codeium' should detect as codeium."""
        codeium_dir = tmp_path / ".codeium"
        codeium_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(codeium_dir) == "codeium"

    @pytest.mark.unit
    def test_detect_copilot_from_copilot_db_file(self, tmp_path):
        """Directory containing copilot.db should detect as copilot."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "copilot.db").touch()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(agent_dir) == "copilot"

    @pytest.mark.unit
    def test_detect_copilot_from_copilot_conversations_json(self, tmp_path):
        """Directory containing copilot_conversations.json should detect as copilot."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "copilot_conversations.json").write_text("[]")
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(agent_dir) == "copilot"

    @pytest.mark.unit
    def test_detect_cursor_from_conversations_db(self, tmp_path):
        """Directory containing conversations.db should detect as cursor."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "conversations.db").touch()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(agent_dir) == "cursor"

    @pytest.mark.unit
    def test_detect_cursor_from_cursor_db(self, tmp_path):
        """Directory containing cursor.db should detect as cursor."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "cursor.db").touch()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(agent_dir) == "cursor"

    @pytest.mark.unit
    def test_detect_generic_from_chat_history_json(self, tmp_path):
        """Directory containing chat_history.json should detect as generic."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "chat_history.json").write_text("{}")
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(agent_dir) == "generic"

    @pytest.mark.unit
    def test_detect_generic_from_sessions_json(self, tmp_path):
        """Directory containing sessions.json should detect as generic."""
        agent_dir = tmp_path / "myagentdata"
        agent_dir.mkdir()
        (agent_dir / "sessions.json").write_text("{}")
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(agent_dir) == "generic"

    @pytest.mark.unit
    def test_detect_unknown_path_returns_none(self, tmp_path):
        """A directory with no agent indicators should return None."""
        unknown_dir = tmp_path / "randomdata"
        unknown_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(unknown_dir) is None

    @pytest.mark.unit
    def test_detect_case_insensitive(self, tmp_path):
        """Detection should be case-insensitive (path is lowered)."""
        vscode_dir = tmp_path / ".VSCODE"
        vscode_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer._detect_agent_type(vscode_dir) == "copilot"


# ===========================================================================
# import_data dispatch tests
# ===========================================================================


class TestImportDataDispatch:
    """Tests for FilesystemCodingImporter.import_data() dispatch logic."""

    @pytest.mark.unit
    def test_import_dispatches_to_copilot(self, tmp_path):
        """import_data on a copilot path dispatches to _import_copilot."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()
        importer = FilesystemCodingImporter()
        result = importer.import_data(str(copilot_dir))
        assert isinstance(result, list)

    @pytest.mark.unit
    def test_import_dispatches_to_cursor(self, tmp_path):
        """import_data on a cursor path dispatches to _import_cursor."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        importer = FilesystemCodingImporter()
        result = importer.import_data(str(cursor_dir))
        assert isinstance(result, list)

    @pytest.mark.unit
    def test_import_dispatches_to_claude_code(self, tmp_path):
        """import_data on a claude path dispatches to _import_claude_code."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        importer = FilesystemCodingImporter()
        result = importer.import_data(str(claude_dir))
        assert result == []

    @pytest.mark.unit
    def test_import_dispatches_to_codeium(self, tmp_path):
        """import_data on a codeium path dispatches to _import_codeium."""
        codeium_dir = tmp_path / ".codeium"
        codeium_dir.mkdir()
        importer = FilesystemCodingImporter()
        result = importer.import_data(str(codeium_dir))
        assert result == []

    @pytest.mark.unit
    def test_import_dispatches_to_generic(self, tmp_path):
        """import_data on an unknown path dispatches to _import_generic."""
        unknown_dir = tmp_path / "randomdata"
        unknown_dir.mkdir()
        importer = FilesystemCodingImporter()
        result = importer.import_data(str(unknown_dir))
        assert isinstance(result, list)


# ===========================================================================
# Copilot import tests
# ===========================================================================


class TestCopilotImport:
    """Tests for _import_copilot, _parse_copilot_row, _parse_copilot_json."""

    @pytest.mark.unit
    def test_import_copilot_empty_directory(self, tmp_path):
        """An empty copilot directory should return an empty list."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()
        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert result == []

    @pytest.mark.unit
    def test_import_copilot_from_db_with_conversation_table(self, tmp_path):
        """A copilot.db with a 'conversations' table should produce ConversationTree objects."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()
        db_path = copilot_dir / "copilot_data.db"

        messages_json = json.dumps(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        )

        _create_test_db(
            db_path,
            "conversations",
            ["id", "title", "messages"],
            [("conv-1", "Test Chat", messages_json)],
        )

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)

        assert len(result) == 1
        conv = result[0]
        assert isinstance(conv, ConversationTree)
        assert conv.id == "conv-1"
        assert conv.title == "Test Chat"
        assert len(conv.message_map) == 2

        # Verify message chain
        messages = conv.get_longest_path()
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "Hello"
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[1].content.text == "Hi there!"

    @pytest.mark.unit
    def test_import_copilot_from_db_with_chat_table(self, tmp_path):
        """A copilot.db with a 'chat_history' table should also work."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()
        db_path = copilot_dir / "copilot_data.db"

        messages_json = json.dumps(
            [
                {"role": "user", "content": "What is Python?"},
            ]
        )

        _create_test_db(
            db_path,
            "chat_history",
            ["id", "title", "messages"],
            [("conv-2", "Python Q", messages_json)],
        )

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)

        assert len(result) == 1
        assert result[0].id == "conv-2"

    @pytest.mark.unit
    def test_import_copilot_db_ignores_non_conversation_tables(self, tmp_path):
        """Tables not matching 'conversation' or 'chat' should be ignored."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()
        db_path = copilot_dir / "copilot_settings.db"

        _create_test_db(
            db_path,
            "settings",
            ["key", "value"],
            [("theme", "dark")],
        )

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert result == []

    @pytest.mark.unit
    def test_import_copilot_state_vscdb(self, tmp_path):
        """state.vscdb files should also be scanned for conversations."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()
        db_path = copilot_dir / "state.vscdb"

        messages_json = json.dumps(
            [
                {"role": "user", "content": "Code help"},
                {"role": "assistant", "content": "Sure!"},
            ]
        )

        _create_test_db(
            db_path,
            "conversation_log",
            ["id", "title", "messages"],
            [("conv-vscdb", "VSCDB Chat", messages_json)],
        )

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert len(result) == 1
        assert result[0].id == "conv-vscdb"

    @pytest.mark.unit
    def test_import_copilot_from_json_single_object(self, tmp_path):
        """A JSON file with a single copilot conversation object should import."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()

        json_data = {
            "conversationId": "json-conv-1",
            "title": "JSON Chat",
            "turns": [
                {
                    "id": "t1",
                    "request": {"message": "Help me code"},
                    "response": {"message": "Sure, what do you need?"},
                }
            ],
        }

        json_path = copilot_dir / "my_conversation_data.json"
        json_path.write_text(json.dumps(json_data))

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert len(result) == 1
        assert result[0].id == "json-conv-1"

    @pytest.mark.unit
    def test_import_copilot_from_json_list(self, tmp_path):
        """A JSON file with a list of copilot conversations should import all."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()

        json_data = [
            {
                "conversationId": "list-conv-1",
                "title": "First Chat",
                "turns": [
                    {
                        "id": "t1",
                        "request": {"message": "Q1"},
                        "response": {"message": "A1"},
                    }
                ],
            },
            {
                "conversationId": "list-conv-2",
                "title": "Second Chat",
                "turns": [
                    {
                        "id": "t2",
                        "request": {"message": "Q2"},
                        "response": {"message": "A2"},
                    }
                ],
            },
        ]

        json_path = copilot_dir / "chat_log.json"
        json_path.write_text(json.dumps(json_data))

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert len(result) == 2

    @pytest.mark.unit
    def test_import_copilot_invalid_json_skipped(self, tmp_path):
        """Invalid JSON files should be skipped without error."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()

        json_path = copilot_dir / "broken_conversation.json"
        json_path.write_text("{invalid json content}")

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert result == []

    @pytest.mark.unit
    def test_import_copilot_corrupt_db_skipped(self, tmp_path):
        """Corrupt SQLite databases should be skipped without error."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()

        db_path = copilot_dir / "copilot_corrupt.db"
        db_path.write_text("this is not a sqlite database")

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert result == []


# ===========================================================================
# _parse_copilot_row tests
# ===========================================================================


class TestParseCopilotRow:
    """Tests for _parse_copilot_row."""

    @pytest.mark.unit
    def test_parse_row_with_messages_json_string(self):
        """A row with a JSON string 'messages' field should produce a tree with messages."""
        importer = FilesystemCodingImporter()
        row = {
            "id": "row-1",
            "title": "Row Chat",
            "messages": json.dumps(
                [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "World"},
                ]
            ),
        }
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert result.id == "row-1"
        assert result.title == "Row Chat"
        assert len(result.message_map) == 2
        assert result.metadata.source == "GitHub Copilot"
        assert result.metadata.format == "copilot"
        assert "copilot" in result.metadata.tags

    @pytest.mark.unit
    def test_parse_row_without_messages(self):
        """A row without messages should produce a tree with no messages."""
        importer = FilesystemCodingImporter()
        row = {"id": "row-empty", "title": "Empty Chat"}
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert result.id == "row-empty"
        assert len(result.message_map) == 0

    @pytest.mark.unit
    def test_parse_row_default_id_and_title(self):
        """A row missing id/title should get defaults."""
        importer = FilesystemCodingImporter()
        row = {}
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert result.title == "Copilot Session"
        # id should be a UUID
        assert len(result.id) > 0

    @pytest.mark.unit
    def test_parse_row_with_timestamps(self):
        """A row with created_at/updated_at should parse timestamps."""
        importer = FilesystemCodingImporter()
        row = {
            "id": "ts-row",
            "title": "Timestamped",
            "created_at": "2024-06-15T10:30:00",
            "updated_at": "2024-06-15T11:00:00",
        }
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert result.metadata.created_at.year == 2024
        assert result.metadata.created_at.month == 6
        assert result.metadata.updated_at.hour == 11

    @pytest.mark.unit
    def test_parse_row_preserves_workspace_and_language(self):
        """custom_data should include workspace and language from the row."""
        importer = FilesystemCodingImporter()
        row = {
            "id": "meta-row",
            "workspace": "/home/user/project",
            "language": "python",
        }
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert result.metadata.custom_data["workspace"] == "/home/user/project"
        assert result.metadata.custom_data["language"] == "python"

    @pytest.mark.unit
    def test_parse_row_message_parent_chain(self):
        """Messages should be chained: first is root, subsequent have parent_id."""
        importer = FilesystemCodingImporter()
        row = {
            "id": "chain-row",
            "messages": json.dumps(
                [
                    {"role": "user", "content": "First"},
                    {"role": "assistant", "content": "Second"},
                    {"role": "user", "content": "Third"},
                ]
            ),
        }
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert len(result.message_map) == 3

        msg0 = result.message_map["msg_0"]
        msg1 = result.message_map["msg_1"]
        msg2 = result.message_map["msg_2"]

        assert msg0.parent_id is None
        assert msg1.parent_id == "msg_0"
        assert msg2.parent_id == "msg_1"

    @pytest.mark.unit
    def test_parse_row_file_context_in_metadata(self):
        """Message metadata should include file_context from the source data."""
        importer = FilesystemCodingImporter()
        row = {
            "id": "ctx-row",
            "messages": json.dumps(
                [
                    {"role": "user", "content": "Help", "file_context": "main.py:10"},
                ]
            ),
        }
        result = importer._parse_copilot_row(row)
        assert result is not None
        msg = result.message_map["msg_0"]
        assert msg.content.metadata["file_context"] == "main.py:10"

    @pytest.mark.unit
    def test_parse_row_empty_messages_string(self):
        """An empty string for messages should result in no messages."""
        importer = FilesystemCodingImporter()
        row = {"id": "empty-msg", "messages": ""}
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert len(result.message_map) == 0


# ===========================================================================
# _parse_copilot_json tests
# ===========================================================================


class TestParseCopilotJson:
    """Tests for _parse_copilot_json."""

    @pytest.mark.unit
    def test_parse_json_with_turns_request_response(self):
        """JSON with turns containing request/response pairs should parse."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "json-1",
            "title": "JSON Conv",
            "turns": [
                {
                    "id": "turn1",
                    "request": {"message": "Hello"},
                    "response": {"message": "Hi!"},
                }
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        assert result.id == "json-1"
        assert result.title == "JSON Conv"
        assert len(result.message_map) == 2

        # Check roles
        roles = [m.role for m in result.message_map.values()]
        assert MessageRole.USER in roles
        assert MessageRole.ASSISTANT in roles

    @pytest.mark.unit
    def test_parse_json_with_messages_key(self):
        """JSON with 'messages' key (fallback from 'turns') should parse."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "msg-json",
            "messages": [
                {
                    "id": "m1",
                    "request": {"message": "Q"},
                    "response": {"message": "A"},
                }
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        assert len(result.message_map) == 2

    @pytest.mark.unit
    def test_parse_json_request_only(self):
        """A turn with only a request (no response) should add one message."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "req-only",
            "turns": [
                {"id": "t1", "request": {"message": "Hello"}},
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        assert len(result.message_map) == 1
        msg = list(result.message_map.values())[0]
        assert msg.role == MessageRole.USER

    @pytest.mark.unit
    def test_parse_json_response_only(self):
        """A turn with only a response (no request) should add one message."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "resp-only",
            "turns": [
                {"id": "t1", "response": {"message": "Hi!"}},
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        assert len(result.message_map) == 1
        msg = list(result.message_map.values())[0]
        assert msg.role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_parse_json_empty_turns(self):
        """JSON with empty turns should return None (empty message_map)."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "empty-turns",
            "turns": [],
        }
        result = importer._parse_copilot_json(data)
        assert result is None

    @pytest.mark.unit
    def test_parse_json_metadata_propagated(self):
        """The 'metadata' key from data should be set as custom_data."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "meta-json",
            "metadata": {"workspace": "/project"},
            "turns": [
                {"id": "t1", "request": {"message": "test"}},
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        assert result.metadata.custom_data == {"workspace": "/project"}

    @pytest.mark.unit
    def test_parse_json_multiple_turns_chained(self):
        """Multiple turns should be chained via parent_id."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "multi-turn",
            "turns": [
                {
                    "id": "t1",
                    "request": {"message": "Q1"},
                    "response": {"message": "A1"},
                },
                {
                    "id": "t2",
                    "request": {"message": "Q2"},
                    "response": {"message": "A2"},
                },
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        assert len(result.message_map) == 4

        # First request should be root
        first_req = result.message_map["t1_req"]
        assert first_req.parent_id is None

        # First response chains from first request
        first_resp = result.message_map["t1_resp"]
        assert first_resp.parent_id == "t1_req"

        # Second request chains from first response
        second_req = result.message_map["t2_req"]
        assert second_req.parent_id == "t1_resp"

    @pytest.mark.unit
    def test_parse_json_default_id_and_title(self):
        """Missing conversationId and title should get defaults."""
        importer = FilesystemCodingImporter()
        data = {
            "turns": [
                {"id": "t1", "request": {"message": "Hello"}},
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        assert result.title == "Copilot Session"
        assert len(result.id) > 0

    @pytest.mark.unit
    def test_parse_json_response_suggestions_in_metadata(self):
        """Response suggestions should be captured in message metadata."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "sugg",
            "turns": [
                {
                    "id": "t1",
                    "response": {
                        "message": "Try this",
                        "suggestions": ["option A", "option B"],
                    },
                }
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        msg = list(result.message_map.values())[0]
        assert msg.content.metadata["suggestions"] == ["option A", "option B"]


# ===========================================================================
# Cursor import tests
# ===========================================================================


class TestCursorImport:
    """Tests for _import_cursor and _parse_cursor_conversation."""

    @pytest.mark.unit
    def test_import_cursor_empty_directory(self, tmp_path):
        """An empty cursor directory should return an empty list."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        importer = FilesystemCodingImporter()
        result = importer._import_cursor(cursor_dir)
        assert result == []

    @pytest.mark.unit
    def test_import_cursor_with_db_no_conversation_table(self, tmp_path):
        """A cursor .db without conversation tables should return empty list."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        db_path = cursor_dir / "data.db"
        _create_test_db(db_path, "settings", ["key", "value"], [("a", "b")])

        importer = FilesystemCodingImporter()
        result = importer._import_cursor(cursor_dir)
        assert result == []

    @pytest.mark.unit
    def test_import_cursor_with_conversation_table_placeholder_returns_empty(
        self, tmp_path
    ):
        """Cursor with conversation table rows still returns empty (placeholder parser returns None)."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        db_path = cursor_dir / "state.db"

        _create_test_db(
            db_path,
            "conversations",
            ["id", "data"],
            [("c1", "some data")],
        )

        importer = FilesystemCodingImporter()
        result = importer._import_cursor(cursor_dir)
        # _parse_cursor_conversation is a placeholder that returns None
        assert result == []

    @pytest.mark.unit
    def test_parse_cursor_conversation_returns_none(self):
        """The placeholder _parse_cursor_conversation should return None."""
        importer = FilesystemCodingImporter()
        assert importer._parse_cursor_conversation(("some", "data")) is None

    @pytest.mark.unit
    def test_import_cursor_corrupt_db_skipped(self, tmp_path):
        """Corrupt SQLite databases should be skipped gracefully."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        db_path = cursor_dir / "corrupt.db"
        db_path.write_text("not a database")

        importer = FilesystemCodingImporter()
        result = importer._import_cursor(cursor_dir)
        assert result == []


# ===========================================================================
# Claude Code and Codeium placeholder tests
# ===========================================================================


class TestPlaceholderImports:
    """Tests for placeholder import methods."""

    @pytest.mark.unit
    def test_import_claude_code_returns_empty(self, tmp_path):
        """_import_claude_code is a placeholder and should return []."""
        importer = FilesystemCodingImporter()
        assert importer._import_claude_code(tmp_path) == []

    @pytest.mark.unit
    def test_import_codeium_returns_empty(self, tmp_path):
        """_import_codeium is a placeholder and should return []."""
        importer = FilesystemCodingImporter()
        assert importer._import_codeium(tmp_path) == []


# ===========================================================================
# Generic import tests
# ===========================================================================


class TestGenericImport:
    """Tests for _import_generic, _looks_like_conversation, _parse_generic_conversation."""

    @pytest.mark.unit
    def test_import_generic_empty_directory(self, tmp_path):
        """An empty directory should return an empty list."""
        importer = FilesystemCodingImporter()
        result = importer._import_generic(tmp_path)
        assert result == []

    @pytest.mark.unit
    def test_import_generic_json_with_messages_key(self, tmp_path):
        """JSON with 'messages' key detected but _parse_generic returns None, so empty result."""
        json_path = tmp_path / "data.json"
        json_path.write_text(
            json.dumps({"messages": [{"role": "user", "content": "Hi"}]})
        )

        importer = FilesystemCodingImporter()
        result = importer._import_generic(tmp_path)
        # _parse_generic_conversation is a placeholder returning None
        assert result == []

    @pytest.mark.unit
    def test_import_generic_skips_non_conversation_json(self, tmp_path):
        """JSON files without conversation keys should be skipped."""
        json_path = tmp_path / "config.json"
        json_path.write_text(json.dumps({"version": "1.0", "settings": {}}))

        importer = FilesystemCodingImporter()
        result = importer._import_generic(tmp_path)
        assert result == []

    @pytest.mark.unit
    def test_import_generic_invalid_json_skipped(self, tmp_path):
        """Invalid JSON files should be skipped without error."""
        json_path = tmp_path / "broken.json"
        json_path.write_text("{broken json")

        importer = FilesystemCodingImporter()
        result = importer._import_generic(tmp_path)
        assert result == []

    @pytest.mark.unit
    def test_import_generic_nested_json(self, tmp_path):
        """JSON files in subdirectories should also be scanned."""
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        json_path = subdir / "data.json"
        json_path.write_text(json.dumps({"messages": []}))

        importer = FilesystemCodingImporter()
        result = importer._import_generic(tmp_path)
        # Still empty because _parse_generic returns None
        assert result == []


# ===========================================================================
# _looks_like_conversation tests
# ===========================================================================


class TestLooksLikeConversation:
    """Tests for the _looks_like_conversation heuristic."""

    @pytest.mark.unit
    def test_dict_with_messages_key(self):
        """Dict with 'messages' key should be detected."""
        importer = FilesystemCodingImporter()
        assert importer._looks_like_conversation({"messages": []}) is True

    @pytest.mark.unit
    def test_dict_with_turns_key(self):
        """Dict with 'turns' key should be detected."""
        importer = FilesystemCodingImporter()
        assert importer._looks_like_conversation({"turns": []}) is True

    @pytest.mark.unit
    def test_dict_with_interactions_key(self):
        """Dict with 'interactions' key should be detected."""
        importer = FilesystemCodingImporter()
        assert importer._looks_like_conversation({"interactions": []}) is True

    @pytest.mark.unit
    def test_dict_with_conversation_key(self):
        """Dict with 'conversation' key should be detected."""
        importer = FilesystemCodingImporter()
        assert importer._looks_like_conversation({"conversation": {}}) is True

    @pytest.mark.unit
    def test_dict_without_conv_keys(self):
        """Dict without any conversation keys should return False."""
        importer = FilesystemCodingImporter()
        assert importer._looks_like_conversation({"data": [], "config": {}}) is False

    @pytest.mark.unit
    def test_non_dict_returns_false(self):
        """Non-dict data should return False."""
        importer = FilesystemCodingImporter()
        assert importer._looks_like_conversation([{"messages": []}]) is False
        assert importer._looks_like_conversation("messages") is False
        assert importer._looks_like_conversation(42) is False
        assert importer._looks_like_conversation(None) is False

    @pytest.mark.unit
    def test_parse_generic_conversation_returns_none(self):
        """The placeholder _parse_generic_conversation should return None."""
        importer = FilesystemCodingImporter()
        assert importer._parse_generic_conversation({"messages": []}) is None


# ===========================================================================
# Edge case and integration tests
# ===========================================================================


class TestEdgeCases:
    """Edge cases and additional integration scenarios."""

    @pytest.mark.unit
    def test_unicode_path(self, tmp_path):
        """Paths with unicode characters should work."""
        unicode_dir = tmp_path / "datos_\u00e9l\u00e8ve" / ".vscode"
        unicode_dir.mkdir(parents=True)
        importer = FilesystemCodingImporter()
        assert importer.validate(str(unicode_dir)) is True

    @pytest.mark.unit
    def test_plugin_attributes(self):
        """Plugin class attributes should be set correctly."""
        importer = FilesystemCodingImporter()
        assert importer.name == "filesystem_coding"
        assert importer.version == "1.0.0"
        assert "filesystem" in importer.supported_formats
        assert "vscode" in importer.supported_formats

    @pytest.mark.unit
    def test_known_paths_structure(self):
        """KNOWN_PATHS should contain entries for all expected agents."""
        assert "copilot" in FilesystemCodingImporter.KNOWN_PATHS
        assert "cursor" in FilesystemCodingImporter.KNOWN_PATHS
        assert "claude_code" in FilesystemCodingImporter.KNOWN_PATHS
        assert "codeium" in FilesystemCodingImporter.KNOWN_PATHS

    @pytest.mark.unit
    def test_copilot_row_with_messages_as_list(self):
        """If messages is already a list (not a JSON string), it should still parse."""
        importer = FilesystemCodingImporter()
        row = {
            "id": "list-msg",
            "messages": [
                {"role": "user", "content": "Hello"},
            ],
        }
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert len(result.message_map) == 1

    @pytest.mark.unit
    def test_copilot_row_messages_none(self):
        """If messages is None, should produce tree with no messages."""
        importer = FilesystemCodingImporter()
        row = {"id": "none-msg", "messages": None}
        result = importer._parse_copilot_row(row)
        assert result is not None
        assert len(result.message_map) == 0

    @pytest.mark.unit
    def test_copilot_json_with_context_in_request(self):
        """Request context should be captured in message content metadata."""
        importer = FilesystemCodingImporter()
        data = {
            "conversationId": "ctx-json",
            "turns": [
                {
                    "id": "t1",
                    "request": {
                        "message": "Fix this",
                        "context": {"file": "main.py", "line": 42},
                    },
                }
            ],
        }
        result = importer._parse_copilot_json(data)
        assert result is not None
        msg = list(result.message_map.values())[0]
        assert msg.content.metadata["context"] == {"file": "main.py", "line": 42}

    @pytest.mark.unit
    def test_import_copilot_db_and_json_combined(self, tmp_path):
        """Both DB and JSON sources in same directory should contribute conversations."""
        copilot_dir = tmp_path / ".vscode"
        copilot_dir.mkdir()

        # Create a DB with one conversation
        db_path = copilot_dir / "copilot_main.db"
        messages_json = json.dumps(
            [
                {"role": "user", "content": "DB Hello"},
            ]
        )
        _create_test_db(
            db_path,
            "conversations",
            ["id", "title", "messages"],
            [("db-conv", "DB Chat", messages_json)],
        )

        # Create a JSON file with one conversation
        json_data = {
            "conversationId": "json-conv",
            "title": "JSON Chat",
            "turns": [
                {"id": "t1", "request": {"message": "JSON Hello"}},
            ],
        }
        json_path = copilot_dir / "copilot_conversation_log.json"
        json_path.write_text(json.dumps(json_data))

        importer = FilesystemCodingImporter()
        result = importer._import_copilot(copilot_dir)
        assert len(result) == 2
        conv_ids = {c.id for c in result}
        assert "db-conv" in conv_ids
        assert "json-conv" in conv_ids

    @pytest.mark.unit
    def test_scan_for_conversations_classmethod(self, tmp_path, monkeypatch):
        """scan_for_conversations should return paths that exist."""
        # Monkeypatch KNOWN_PATHS to use our tmp_path
        test_paths = {
            "copilot": [str(tmp_path / "copilot_dir")],
            "cursor": [str(tmp_path / "nonexistent")],
        }
        monkeypatch.setattr(FilesystemCodingImporter, "KNOWN_PATHS", test_paths)

        # Only create the copilot directory
        (tmp_path / "copilot_dir").mkdir()

        found = FilesystemCodingImporter.scan_for_conversations()
        assert len(found) == 1
        assert str(found[0]) == str(tmp_path / "copilot_dir")

    @pytest.mark.unit
    def test_import_data_end_to_end_copilot(self, tmp_path):
        """End-to-end test: validate -> import_data for a copilot directory."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()

        db_path = vscode_dir / "copilot_data.db"
        messages_json = json.dumps(
            [
                {"role": "user", "content": "Write a function"},
                {"role": "assistant", "content": "def hello(): pass"},
            ]
        )
        _create_test_db(
            db_path,
            "conversation_log",
            ["id", "title", "messages"],
            [("e2e-conv", "E2E Chat", messages_json)],
        )

        importer = FilesystemCodingImporter()
        assert importer.validate(str(vscode_dir)) is True

        result = importer.import_data(str(vscode_dir))
        assert len(result) == 1
        assert result[0].id == "e2e-conv"
        assert result[0].metadata.source == "GitHub Copilot"

        messages = result[0].get_longest_path()
        assert len(messages) == 2
        assert messages[0].content.text == "Write a function"
        assert messages[1].content.text == "def hello(): pass"

    @pytest.mark.unit
    def test_detect_format_delegates_to_validate(self, tmp_path):
        """detect_format should delegate to validate (inherited from ImporterPlugin)."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        importer = FilesystemCodingImporter()
        assert importer.detect_format(str(vscode_dir)) is True
        assert importer.detect_format("/nonexistent/path") is False
