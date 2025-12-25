"""
Tests for shell tab completion.

Tests: command completion, path completion, slug completion
"""

import pytest
from unittest.mock import Mock, MagicMock
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
        doc = Document('')
        completions = list(self.completer.get_completions(doc, None))

        assert len(completions) > 0
        command_texts = [c.text for c in completions]
        assert 'cd' in command_texts
        assert 'ls' in command_texts
        assert 'cat' in command_texts

    def test_partial_command_shows_matches(self):
        """Test partial command filters completions"""
        doc = Document('c')
        completions = list(self.completer.get_completions(doc, None))

        command_texts = [c.text for c in completions]
        assert 'cd' in command_texts
        assert 'cat' in command_texts
        assert 'clear' in command_texts
        assert 'ls' not in command_texts  # doesn't start with 'c'

    def test_full_command_with_space_shows_no_command_completions(self):
        """Test full command followed by space doesn't complete commands"""
        doc = Document('cd ')
        completions = list(self.completer.get_completions(doc, None))

        # Should be path completions, not commands
        # (but we have no tui, so should be empty)
        command_texts = [c.text for c in completions]
        assert 'cd' not in command_texts


class TestPathCompletion:
    """Tests for VFS path completion"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tui = Mock()
        self.tui.vfs_cwd = '/'
        self.tui.uuid_prefix_len = 8
        self.tui.vfs_navigator = Mock()
        self.completer = ShellCompleter(tui_instance=self.tui)

    def test_path_completion_after_cd(self):
        """Test path completion after cd command"""
        # Mock directory entries
        entries = [
            VFSEntry(name='chats', is_directory=True),
            VFSEntry(name='starred', is_directory=True),
            VFSEntry(name='pinned', is_directory=True),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document('cd ')
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert 'chats/' in texts
        assert 'starred/' in texts

    def test_path_completion_with_partial(self):
        """Test path completion with partial input"""
        entries = [
            VFSEntry(name='chats', is_directory=True),
            VFSEntry(name='starred', is_directory=True),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document('cd ch')
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert 'chats/' in texts
        assert 'starred/' not in texts  # doesn't match 'ch'


class TestSlugCompletion:
    """Tests for slug-based path completion"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tui = Mock()
        self.tui.vfs_cwd = '/chats'
        self.tui.uuid_prefix_len = 8
        self.tui.vfs_navigator = Mock()
        self.completer = ShellCompleter(tui_instance=self.tui)

    def test_slug_completion(self):
        """Test completion shows slugs for conversations"""
        entries = [
            VFSEntry(
                name='abc12345-...',
                is_directory=True,
                conversation_id='abc12345-1234-5678-9abc-def012345678',
                slug='my-python-chat'
            ),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document('cd my')
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert 'my-python-chat/' in texts

    def test_uuid_prefix_completion(self):
        """Test completion shows UUID prefix as alternative"""
        entries = [
            VFSEntry(
                name='abc12345-...',
                is_directory=True,
                conversation_id='abc12345-1234-5678-9abc-def012345678',
                slug='my-python-chat'
            ),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document('cd abc')
        completions = list(self.completer.get_completions(doc, None))

        # Should match UUID prefix
        texts = [c.text for c in completions]
        assert len(texts) > 0
        # The slug starts with 'm' not 'a', so should match uuid instead
        assert any('abc12345' in t for t in texts)

    def test_partial_slug_completion(self):
        """Test partial slug matching"""
        entries = [
            VFSEntry(
                name='...',
                is_directory=True,
                conversation_id='id1',
                slug='python-tips'
            ),
            VFSEntry(
                name='...',
                is_directory=True,
                conversation_id='id2',
                slug='python-hints'
            ),
            VFSEntry(
                name='...',
                is_directory=True,
                conversation_id='id3',
                slug='java-basics'
            ),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document('cd python')
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert 'python-tips/' in texts
        assert 'python-hints/' in texts
        assert 'java-basics/' not in texts

    def test_absolute_path_completion(self):
        """Test completion with absolute paths"""
        entries = [
            VFSEntry(name='chats', is_directory=True),
        ]
        self.tui.vfs_navigator.list_directory.return_value = entries

        doc = Document('cd /ch')
        completions = list(self.completer.get_completions(doc, None))

        texts = [c.text for c in completions]
        assert '/chats/' in texts


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
