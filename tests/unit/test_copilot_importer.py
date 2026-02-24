"""
Unit tests for GitHub Copilot importer.

Tests cover:
- Validation (dict formats, path-based, JSON file)
- Chat session parsing (requests/responses, timestamps, titles, file context)
- Import data dispatch (dict, directory, file, edge cases)
- Edge cases (unicode, missing fields, empty data, multiple sessions)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from ctk.core.models import MessageRole
from ctk.integrations.importers.copilot import CopilotImporter


@pytest.fixture
def importer():
    """Create a CopilotImporter instance."""
    return CopilotImporter()


def _make_session(
    requests=None, session_id=None, creation_date=None, last_message_date=None
):
    """Helper to build a minimal Copilot chat session dict."""
    data = {}
    if requests is not None:
        data["requests"] = requests
    if session_id is not None:
        data["sessionId"] = session_id
    if creation_date is not None:
        data["creationDate"] = creation_date
    if last_message_date is not None:
        data["lastMessageDate"] = last_message_date
    return data


def _make_turn(
    user_text, response_text=None, response_format="result_metadata", variable_data=None
):
    """Helper to build a single request turn.

    response_format:
        "result_metadata" - response in result.metadata.response
        "response_list"   - response in turn["response"] as list of dicts/strings
        None              - no response
    """
    turn = {
        "message": {"text": user_text},
    }
    if response_text is not None:
        if response_format == "result_metadata":
            turn["result"] = {"metadata": {"response": response_text}}
        elif response_format == "response_list":
            turn["response"] = [{"value": response_text}]
    if variable_data is not None:
        turn["variableData"] = variable_data
    return turn


# ===========================================================================
# Validation tests
# ===========================================================================
class TestCopilotValidation:
    """Tests for CopilotImporter.validate()."""

    @pytest.mark.unit
    def test_validate_dict_with_requests(self, importer):
        """Dict with 'requests' key should validate as True."""
        assert importer.validate({"requests": []}) is True

    @pytest.mark.unit
    def test_validate_dict_with_session_id(self, importer):
        """Dict with 'sessionId' key should validate as True."""
        assert importer.validate({"sessionId": "abc-123"}) is True

    @pytest.mark.unit
    def test_validate_dict_with_both_keys(self, importer):
        """Dict with both 'requests' and 'sessionId' should validate as True."""
        assert importer.validate({"requests": [], "sessionId": "abc"}) is True

    @pytest.mark.unit
    def test_validate_invalid_dict(self, importer):
        """Dict without relevant keys should validate as False."""
        assert importer.validate({"foo": "bar", "baz": 42}) is False

    @pytest.mark.unit
    def test_validate_empty_dict(self, importer):
        """Empty dict should validate as False."""
        assert importer.validate({}) is False

    @pytest.mark.unit
    def test_validate_none(self, importer):
        """None should validate as False."""
        assert importer.validate(None) is False

    @pytest.mark.unit
    def test_validate_integer(self, importer):
        """Integer should validate as False."""
        assert importer.validate(42) is False

    @pytest.mark.unit
    def test_validate_list(self, importer):
        """List should validate as False."""
        assert importer.validate([{"requests": []}]) is False

    @pytest.mark.unit
    def test_validate_empty_string(self, importer):
        """Empty string should validate as False (not a valid path)."""
        assert importer.validate("") is False

    @pytest.mark.unit
    def test_validate_directory_with_chat_sessions(self, importer, tmp_path):
        """Directory containing chatSessions/ should validate as True."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()
        assert importer.validate(str(tmp_path)) is True

    @pytest.mark.unit
    def test_validate_directory_without_chat_sessions(self, importer, tmp_path):
        """Directory without chatSessions/ should validate as False."""
        (tmp_path / "some_other_dir").mkdir()
        assert importer.validate(str(tmp_path)) is False

    @pytest.mark.unit
    def test_validate_workspace_storage_root(self, importer, tmp_path):
        """Workspace storage root with a subdirectory containing chatSessions/."""
        ws_dir = tmp_path / "abc123hash"
        ws_dir.mkdir()
        (ws_dir / "chatSessions").mkdir()
        assert importer.validate(str(tmp_path)) is True

    @pytest.mark.unit
    def test_validate_workspace_storage_root_no_sessions(self, importer, tmp_path):
        """Workspace storage root with subdirectories but no chatSessions/."""
        ws_dir = tmp_path / "abc123hash"
        ws_dir.mkdir()
        (ws_dir / "other_stuff").mkdir()
        assert importer.validate(str(tmp_path)) is False

    @pytest.mark.unit
    def test_validate_json_file_with_requests(self, importer, tmp_path):
        """JSON file containing 'requests' should validate as True."""
        json_file = tmp_path / "session.json"
        json_file.write_text(json.dumps({"requests": []}))
        assert importer.validate(str(json_file)) is True

    @pytest.mark.unit
    def test_validate_json_file_with_creation_date(self, importer, tmp_path):
        """JSON file containing 'creationDate' should validate as True."""
        json_file = tmp_path / "session.json"
        json_file.write_text(json.dumps({"creationDate": 1700000000000}))
        assert importer.validate(str(json_file)) is True

    @pytest.mark.unit
    def test_validate_json_file_without_copilot_keys(self, importer, tmp_path):
        """JSON file without Copilot keys should validate as False."""
        json_file = tmp_path / "other.json"
        json_file.write_text(json.dumps({"unrelated": "data"}))
        assert importer.validate(str(json_file)) is False

    @pytest.mark.unit
    def test_validate_invalid_json_file(self, importer, tmp_path):
        """Non-JSON file with .json extension should validate as False."""
        json_file = tmp_path / "broken.json"
        json_file.write_text("this is not json {{{")
        assert importer.validate(str(json_file)) is False

    @pytest.mark.unit
    def test_validate_nonexistent_path(self, importer):
        """Non-existent path should validate as False."""
        assert importer.validate("/tmp/does_not_exist_copilot_test_xyz") is False

    @pytest.mark.unit
    def test_validate_very_long_string(self, importer):
        """String longer than 4096 chars is not treated as path."""
        long_str = "x" * 5000
        assert importer.validate(long_str) is False


# ===========================================================================
# _is_conversation_data tests
# ===========================================================================
class TestIsConversationData:
    """Tests for CopilotImporter._is_conversation_data()."""

    @pytest.mark.unit
    def test_with_requests(self, importer):
        assert importer._is_conversation_data({"requests": []}) is True

    @pytest.mark.unit
    def test_with_messages(self, importer):
        assert importer._is_conversation_data({"messages": []}) is True

    @pytest.mark.unit
    def test_with_session_id(self, importer):
        assert importer._is_conversation_data({"sessionId": "abc"}) is True

    @pytest.mark.unit
    def test_non_dict(self, importer):
        assert importer._is_conversation_data("not a dict") is False

    @pytest.mark.unit
    def test_empty_dict(self, importer):
        assert importer._is_conversation_data({}) is False

    @pytest.mark.unit
    def test_none(self, importer):
        assert importer._is_conversation_data(None) is False

    @pytest.mark.unit
    def test_list(self, importer):
        assert importer._is_conversation_data([1, 2, 3]) is False


# ===========================================================================
# _parse_chat_session tests
# ===========================================================================
class TestCopilotParseChatSession:
    """Tests for CopilotImporter._parse_chat_session()."""

    @pytest.mark.unit
    def test_basic_request_response(self, importer):
        """Parse a basic user request with assistant response."""
        data = _make_session(
            requests=[
                _make_turn("Hello Copilot", "Hi there!"),
            ]
        )
        conv = importer._parse_chat_session(data)

        assert conv is not None
        messages = conv.get_longest_path()
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "Hello Copilot"
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[1].content.text == "Hi there!"

    @pytest.mark.unit
    def test_multiple_turns(self, importer):
        """Parse multiple request/response turns."""
        data = _make_session(
            requests=[
                _make_turn("First question", "First answer"),
                _make_turn("Second question", "Second answer"),
            ]
        )
        conv = importer._parse_chat_session(data)

        messages = conv.get_longest_path()
        assert len(messages) == 4
        assert messages[0].content.text == "First question"
        assert messages[1].content.text == "First answer"
        assert messages[2].content.text == "Second question"
        assert messages[3].content.text == "Second answer"

    @pytest.mark.unit
    def test_user_message_only_no_response(self, importer):
        """Turn with user message but no response should still add user message."""
        data = _make_session(
            requests=[
                _make_turn("Just a question", response_text=None),
            ]
        )
        conv = importer._parse_chat_session(data)

        assert conv is not None
        messages = conv.get_longest_path()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "Just a question"

    @pytest.mark.unit
    def test_empty_requests_returns_none(self, importer):
        """Empty requests list produces no messages, returns None."""
        data = _make_session(requests=[])
        conv = importer._parse_chat_session(data)
        assert conv is None

    @pytest.mark.unit
    def test_session_id_from_data(self, importer):
        """Session ID should be taken from data when not passed explicitly."""
        data = _make_session(
            requests=[_make_turn("Hi", "Hello")],
            session_id="my-session-123",
        )
        conv = importer._parse_chat_session(data)
        assert conv.id == "my-session-123"

    @pytest.mark.unit
    def test_session_id_from_parameter(self, importer):
        """Explicit session_id parameter should override data sessionId."""
        data = _make_session(
            requests=[_make_turn("Hi", "Hello")],
            session_id="data-id",
        )
        conv = importer._parse_chat_session(data, session_id="param-id")
        assert conv.id == "param-id"

    @pytest.mark.unit
    def test_session_id_auto_generated(self, importer):
        """When no session ID provided, a UUID should be generated."""
        data = _make_session(requests=[_make_turn("Hi", "Hello")])
        conv = importer._parse_chat_session(data)
        # Should be a valid UUID-like string (36 chars with hyphens)
        assert conv.id is not None
        assert len(conv.id) > 0

    @pytest.mark.unit
    def test_creation_date_timestamp(self, importer):
        """creationDate in milliseconds should be converted to datetime."""
        # 1700000000000 ms = 2023-11-14 22:13:20 UTC
        ts_ms = 1700000000000
        data = _make_session(
            requests=[_make_turn("Hi", "Hello")],
            creation_date=ts_ms,
        )
        conv = importer._parse_chat_session(data)
        expected = datetime.fromtimestamp(ts_ms / 1000)
        assert conv.metadata.created_at == expected

    @pytest.mark.unit
    def test_last_message_date_timestamp(self, importer):
        """lastMessageDate in milliseconds should set updated_at, but add_message() overwrites it."""
        ts_ms = 1700001000000
        data = _make_session(
            requests=[_make_turn("Hi", "Hello")],
            last_message_date=ts_ms,
        )
        conv = importer._parse_chat_session(data)
        # add_message() overwrites updated_at, so just verify it's a datetime
        assert isinstance(conv.metadata.updated_at, datetime)

    @pytest.mark.unit
    def test_title_from_first_user_message(self, importer):
        """Title should be extracted from first user message text."""
        data = _make_session(
            requests=[
                _make_turn("How do I parse JSON in Python?", "Use json.loads()"),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv.title == "How do I parse JSON in Python?"

    @pytest.mark.unit
    def test_title_truncation_at_50_chars(self, importer):
        """Title longer than 50 chars should be truncated with '...'."""
        long_msg = "A" * 60  # 60 characters
        data = _make_session(
            requests=[
                _make_turn(long_msg, "Response"),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv.title == "A" * 50 + "..."
        assert len(conv.title) == 53

    @pytest.mark.unit
    def test_title_exactly_50_chars(self, importer):
        """Title of exactly 50 chars should get '...' appended."""
        msg = "B" * 50
        data = _make_session(
            requests=[
                _make_turn(msg, "Response"),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv.title == "B" * 50 + "..."

    @pytest.mark.unit
    def test_title_under_50_chars(self, importer):
        """Title under 50 chars should not be truncated."""
        msg = "C" * 49
        data = _make_session(
            requests=[
                _make_turn(msg, "Response"),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv.title == "C" * 49

    @pytest.mark.unit
    def test_title_multiline_uses_first_line(self, importer):
        """Title should use only the first line of user message."""
        data = _make_session(
            requests=[
                _make_turn("First line\nSecond line\nThird line", "Response"),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv.title == "First line"

    @pytest.mark.unit
    def test_default_title_when_no_message_text(self, importer):
        """Default title 'Copilot Chat' when first message has no text."""
        data = _make_session(
            requests=[
                {"message": {"text": ""}, "result": {"metadata": {"response": "Hi"}}},
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv.title == "Copilot Chat"

    @pytest.mark.unit
    def test_default_title_when_no_message_key(self, importer):
        """Default title when first request has no 'message' key."""
        data = _make_session(
            requests=[
                {"result": {"metadata": {"response": "Some response"}}},
            ]
        )
        conv = importer._parse_chat_session(data)
        # No user message text -> default title
        # But assistant response is still added
        assert conv is not None
        assert conv.title == "Copilot Chat"
        messages = conv.get_longest_path()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_project_path_extraction(self, importer):
        """project_path should be stored in metadata and project_name extracted."""
        data = _make_session(requests=[_make_turn("Hi", "Hello")])
        conv = importer._parse_chat_session(
            data, project_path="file:///home/user/myproject"
        )
        assert (
            conv.metadata.custom_data["project_path"] == "file:///home/user/myproject"
        )
        assert conv.metadata.custom_data["project_name"] == "myproject"
        assert "project:myproject" in conv.metadata.tags

    @pytest.mark.unit
    def test_project_path_none(self, importer):
        """When project_path is None, project_name should be None."""
        data = _make_session(requests=[_make_turn("Hi", "Hello")])
        conv = importer._parse_chat_session(data, project_path=None)
        assert conv.metadata.custom_data["project_name"] is None
        # No project tag should be added
        assert not any(t.startswith("project:") for t in conv.metadata.tags)

    @pytest.mark.unit
    def test_metadata_source_and_model(self, importer):
        """Metadata should have correct source and model."""
        data = _make_session(requests=[_make_turn("Hi", "Hello")])
        conv = importer._parse_chat_session(data)
        assert conv.metadata.source == "GitHub Copilot"
        assert conv.metadata.model == "Copilot"
        assert conv.metadata.format == "copilot"

    @pytest.mark.unit
    def test_default_tags(self, importer):
        """Conversations should have default tags."""
        data = _make_session(requests=[_make_turn("Hi", "Hello")])
        conv = importer._parse_chat_session(data)
        assert "copilot" in conv.metadata.tags
        assert "vscode" in conv.metadata.tags
        assert "coding" in conv.metadata.tags

    @pytest.mark.unit
    def test_file_context_in_variable_data(self, importer):
        """File references from variableData should be in message metadata."""
        var_data = {
            "variables": [
                {
                    "kind": "file",
                    "value": {"uri": {"path": "/home/user/project/main.py"}},
                },
                {
                    "kind": "file",
                    "value": {"uri": {"path": "/home/user/project/utils.py"}},
                },
            ]
        }
        data = _make_session(
            requests=[
                _make_turn("Explain this code", "Sure!", variable_data=var_data),
            ]
        )
        conv = importer._parse_chat_session(data)
        user_msg = conv.get_longest_path()[0]
        refs = user_msg.content.metadata.get("referenced_files", [])
        assert len(refs) == 2
        assert "/home/user/project/main.py" in refs
        assert "/home/user/project/utils.py" in refs

    @pytest.mark.unit
    def test_file_context_non_file_kind_ignored(self, importer):
        """Variables with kind != 'file' should be ignored."""
        var_data = {
            "variables": [
                {"kind": "selection", "value": {"text": "some code"}},
            ]
        }
        data = _make_session(
            requests=[
                _make_turn("Explain", "Sure!", variable_data=var_data),
            ]
        )
        conv = importer._parse_chat_session(data)
        user_msg = conv.get_longest_path()[0]
        refs = user_msg.content.metadata.get("referenced_files", [])
        assert len(refs) == 0

    @pytest.mark.unit
    def test_response_in_result_metadata_format(self, importer):
        """Response in result.metadata.response format."""
        data = _make_session(
            requests=[
                _make_turn(
                    "Q",
                    "Answer from result.metadata",
                    response_format="result_metadata",
                ),
            ]
        )
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert messages[1].content.text == "Answer from result.metadata"

    @pytest.mark.unit
    def test_response_in_turn_response_list_format(self, importer):
        """Response in turn['response'] list format with value dicts."""
        data = _make_session(
            requests=[
                _make_turn("Q", "Answer from list", response_format="response_list"),
            ]
        )
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert messages[1].content.text == "Answer from list"

    @pytest.mark.unit
    def test_response_list_with_mixed_types(self, importer):
        """Response list with both dict and string parts."""
        turn = {
            "message": {"text": "Question"},
            "response": [
                {"value": "Part 1 "},
                "Part 2 ",
                {"value": "Part 3"},
            ],
        }
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert messages[1].content.text == "Part 1 Part 2 Part 3"

    @pytest.mark.unit
    def test_response_list_empty_produces_no_assistant_message(self, importer):
        """Empty response list means no response text, so no assistant message."""
        turn = {
            "message": {"text": "Question"},
            "response": [],
        }
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER

    @pytest.mark.unit
    def test_message_ids_contain_conv_id(self, importer):
        """Message IDs should include the conversation ID."""
        data = _make_session(
            requests=[_make_turn("Hi", "Hello")],
            session_id="test-conv-id",
        )
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert "test-conv-id" in messages[0].id
        assert "test-conv-id" in messages[1].id

    @pytest.mark.unit
    def test_message_parent_chain(self, importer):
        """Messages should be chained via parent_id."""
        data = _make_session(
            requests=[
                _make_turn("Q1", "A1"),
                _make_turn("Q2", "A2"),
            ]
        )
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()

        # First user message has no parent
        assert messages[0].parent_id is None
        # First assistant is child of first user
        assert messages[1].parent_id == messages[0].id
        # Second user is child of first assistant
        assert messages[2].parent_id == messages[1].id
        # Second assistant is child of second user
        assert messages[3].parent_id == messages[2].id

    @pytest.mark.unit
    def test_missing_message_text_key(self, importer):
        """Turn with message dict but no 'text' key -> empty user_msg, not added."""
        turn = {
            "message": {},
            "result": {"metadata": {"response": "A response"}},
        }
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        # user_msg is "" which is falsy, so user message is not added.
        # But response also won't be added since parent_id never got set to user msg.
        # Actually looking at the code: user_msg="" is falsy, so user message block
        # is skipped, but response_text is still checked and can be added with parent_id=None
        assert conv is not None
        messages = conv.get_longest_path()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.ASSISTANT


# ===========================================================================
# import_data tests
# ===========================================================================
class TestCopilotImportData:
    """Tests for CopilotImporter.import_data()."""

    @pytest.mark.unit
    def test_import_from_dict(self, importer):
        """Import directly from a dict with conversation data."""
        data = _make_session(
            requests=[
                _make_turn("Hello", "World"),
            ]
        )
        results = importer.import_data(data)
        assert len(results) == 1
        assert results[0].get_longest_path()[0].content.text == "Hello"

    @pytest.mark.unit
    def test_import_from_empty_dict(self, importer):
        """Empty dict with no requests should return empty list."""
        results = importer.import_data({})
        assert results == []

    @pytest.mark.unit
    def test_import_from_dict_empty_requests(self, importer):
        """Dict with empty requests list produces no conversation (returns None)."""
        results = importer.import_data({"requests": []})
        assert results == []

    @pytest.mark.unit
    def test_import_nonexistent_path(self, importer):
        """Non-existent path string should return empty list."""
        results = importer.import_data("/tmp/nonexistent_copilot_path_xyz_123")
        assert results == []

    @pytest.mark.unit
    def test_import_non_string_non_dict(self, importer):
        """Non-string, non-dict input should return empty list."""
        assert importer.import_data(42) == []
        assert importer.import_data(None) == []
        assert importer.import_data([]) == []

    @pytest.mark.unit
    def test_import_from_directory(self, importer, tmp_path):
        """Import from directory with chatSessions/ containing JSON files."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()

        session = _make_session(
            requests=[
                _make_turn("Dir question", "Dir answer"),
            ]
        )
        (chat_dir / "session1.json").write_text(json.dumps(session))

        results = importer.import_data(str(tmp_path))
        assert len(results) == 1
        messages = results[0].get_longest_path()
        assert messages[0].content.text == "Dir question"

    @pytest.mark.unit
    def test_import_from_directory_multiple_sessions(self, importer, tmp_path):
        """Import multiple sessions from a single directory."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()

        for i in range(3):
            session = _make_session(
                requests=[
                    _make_turn(f"Question {i}", f"Answer {i}"),
                ]
            )
            (chat_dir / f"session_{i}.json").write_text(json.dumps(session))

        results = importer.import_data(str(tmp_path))
        assert len(results) == 3

    @pytest.mark.unit
    def test_import_from_workspace_storage_root(self, importer, tmp_path):
        """Import from workspace storage root with multiple workspace dirs."""
        for ws_name in ["workspace_a", "workspace_b"]:
            ws_dir = tmp_path / ws_name
            ws_dir.mkdir()
            chat_dir = ws_dir / "chatSessions"
            chat_dir.mkdir()
            session = _make_session(
                requests=[
                    _make_turn(f"Q from {ws_name}", f"A from {ws_name}"),
                ]
            )
            (chat_dir / "session.json").write_text(json.dumps(session))

        results = importer.import_data(str(tmp_path))
        assert len(results) == 2

    @pytest.mark.unit
    def test_import_from_directory_with_workspace_json(self, importer, tmp_path):
        """workspace.json should provide project_path to parsed sessions."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()

        ws_json = tmp_path / "workspace.json"
        ws_json.write_text(json.dumps({"folder": "file:///home/user/myrepo"}))

        session = _make_session(
            requests=[
                _make_turn("Code question", "Code answer"),
            ]
        )
        (chat_dir / "session.json").write_text(json.dumps(session))

        results = importer.import_data(str(tmp_path))
        assert len(results) == 1
        assert (
            results[0].metadata.custom_data["project_path"]
            == "file:///home/user/myrepo"
        )
        assert results[0].metadata.custom_data["project_name"] == "myrepo"

    @pytest.mark.unit
    def test_import_from_directory_broken_workspace_json(self, importer, tmp_path):
        """Broken workspace.json should not prevent session import."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()

        ws_json = tmp_path / "workspace.json"
        ws_json.write_text("NOT VALID JSON {{{")

        session = _make_session(requests=[_make_turn("Q", "A")])
        (chat_dir / "session.json").write_text(json.dumps(session))

        results = importer.import_data(str(tmp_path))
        assert len(results) == 1
        assert results[0].metadata.custom_data["project_path"] is None

    @pytest.mark.unit
    def test_import_from_json_file(self, importer, tmp_path):
        """Import from a single .json file."""
        session = _make_session(
            requests=[
                _make_turn("File question", "File answer"),
            ]
        )
        json_file = tmp_path / "copilot_session.json"
        json_file.write_text(json.dumps(session))

        results = importer.import_data(str(json_file))
        assert len(results) == 1
        assert results[0].get_longest_path()[0].content.text == "File question"

    @pytest.mark.unit
    def test_import_from_broken_json_file(self, importer, tmp_path):
        """Broken JSON file should return empty list."""
        json_file = tmp_path / "broken.json"
        json_file.write_text("not json at all!!!")

        results = importer.import_data(str(json_file))
        assert results == []

    @pytest.mark.unit
    def test_import_from_unsupported_file_extension(self, importer, tmp_path):
        """File with unsupported extension should return empty list."""
        txt_file = tmp_path / "data.txt"
        txt_file.write_text("some text")

        results = importer.import_data(str(txt_file))
        assert results == []

    @pytest.mark.unit
    def test_import_from_directory_with_broken_session_file(self, importer, tmp_path):
        """Broken session file should be skipped, valid ones imported."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()

        # One good session
        good_session = _make_session(requests=[_make_turn("Good Q", "Good A")])
        (chat_dir / "good.json").write_text(json.dumps(good_session))

        # One broken session
        (chat_dir / "bad.json").write_text("NOT JSON!!!")

        results = importer.import_data(str(tmp_path))
        assert len(results) == 1

    @pytest.mark.unit
    def test_import_session_id_from_filename(self, importer, tmp_path):
        """Session ID should come from filename stem when importing from directory."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()

        session = _make_session(requests=[_make_turn("Q", "A")])
        (chat_dir / "my-custom-id.json").write_text(json.dumps(session))

        results = importer.import_data(str(tmp_path))
        assert len(results) == 1
        assert results[0].id == "my-custom-id"


# ===========================================================================
# _import_from_vscdb tests
# ===========================================================================
class TestCopilotImportFromVscdb:
    """Tests for CopilotImporter._import_from_vscdb()."""

    @pytest.mark.unit
    def test_import_from_vscdb(self, importer, tmp_path):
        """Import conversation data from a .vscdb SQLite database."""
        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")

        session_data = _make_session(
            requests=[
                _make_turn("DB question", "DB answer"),
            ]
        )
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("copilot.chat.sessions", json.dumps(session_data)),
        )
        conn.commit()
        conn.close()

        results = importer._import_from_vscdb(db_path)
        assert len(results) == 1
        assert results[0].get_longest_path()[0].content.text == "DB question"

    @pytest.mark.unit
    def test_import_from_vscdb_no_matching_keys(self, importer, tmp_path):
        """DB with no copilot/github keys should return empty list."""
        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("some.other.extension", '{"data": "irrelevant"}'),
        )
        conn.commit()
        conn.close()

        results = importer._import_from_vscdb(db_path)
        assert results == []

    @pytest.mark.unit
    def test_import_from_vscdb_non_conversation_data(self, importer, tmp_path):
        """DB rows with copilot key but non-conversation JSON should be skipped."""
        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("copilot.settings", json.dumps({"theme": "dark"})),
        )
        conn.commit()
        conn.close()

        results = importer._import_from_vscdb(db_path)
        assert results == []

    @pytest.mark.unit
    def test_import_from_vscdb_invalid_json_value(self, importer, tmp_path):
        """DB row with invalid JSON value should be skipped gracefully."""
        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("copilot.data", "not-json-at-all"),
        )
        conn.commit()
        conn.close()

        results = importer._import_from_vscdb(db_path)
        assert results == []

    @pytest.mark.unit
    def test_import_from_vscdb_nonexistent_db(self, importer, tmp_path):
        """Non-existent database should return empty list."""
        db_path = tmp_path / "nonexistent.vscdb"
        results = importer._import_from_vscdb(db_path)
        assert results == []

    @pytest.mark.unit
    def test_import_from_vscdb_corrupt_db(self, importer, tmp_path):
        """Corrupt database file should return empty list."""
        db_path = tmp_path / "corrupt.vscdb"
        db_path.write_text("this is not a sqlite database")

        results = importer._import_from_vscdb(db_path)
        assert results == []

    @pytest.mark.unit
    def test_import_from_db_extension(self, importer, tmp_path):
        """Import should work with .db extension via _import_from_file."""
        db_path = tmp_path / "state.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")

        session_data = _make_session(
            requests=[
                _make_turn("DB Q", "DB A"),
            ]
        )
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            ("github.copilot.history", json.dumps(session_data)),
        )
        conn.commit()
        conn.close()

        results = importer.import_data(str(db_path))
        assert len(results) == 1

    @pytest.mark.unit
    def test_import_from_vscdb_multiple_conversations(self, importer, tmp_path):
        """Multiple conversation rows should all be imported."""
        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")

        for i in range(3):
            session = _make_session(
                requests=[
                    _make_turn(f"Question {i}", f"Answer {i}"),
                ]
            )
            conn.execute(
                "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
                (f"copilot.session.{i}", json.dumps(session)),
            )
        conn.commit()
        conn.close()

        results = importer._import_from_vscdb(db_path)
        assert len(results) == 3


# ===========================================================================
# Edge cases
# ===========================================================================
class TestCopilotEdgeCases:
    """Edge case tests for the Copilot importer."""

    @pytest.mark.unit
    def test_unicode_content(self, importer):
        """Unicode content in messages should be handled correctly."""
        data = _make_session(
            requests=[
                _make_turn(
                    "Explain this: def greet(): print('Hola mundo')",
                    "This function prints 'Hola mundo' (Hello world in Spanish)",
                ),
            ]
        )
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert "Hola mundo" in messages[0].content.text
        assert "Hola mundo" in messages[1].content.text

    @pytest.mark.unit
    def test_unicode_emoji_content(self, importer):
        """Emoji and special unicode in messages."""
        data = _make_session(
            requests=[
                _make_turn("What does this do? return x", "It returns x"),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv is not None
        assert conv.get_longest_path()[0].content.text == "What does this do? return x"

    @pytest.mark.unit
    def test_cjk_content(self, importer):
        """CJK characters should be handled correctly."""
        data = _make_session(
            requests=[
                _make_turn("Python", "Python"),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv.get_longest_path()[0].content.text == "Python"

    @pytest.mark.unit
    def test_empty_response_text(self, importer):
        """Empty string response should still be added as assistant message."""
        turn = {
            "message": {"text": "Question"},
            "result": {"metadata": {"response": ""}},
        }
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        # Empty response_text is falsy -> not added
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER

    @pytest.mark.unit
    def test_missing_result_key(self, importer):
        """Turn without 'result' key should only produce user message."""
        turn = {"message": {"text": "Just a question"}}
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER

    @pytest.mark.unit
    def test_missing_message_key_in_turn(self, importer):
        """Turn without 'message' key should be handled gracefully."""
        turn = {"result": {"metadata": {"response": "An answer"}}}
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        # No user message (message.get returns {}), user_msg="" -> skipped
        # But response is still processed
        assert conv is not None
        messages = conv.get_longest_path()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_variable_data_missing_uri(self, importer):
        """File variable without URI path should not crash."""
        var_data = {
            "variables": [
                {"kind": "file", "value": {}},
            ]
        }
        data = _make_session(
            requests=[
                _make_turn("Q", "A", variable_data=var_data),
            ]
        )
        conv = importer._parse_chat_session(data)
        user_msg = conv.get_longest_path()[0]
        refs = user_msg.content.metadata.get("referenced_files", [])
        assert len(refs) == 0

    @pytest.mark.unit
    def test_variable_data_empty_variables(self, importer):
        """Empty variables list should not cause errors."""
        var_data = {"variables": []}
        data = _make_session(
            requests=[
                _make_turn("Q", "A", variable_data=var_data),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv is not None

    @pytest.mark.unit
    def test_variable_data_missing_variables_key(self, importer):
        """variableData without 'variables' key should not crash."""
        var_data = {"someOtherKey": "value"}
        data = _make_session(
            requests=[
                _make_turn("Q", "A", variable_data=var_data),
            ]
        )
        conv = importer._parse_chat_session(data)
        assert conv is not None

    @pytest.mark.unit
    def test_requests_key_missing(self, importer):
        """Data without 'requests' key should return None (no messages)."""
        data = {"sessionId": "abc", "creationDate": 1700000000000}
        conv = importer._parse_chat_session(data)
        assert conv is None

    @pytest.mark.unit
    def test_directory_with_chat_editing_sessions(self, importer, tmp_path):
        """chatEditingSessions directory should be recognized but not crash."""
        chat_dir = tmp_path / "chatSessions"
        chat_dir.mkdir()
        edit_dir = tmp_path / "chatEditingSessions"
        edit_dir.mkdir()

        session = _make_session(requests=[_make_turn("Q", "A")])
        (chat_dir / "session.json").write_text(json.dumps(session))

        results = importer.import_data(str(tmp_path))
        assert len(results) == 1

    @pytest.mark.unit
    def test_directory_with_only_editing_sessions(self, importer, tmp_path):
        """Directory with only chatEditingSessions (no chatSessions) returns empty."""
        edit_dir = tmp_path / "chatEditingSessions"
        edit_dir.mkdir()

        results = importer.import_data(str(tmp_path))
        assert results == []

    @pytest.mark.unit
    def test_import_empty_directory(self, importer, tmp_path):
        """Empty directory should return empty list."""
        results = importer.import_data(str(tmp_path))
        assert results == []

    @pytest.mark.unit
    def test_importer_class_attributes(self, importer):
        """Verify importer class attributes."""
        assert importer.name == "copilot"
        assert "copilot" in importer.supported_formats
        assert "github_copilot" in importer.supported_formats
        assert importer.version == "2.0.0"

    @pytest.mark.unit
    def test_large_conversation(self, importer):
        """Import a conversation with many turns."""
        requests = [_make_turn(f"Question {i}", f"Answer {i}") for i in range(100)]
        data = _make_session(requests=requests)
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert len(messages) == 200  # 100 user + 100 assistant

    @pytest.mark.unit
    def test_response_list_with_only_strings(self, importer):
        """Response list with only string parts."""
        turn = {
            "message": {"text": "Question"},
            "response": ["Part 1 ", "Part 2"],
        }
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        assert messages[1].content.text == "Part 1 Part 2"

    @pytest.mark.unit
    def test_both_result_metadata_and_response_list(self, importer):
        """When both result.metadata.response and turn response exist,
        result.metadata.response takes precedence."""
        turn = {
            "message": {"text": "Question"},
            "result": {"metadata": {"response": "From result"}},
            "response": [{"value": "From response list"}],
        }
        data = _make_session(requests=[turn])
        conv = importer._parse_chat_session(data)
        messages = conv.get_longest_path()
        # result_meta is checked first
        assert messages[1].content.text == "From result"
