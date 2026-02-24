"""
Unit tests for new command modules.

Tests the command modules created for TUI mode unification:
- database.py: save, load, search, list
- llm.py: temp, model, models, regenerate, retry, stream
- session.py: clear, new-chat, system, context, user, stats
- tree_nav.py: fork, branch, merge, goto-*, where, alternatives
"""

from unittest.mock import MagicMock, Mock

import pytest

from ctk.core.commands.database import create_database_commands
from ctk.core.commands.llm import create_llm_commands
from ctk.core.commands.session import create_session_commands
from ctk.core.commands.tree_nav import create_tree_nav_commands


class TestDatabaseCommands:
    """Test database operation commands"""

    @pytest.fixture
    def mock_tui(self):
        """Create a mock TUI instance"""
        tui = Mock()
        tui.root = None
        tui.current_conversation_id = None
        tui.message_map = {}
        tui.conversation_title = None
        tui.provider = Mock()
        tui.provider.model = "test-model"
        return tui

    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        return Mock()

    @pytest.mark.unit
    def test_create_database_commands_returns_dict(self):
        """Test that create_database_commands returns a dictionary"""
        cmds = create_database_commands()
        assert isinstance(cmds, dict)

    @pytest.mark.unit
    def test_database_commands_include_required(self):
        """Test that all required commands are present"""
        cmds = create_database_commands()
        assert "save" in cmds
        assert "load" in cmds
        assert "search" in cmds
        assert "list" in cmds

    @pytest.mark.unit
    def test_save_no_tui(self):
        """Test save command with no TUI"""
        cmds = create_database_commands()
        result = cmds["save"]("")
        assert not result.success
        assert "TUI not available" in result.error

    @pytest.mark.unit
    def test_save_no_db(self, mock_tui):
        """Test save command with no database"""
        cmds = create_database_commands(tui_instance=mock_tui)
        result = cmds["save"]("")
        assert not result.success
        assert "No database configured" in result.error

    @pytest.mark.unit
    def test_save_no_messages(self, mock_tui, mock_db):
        """Test save command with no messages"""
        cmds = create_database_commands(db=mock_db, tui_instance=mock_tui)
        result = cmds["save"]("")
        assert not result.success
        assert "No messages to save" in result.error

    @pytest.mark.unit
    def test_load_no_id(self, mock_tui, mock_db):
        """Test load command without conversation ID"""
        cmds = create_database_commands(db=mock_db, tui_instance=mock_tui)
        result = cmds["load"]("")
        assert not result.success
        assert "requires a conversation ID" in result.error

    @pytest.mark.unit
    def test_search_no_query(self, mock_tui, mock_db):
        """Test search command without query"""
        cmds = create_database_commands(db=mock_db, tui_instance=mock_tui)
        result = cmds["search"]("")
        assert not result.success
        assert "requires a query" in result.error


class TestLLMCommands:
    """Test LLM control commands"""

    @pytest.fixture
    def mock_tui(self):
        """Create a mock TUI instance"""
        tui = Mock()
        tui.temperature = 0.7
        tui.provider = Mock()
        tui.provider.model = "test-model"
        tui.provider.name = "test-provider"
        tui.streaming = True
        tui.num_ctx = None
        return tui

    @pytest.mark.unit
    def test_create_llm_commands_returns_dict(self):
        """Test that create_llm_commands returns a dictionary"""
        cmds = create_llm_commands()
        assert isinstance(cmds, dict)

    @pytest.mark.unit
    def test_llm_commands_include_required(self):
        """Test that all required commands are present"""
        cmds = create_llm_commands()
        assert "temp" in cmds
        assert "model" in cmds
        assert "models" in cmds
        assert "regenerate" in cmds
        assert "retry" in cmds
        assert "stream" in cmds
        assert "num_ctx" in cmds

    @pytest.mark.unit
    def test_temp_get(self, mock_tui):
        """Test getting temperature"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["temp"]("")
        assert result.success
        assert "0.7" in result.output

    @pytest.mark.unit
    def test_temp_set_valid(self, mock_tui):
        """Test setting valid temperature"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["temp"]("0.5")
        assert result.success
        assert "0.5" in result.output
        assert mock_tui.temperature == 0.5

    @pytest.mark.unit
    def test_temp_set_invalid_range(self, mock_tui):
        """Test setting temperature outside valid range"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["temp"]("3.0")
        assert not result.success
        assert "between 0.0 and 2.0" in result.error

    @pytest.mark.unit
    def test_temp_set_invalid_format(self, mock_tui):
        """Test setting non-numeric temperature"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["temp"]("abc")
        assert not result.success
        assert "Invalid temperature" in result.error

    @pytest.mark.unit
    def test_model_get(self, mock_tui):
        """Test getting current model"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["model"]("")
        assert result.success
        assert "test-model" in result.output

    @pytest.mark.unit
    def test_model_set(self, mock_tui):
        """Test setting model"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["model"]("new-model")
        assert result.success
        assert "new-model" in result.output
        assert mock_tui.provider.model == "new-model"

    @pytest.mark.unit
    def test_stream_toggle(self, mock_tui):
        """Test toggling streaming"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        initial = mock_tui.streaming
        result = cmds["stream"]("")
        assert result.success
        assert mock_tui.streaming != initial

    @pytest.mark.unit
    def test_num_ctx_get_default(self, mock_tui):
        """Test getting default context window"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["num_ctx"]("")
        assert result.success
        assert "not set" in result.output

    @pytest.mark.unit
    def test_num_ctx_set(self, mock_tui):
        """Test setting context window"""
        cmds = create_llm_commands(tui_instance=mock_tui)
        result = cmds["num_ctx"]("8192")
        assert result.success
        assert "8,192" in result.output
        assert mock_tui.num_ctx == 8192


class TestSessionCommands:
    """Test session management commands"""

    @pytest.fixture
    def mock_tui(self):
        """Create a mock TUI instance"""
        tui = Mock()
        tui.root = None
        tui.current_message = None
        tui.message_map = {}
        tui.current_conversation_id = None
        tui.conversation_title = None
        tui.conversation_project = None
        tui.conversation_model = "test-model"
        tui.provider = Mock()
        tui.provider.model = "test-model"
        tui.current_user = None
        return tui

    @pytest.mark.unit
    def test_create_session_commands_returns_dict(self):
        """Test that create_session_commands returns a dictionary"""
        cmds = create_session_commands()
        assert isinstance(cmds, dict)

    @pytest.mark.unit
    def test_session_commands_include_required(self):
        """Test that all required commands are present"""
        cmds = create_session_commands()
        assert "clear" in cmds
        assert "new-chat" in cmds
        assert "system" in cmds
        assert "context" in cmds
        assert "user" in cmds
        assert "stats" in cmds
        assert "project" in cmds
        assert "history" in cmds

    @pytest.mark.unit
    def test_clear(self, mock_tui):
        """Test clear command"""
        mock_tui.root = Mock()  # Has messages
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["clear"]("")
        assert result.success
        assert mock_tui.root is None
        assert mock_tui.current_message is None

    @pytest.mark.unit
    def test_new_chat_no_title(self, mock_tui):
        """Test new-chat without title"""
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["new-chat"]("")
        assert result.success
        assert "Started new conversation" in result.output
        assert mock_tui.conversation_title is None

    @pytest.mark.unit
    def test_new_chat_with_title(self, mock_tui):
        """Test new-chat with title"""
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["new-chat"]("Test Chat")
        assert result.success
        assert "Test Chat" in result.output
        assert mock_tui.conversation_title == "Test Chat"

    @pytest.mark.unit
    def test_system_no_message(self, mock_tui):
        """Test system command without message"""
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["system"]("")
        assert not result.success
        assert "requires a message" in result.error

    @pytest.mark.unit
    def test_user_get_default(self, mock_tui):
        """Test getting default user"""
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["user"]("")
        assert result.success
        assert "No user set" in result.output

    @pytest.mark.unit
    def test_user_set(self, mock_tui):
        """Test setting user"""
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["user"]("Alice")
        assert result.success
        assert "Alice" in result.output
        assert mock_tui.current_user == "Alice"

    @pytest.mark.unit
    def test_project_get_default(self, mock_tui):
        """Test getting default project"""
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["project"]("")
        assert result.success
        assert "No project set" in result.output

    @pytest.mark.unit
    def test_project_set(self, mock_tui):
        """Test setting project"""
        cmds = create_session_commands(tui_instance=mock_tui)
        result = cmds["project"]("my-app")
        assert result.success
        assert "my-app" in result.output
        assert mock_tui.conversation_project == "my-app"


class TestTreeNavCommands:
    """Test tree navigation commands"""

    @pytest.fixture
    def mock_tui(self):
        """Create a mock TUI instance"""
        return Mock()

    @pytest.mark.unit
    def test_create_tree_nav_commands_returns_dict(self):
        """Test that create_tree_nav_commands returns a dictionary"""
        cmds = create_tree_nav_commands()
        assert isinstance(cmds, dict)

    @pytest.mark.unit
    def test_tree_nav_commands_include_required(self):
        """Test that all required commands are present"""
        cmds = create_tree_nav_commands()
        assert "fork" in cmds
        assert "fork-id" in cmds
        assert "branch" in cmds
        assert "merge" in cmds
        assert "goto-longest" in cmds
        assert "goto-latest" in cmds
        assert "where" in cmds
        assert "alternatives" in cmds
        assert "rollback" in cmds
        assert "split" in cmds
        assert "prune" in cmds
        assert "keep-path" in cmds

    @pytest.mark.unit
    def test_fork_no_args(self, mock_tui):
        """Test fork without arguments"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["fork"]("")
        assert not result.success
        assert "requires a message number" in result.error

    @pytest.mark.unit
    def test_fork_invalid_number(self, mock_tui):
        """Test fork with invalid number"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["fork"]("abc")
        assert not result.success
        assert "Invalid message number" in result.error

    @pytest.mark.unit
    def test_fork_id_no_args(self, mock_tui):
        """Test fork-id without arguments"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["fork-id"]("")
        assert not result.success
        assert "requires a message ID" in result.error

    @pytest.mark.unit
    def test_merge_no_args(self, mock_tui):
        """Test merge without arguments"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["merge"]("")
        assert not result.success
        assert "requires a conversation ID" in result.error

    @pytest.mark.unit
    def test_rollback_default(self, mock_tui):
        """Test rollback with default value"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["rollback"]("")
        mock_tui.rollback.assert_called_once_with(1)

    @pytest.mark.unit
    def test_rollback_with_number(self, mock_tui):
        """Test rollback with specific number"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["rollback"]("3")
        mock_tui.rollback.assert_called_once_with(3)

    @pytest.mark.unit
    def test_split_no_args(self, mock_tui):
        """Test split without arguments"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["split"]("")
        assert not result.success
        assert "requires a message number" in result.error

    @pytest.mark.unit
    def test_prune_no_args(self, mock_tui):
        """Test prune without arguments"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["prune"]("")
        assert not result.success
        assert "requires a message ID" in result.error

    @pytest.mark.unit
    def test_keep_path_no_args(self, mock_tui):
        """Test keep-path without arguments"""
        cmds = create_tree_nav_commands(tui_instance=mock_tui)
        result = cmds["keep-path"]("")
        assert not result.success
        assert "requires a path number" in result.error
