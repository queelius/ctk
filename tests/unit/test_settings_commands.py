"""
Tests for settings shell commands

Tests: set, get
"""

import pytest
from unittest.mock import Mock

from ctk.core.commands.settings import SettingsCommands, create_settings_commands, SHELL_SETTINGS


class TestSettingsCommands:
    """Tests for set/get commands"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tui = Mock()
        self.tui.uuid_prefix_len = 8  # Default
        self.commands = SettingsCommands(tui_instance=self.tui)

    def test_set_no_args_shows_all_settings(self):
        """Test 'set' with no args shows all available settings"""
        result = self.commands.cmd_set([], '')

        assert result.success
        assert 'Shell Settings:' in result.output
        assert 'uuid_prefix_len' in result.output
        assert '8' in result.output  # default value

    def test_set_single_arg_shows_specific_setting(self):
        """Test 'set <name>' shows specific setting value"""
        result = self.commands.cmd_set(['uuid_prefix_len'], '')

        assert result.success
        assert 'uuid_prefix_len = 8' in result.output

    def test_set_unknown_setting_shows_error(self):
        """Test 'set <unknown>' shows error"""
        result = self.commands.cmd_set(['unknown_setting'], '')

        assert not result.success
        assert "Unknown setting" in result.error

    def test_set_value_updates_tui(self):
        """Test 'set <name> <value>' updates TUI attribute"""
        result = self.commands.cmd_set(['uuid_prefix_len', '12'], '')

        assert result.success
        assert 'Set uuid_prefix_len = 12' in result.output
        assert self.tui.uuid_prefix_len == 12

    def test_set_value_respects_minimum(self):
        """Test 'set' enforces minimum value"""
        result = self.commands.cmd_set(['uuid_prefix_len', '2'], '')

        assert not result.success
        assert 'must be >= 4' in result.error

    def test_set_value_respects_maximum(self):
        """Test 'set' enforces maximum value"""
        result = self.commands.cmd_set(['uuid_prefix_len', '40'], '')

        assert not result.success
        assert 'must be <= 36' in result.error

    def test_set_invalid_type_shows_error(self):
        """Test 'set' with invalid type shows error"""
        result = self.commands.cmd_set(['uuid_prefix_len', 'abc'], '')

        assert not result.success
        assert 'Invalid value type' in result.error

    def test_get_returns_value(self):
        """Test 'get <name>' returns setting value"""
        self.tui.uuid_prefix_len = 10
        result = self.commands.cmd_get(['uuid_prefix_len'], '')

        assert result.success
        assert '10' in result.output

    def test_get_no_args_shows_error(self):
        """Test 'get' with no args shows error"""
        result = self.commands.cmd_get([], '')

        assert not result.success
        assert 'Specify a setting name' in result.error

    def test_get_unknown_setting_shows_error(self):
        """Test 'get <unknown>' shows error"""
        result = self.commands.cmd_get(['unknown_setting'], '')

        assert not result.success
        assert 'Unknown setting' in result.error


class TestSettingsWithoutTUI:
    """Tests for settings commands without TUI instance"""

    def setup_method(self):
        """Set up test fixtures"""
        self.commands = SettingsCommands(tui_instance=None)

    def test_get_returns_default_without_tui(self):
        """Test get returns default value when no TUI"""
        result = self.commands.cmd_get(['uuid_prefix_len'], '')

        assert result.success
        assert '8' in result.output  # default

    def test_set_value_fails_without_tui(self):
        """Test set fails when no TUI instance"""
        result = self.commands.cmd_set(['uuid_prefix_len', '12'], '')

        assert not result.success
        assert 'No TUI instance' in result.error


class TestCreateSettingsCommands:
    """Tests for create_settings_commands factory function"""

    def test_creates_expected_commands(self):
        """Test factory creates set and get commands"""
        tui = Mock()
        tui.uuid_prefix_len = 8
        commands = create_settings_commands(tui_instance=tui)

        assert 'set' in commands
        assert 'get' in commands
        assert callable(commands['set'])
        assert callable(commands['get'])

    def test_commands_work_with_tui(self):
        """Test created commands work with TUI instance"""
        tui = Mock()
        tui.uuid_prefix_len = 8
        commands = create_settings_commands(tui_instance=tui)

        # Test set
        result = commands['set'](['uuid_prefix_len', '16'], '')
        assert result.success
        assert tui.uuid_prefix_len == 16

        # Test get
        result = commands['get'](['uuid_prefix_len'], '')
        assert result.success
        assert '16' in result.output


class TestShellSettingsDefinition:
    """Tests for SHELL_SETTINGS configuration"""

    def test_uuid_prefix_len_defined(self):
        """Test uuid_prefix_len setting is properly defined"""
        assert 'uuid_prefix_len' in SHELL_SETTINGS

        spec = SHELL_SETTINGS['uuid_prefix_len']
        assert spec['default'] == 8
        assert spec['type'] == int
        assert spec['min'] == 4
        assert spec['max'] == 36
        assert 'description' in spec
