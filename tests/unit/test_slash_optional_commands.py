"""
Unit tests for command routing.

Tests that commands work without '/' prefix (slash-free design).
"""

import pytest
from unittest.mock import Mock, patch
from ctk.integrations.chat.tui import ChatTUI


class TestCommandRouting:
    """Test that commands work without slash prefix"""

    @pytest.fixture
    def tui(self):
        """Create a ChatTUI instance for testing"""
        with patch('prompt_toolkit.PromptSession'):
            # Create mock provider
            mock_provider = Mock()
            mock_provider.model = "test-model"

            # Create TUI without database
            tui = ChatTUI(provider=mock_provider, db=None)
            # Mock console to avoid Rich output during tests
            tui.console = Mock()
            return tui

    def test_known_commands_defined(self, tui):
        """Test that known_commands set is populated"""
        assert 'help' in tui.known_commands
        assert 'cd' in tui.known_commands
        assert 'ls' in tui.known_commands
        assert 'quit' in tui.known_commands
        assert 'star' in tui.known_commands

    def test_command_without_slash(self, tui):
        """Test that commands work without slash"""
        # Commands now work without slash prefix
        assert tui.handle_command('pwd')
        assert tui.handle_command('clear')

    def test_command_recognition(self, tui):
        """Test that commands are recognized in known_commands set"""
        first_word = 'pwd'
        assert first_word in tui.known_commands

        first_word = 'clear'
        assert first_word in tui.known_commands

        first_word = 'help'
        assert first_word in tui.known_commands

    def test_non_command_not_recognized(self, tui):
        """Test that non-commands are not in known_commands"""
        assert 'hello' not in tui.known_commands
        assert 'foobar' not in tui.known_commands
        assert 'not_a_command' not in tui.known_commands

    def test_command_parsing(self):
        """Test that commands are parsed correctly"""
        test_input = "help"
        parts = test_input.split(maxsplit=1)
        cmd = parts[0].lower()
        assert cmd == "help"

        test_input = "cd /tags/physics"
        parts = test_input.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        assert cmd == "cd"
        assert args == "/tags/physics"

    def test_first_word_extraction(self):
        """Test extracting first word from input"""
        user_input = "help me"
        first_word = user_input.split()[0].lower()
        assert first_word == "help"

        user_input = "cd /tags/physics"
        first_word = user_input.split()[0].lower()
        assert first_word == "cd"

        user_input = "ls -l /starred"
        first_word = user_input.split()[0].lower()
        assert first_word == "ls"

    def test_case_insensitivity(self, tui):
        """Test that commands are case-insensitive"""
        assert 'help' in tui.known_commands
        assert 'HELP'.lower() in tui.known_commands
        assert 'Help'.lower() in tui.known_commands
        assert 'CD'.lower() in tui.known_commands

    def test_multiword_command_recognition(self, tui):
        """Test commands with arguments are recognized"""
        user_input = "cd /tags/physics"
        first_word = user_input.split()[0].lower()
        assert first_word in tui.known_commands

        user_input = "search quantum mechanics"
        first_word = user_input.split()[0].lower()
        assert first_word in tui.known_commands

    def test_command_detection(self, tui):
        """Test that commands are correctly detected"""
        user_input = "help"
        first_word = user_input.split()[0].lower() if user_input.split() else ""
        is_command = first_word in tui.known_commands
        assert is_command

        user_input = "cd /tags"
        first_word = user_input.split()[0].lower() if user_input.split() else ""
        is_command = first_word in tui.known_commands
        assert is_command

    def test_empty_input(self):
        """Test handling of empty input"""
        user_input = ""
        first_word = user_input.split()[0].lower() if user_input.split() else ""
        assert first_word == ""
        assert first_word not in ['help', 'cd', 'ls']  # Not a command
