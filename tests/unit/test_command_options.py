"""
Unit tests for command options module.

Tests the COMMAND_OPTIONS registry and helper functions
used for shell option completion.
"""

import pytest

from ctk.core.command_options import (COMMAND_OPTIONS, get_command_options,
                                      get_option_enum_values, get_option_info,
                                      has_options)


class TestCommandOptionsRegistry:
    """Test the COMMAND_OPTIONS registry structure"""

    @pytest.mark.unit
    def test_registry_has_find_command(self):
        """Test that find command has options defined"""
        assert "find" in COMMAND_OPTIONS
        assert "options" in COMMAND_OPTIONS["find"]

    @pytest.mark.unit
    def test_registry_has_grep_command(self):
        """Test that grep command has options defined"""
        assert "grep" in COMMAND_OPTIONS
        assert "options" in COMMAND_OPTIONS["grep"]

    @pytest.mark.unit
    def test_find_options_structure(self):
        """Test that find options have required fields"""
        options = COMMAND_OPTIONS["find"]["options"]
        for opt in options:
            assert "name" in opt
            assert "takes_arg" in opt
            assert opt["name"].startswith("-")

    @pytest.mark.unit
    def test_find_has_role_option_with_enum(self):
        """Test that find -role has enum values"""
        options = COMMAND_OPTIONS["find"]["options"]
        role_opt = next((o for o in options if o["name"] == "-role"), None)
        assert role_opt is not None
        assert role_opt["takes_arg"] is True
        assert "enum" in role_opt
        assert "user" in role_opt["enum"]
        assert "assistant" in role_opt["enum"]


class TestGetCommandOptions:
    """Test get_command_options function"""

    @pytest.mark.unit
    def test_get_options_for_find(self):
        """Test getting options for find command"""
        options = get_command_options("find")
        assert len(options) > 0
        names = [o["name"] for o in options]
        assert "-name" in names
        assert "-content" in names
        assert "-role" in names
        assert "-i" in names
        assert "-limit" in names
        assert "-l" in names

    @pytest.mark.unit
    def test_get_options_for_grep(self):
        """Test getting options for grep command"""
        options = get_command_options("grep")
        assert len(options) > 0
        names = [o["name"] for o in options]
        assert "-i" in names
        assert "-v" in names
        assert "-c" in names
        assert "-l" in names

    @pytest.mark.unit
    def test_get_options_for_unknown_command(self):
        """Test getting options for unknown command returns empty list"""
        options = get_command_options("unknown_command")
        assert options == []

    @pytest.mark.unit
    def test_get_options_for_ls(self):
        """Test getting options for ls command"""
        options = get_command_options("ls")
        names = [o["name"] for o in options]
        assert "-l" in names
        assert "-a" in names


class TestGetOptionInfo:
    """Test get_option_info function"""

    @pytest.mark.unit
    def test_get_option_info_exists(self):
        """Test getting info for existing option"""
        info = get_option_info("find", "-name")
        assert info is not None
        assert info["name"] == "-name"
        assert info["takes_arg"] is True

    @pytest.mark.unit
    def test_get_option_info_not_exists(self):
        """Test getting info for non-existent option"""
        info = get_option_info("find", "--nonexistent")
        assert info is None

    @pytest.mark.unit
    def test_get_option_info_unknown_command(self):
        """Test getting option info for unknown command"""
        info = get_option_info("unknown", "-x")
        assert info is None

    @pytest.mark.unit
    def test_get_option_info_flag(self):
        """Test getting info for flag option (no argument)"""
        info = get_option_info("find", "-i")
        assert info is not None
        assert info["takes_arg"] is False


class TestGetOptionEnumValues:
    """Test get_option_enum_values function"""

    @pytest.mark.unit
    def test_get_enum_values_for_role(self):
        """Test getting enum values for -role option"""
        values = get_option_enum_values("find", "-role")
        assert values is not None
        assert "user" in values
        assert "assistant" in values
        assert "system" in values

    @pytest.mark.unit
    def test_get_enum_values_for_type(self):
        """Test getting enum values for -type option"""
        values = get_option_enum_values("find", "-type")
        assert values is not None
        assert "conversation" in values
        assert "message" in values

    @pytest.mark.unit
    def test_get_enum_values_for_non_enum_option(self):
        """Test getting enum values for option without enum"""
        values = get_option_enum_values("find", "-name")
        assert values is None

    @pytest.mark.unit
    def test_get_enum_values_for_export_format(self):
        """Test getting enum values for export format"""
        values = get_option_enum_values("export", "--format")
        assert values is not None
        assert "markdown" in values
        assert "json" in values
        assert "jsonl" in values
        assert "html" in values


class TestHasOptions:
    """Test has_options function"""

    @pytest.mark.unit
    def test_has_options_find(self):
        """Test that find command has options"""
        assert has_options("find") is True

    @pytest.mark.unit
    def test_has_options_grep(self):
        """Test that grep command has options"""
        assert has_options("grep") is True

    @pytest.mark.unit
    def test_has_options_pwd(self):
        """Test that pwd command has no options"""
        assert has_options("pwd") is False

    @pytest.mark.unit
    def test_has_options_unknown(self):
        """Test unknown command has no options"""
        assert has_options("unknown_command") is False
