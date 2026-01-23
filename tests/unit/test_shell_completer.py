"""
Tests for shell tab completion.

Tests: command completion, path completion, slug completion
"""

from unittest.mock import MagicMock, Mock

import pytest
from prompt_toolkit.document import Document

from ctk.core.shell_completer import ShellCompleter, create_shell_completer
from ctk.core.vfs_navigator import VFSEntry


class TestCommandCompletion:
    """Tests for command name completion"""

    def setup_method(self):
        """Set up test fixtures"""
        self.completer = ShellCompleter()

    def test_empty_input_shows_all_commands(self):
        """Test empty input shows command completions"""
        doc = Document("")
        completions = list(self.completer.get_completions(doc, None))

        assert len(completions) > 0
        command_texts = [c.text for c in completions]
        assert "cd" in command_texts
        assert "ls" in command_texts
        assert "cat" in command_texts

    def test_partial_command_shows_matches(self):
        """Test partial command filters completions"""
        doc = Document("c")
        completions = list(self.completer.get_completions(doc, None))

        command_texts = [c.text for c in completions]
        assert "cd" in command_texts
        assert "cat" in command_texts
        assert "clear" in command_texts
        assert "ls" not in command_texts  # doesn't start with 'c'

    def test_full_command_with_space_shows_no_command_completions(self):
        """Test full command followed by space doesn't complete commands"""
        doc = Document("cd ")
        completions = list(self.completer.get_completions(doc, None))

        # Should be path completions, not commands
        # (but we have no tui, so should be empty)
        command_texts = [c.text for c in completions]
        assert "cd" not in command_texts


class TestPathCompletion:
    """Tests for VFS path completion"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tui = Mock()
        self.tui.vfs_cwd = "/"
        self.tui.uuid_prefix_len = 8
        self.tui.vfs_navigator = Mock()
        self.completer = ShellCompleter(tui_instance=self.tui)

    def test_path_completion_after_cd(self):
        """Test path completion after cd command"""
        # Mock directory entries
        entries = [
            VFSEntry(name="chats", is_directory=True),
            VFSEntry(name="starred", is_directory=True),
            VFSEntry(name="pinned", is_directory=True),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document("cd ")
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert "chats/" in texts
        assert "starred/" in texts

    def test_path_completion_with_partial(self):
        """Test path completion with partial input"""
        entries = [
            VFSEntry(name="chats", is_directory=True),
            VFSEntry(name="starred", is_directory=True),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document("cd ch")
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert "chats/" in texts
        assert "starred/" not in texts  # doesn't match 'ch'


class TestSlugCompletion:
    """Tests for slug-based path completion"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tui = Mock()
        self.tui.vfs_cwd = "/chats"
        self.tui.uuid_prefix_len = 8
        self.tui.vfs_navigator = Mock()
        # Set up mock index for /chats completions (fast path)
        self.mock_index = Mock()
        self.tui.vfs_navigator.index = self.mock_index
        self.completer = ShellCompleter(tui_instance=self.tui)

    def test_slug_completion(self):
        """Test completion shows slugs for conversations (via index)"""
        # Mock the index get_completions to return our test data
        # Returns list of (display_text, conv_id, slug) tuples
        self.mock_index.get_completions.return_value = [
            (
                "my-python-chat",
                "abc12345-1234-5678-9abc-def012345678",
                "my-python-chat",
            ),
        ]

        doc = Document("cd my")
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert "my-python-chat/" in texts

    def test_uuid_prefix_completion(self):
        """Test completion shows UUID prefix when no slug"""
        # Return a conversation without a slug - will show UUID prefix
        self.mock_index.get_completions.return_value = [
            ("abc12345", "abc12345-1234-5678-9abc-def012345678", None),
        ]

        doc = Document("cd abc")
        completions = list(self.completer.get_completions(doc, None))

        # Should match UUID prefix
        texts = [c.text for c in completions]
        assert len(texts) > 0
        assert any("abc12345" in t for t in texts)

    def test_partial_slug_completion(self):
        """Test partial slug matching via index"""
        # Mock the index get_completions with matching entries
        self.mock_index.get_completions.return_value = [
            ("python-tips", "id1", "python-tips"),
            ("python-hints", "id2", "python-hints"),
            # Note: 'python' prefix won't match 'java-basics' so it won't be returned
        ]

        doc = Document("cd python")
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert "python-tips/" in texts
        assert "python-hints/" in texts
        # java-basics not included because it doesn't match 'python' prefix

    def test_absolute_path_completion(self):
        """Test completion with absolute paths (uses standard path, not index)"""
        entries = [
            VFSEntry(name="chats", is_directory=True),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document("cd /ch")
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert "/chats/" in texts


class TestCreateShellCompleter:
    """Tests for create_shell_completer factory"""

    def test_creates_completer(self):
        """Test factory creates completer instance"""
        completer = create_shell_completer()
        assert isinstance(completer, ShellCompleter)

    def test_creates_completer_with_tui(self):
        """Test factory creates completer with TUI instance"""
        tui = Mock()
        completer = create_shell_completer(tui_instance=tui)
        assert completer.tui is tui
