"""
Unit tests for navigation commands

Tests the NavigationCommands class for:
- cd: Change directory with path resolution, prefix matching
- ls: List directory contents
- pwd: Print working directory
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from ctk.core.command_dispatcher import CommandResult
from ctk.core.commands.navigation import (NavigationCommands,
                                          create_navigation_commands)
from ctk.core.vfs import PathType, VFSPath, VFSPathParser
from ctk.core.vfs_navigator import VFSEntry, VFSNavigator


class TestNavigationCommands:
    """Test NavigationCommands class"""

    @pytest.fixture
    def mock_navigator(self):
        """Create mock VFS navigator"""
        navigator = Mock(spec=VFSNavigator)
        return navigator

    @pytest.fixture
    def mock_tui(self):
        """Create mock TUI instance with VFS state"""
        tui = Mock()
        tui.vfs_cwd = "/chats"
        tui._update_environment = Mock()
        return tui

    @pytest.fixture
    def nav_commands(self, mock_navigator, mock_tui):
        """Create NavigationCommands instance with mocks"""
        return NavigationCommands(mock_navigator, mock_tui)

    # Initialization Tests

    @pytest.mark.unit
    def test_init_requires_tui(self, mock_navigator):
        """Test that NavigationCommands requires TUI instance"""
        with pytest.raises(ValueError, match="requires tui_instance"):
            NavigationCommands(mock_navigator, None)

    @pytest.mark.unit
    def test_init_with_tui(self, mock_navigator, mock_tui):
        """Test successful initialization with TUI"""
        nav = NavigationCommands(mock_navigator, mock_tui)
        assert nav.navigator is mock_navigator
        assert nav.tui is mock_tui

    # cmd_cd Tests - Basic Navigation

    @pytest.mark.unit
    def test_cd_no_args_goes_to_root(self, nav_commands, mock_navigator, mock_tui):
        """Test cd with no arguments changes to root"""
        # Mock path parsing and directory listing
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []

            result = nav_commands.cmd_cd([])

            assert result.success is True
            assert mock_tui.vfs_cwd == "/"
            mock_tui._update_environment.assert_called_once()

    @pytest.mark.unit
    def test_cd_absolute_path(self, nav_commands, mock_navigator, mock_tui):
        """Test cd with absolute path"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []
            # resolve_prefix should return None for absolute paths (no prefix resolution)
            mock_navigator.resolve_prefix.return_value = None

            result = nav_commands.cmd_cd(["/starred"])

            assert result.success is True
            assert mock_tui.vfs_cwd == "/starred"
            mock_tui._update_environment.assert_called_once()

    @pytest.mark.unit
    def test_cd_relative_path(self, nav_commands, mock_navigator, mock_tui):
        """Test cd with relative path"""
        mock_tui.vfs_cwd = "/chats"
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []
            # No prefix resolution for this test
            mock_navigator.resolve_prefix.return_value = None

            result = nav_commands.cmd_cd(["abc123"])

            assert result.success is True
            assert mock_tui.vfs_cwd == "/chats/abc123"

    @pytest.mark.unit
    def test_cd_parent_directory(self, nav_commands, mock_navigator, mock_tui):
        """Test cd .. goes up one level"""
        mock_tui.vfs_cwd = "/chats/abc123"

        # Mock the path parser and directory listing
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []
            mock_navigator.resolve_prefix.return_value = None

            result = nav_commands.cmd_cd([".."])

            assert result.success is True
            assert mock_tui.vfs_cwd == "/chats"

    @pytest.mark.unit
    def test_cd_parent_from_root(self, nav_commands, mock_navigator, mock_tui):
        """Test cd .. from root stays at root"""
        mock_tui.vfs_cwd = "/"

        result = nav_commands.cmd_cd([".."])

        assert result.success is True
        assert result.output == "Already at root\n"
        assert mock_tui.vfs_cwd == "/"

    @pytest.mark.unit
    def test_cd_multiple_levels_up(self, nav_commands, mock_navigator, mock_tui):
        """Test cd .. from deep path"""
        mock_tui.vfs_cwd = "/chats/abc123/m1/m2"

        result = nav_commands.cmd_cd([".."])

        assert result.success is True
        assert mock_tui.vfs_cwd == "/chats/abc123/m1"

    @pytest.mark.unit
    def test_cd_relative_from_trailing_slash(
        self, nav_commands, mock_navigator, mock_tui
    ):
        """Test cd with relative path when current path has trailing slash"""
        mock_tui.vfs_cwd = "/chats/"
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []
            mock_navigator.resolve_prefix.return_value = None

            result = nav_commands.cmd_cd(["abc123"])

            assert result.success is True
            assert mock_tui.vfs_cwd == "/chats/abc123"

    # cmd_cd Tests - Prefix Resolution

    @pytest.mark.unit
    def test_cd_prefix_resolution_success(self, nav_commands, mock_navigator, mock_tui):
        """Test cd with prefix that resolves to full ID"""
        mock_tui.vfs_cwd = "/chats"

        # Setup mocks for prefix resolution
        mock_parent_parsed = Mock(spec=VFSPath)
        mock_final_parsed = Mock(spec=VFSPath)
        mock_final_parsed.is_directory = True

        def parse_side_effect(path):
            if path == "/chats":
                return mock_parent_parsed
            elif path == "/chats/abc123def456":
                return mock_final_parsed
            else:
                return Mock(spec=VFSPath, is_directory=True)

        with patch.object(VFSPathParser, "parse", side_effect=parse_side_effect):
            mock_navigator.resolve_prefix.return_value = "abc123def456"
            mock_navigator.list_directory.return_value = []

            result = nav_commands.cmd_cd(["abc123"])

            assert result.success is True
            assert mock_tui.vfs_cwd == "/chats/abc123def456"
            assert "Resolved 'abc123' to: abc123def456" in result.output

    @pytest.mark.unit
    def test_cd_prefix_resolution_failure(self, nav_commands, mock_navigator, mock_tui):
        """Test cd with prefix that doesn't resolve"""
        mock_tui.vfs_cwd = "/chats"

        mock_parent_parsed = Mock(spec=VFSPath)
        mock_final_parsed = Mock(spec=VFSPath)
        mock_final_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_final_parsed):
            # Prefix resolution returns None (no match)
            mock_navigator.resolve_prefix.return_value = None
            mock_navigator.list_directory.return_value = []

            result = nav_commands.cmd_cd(["abc"])

            assert result.success is True
            # Should use original path when prefix doesn't resolve
            assert mock_tui.vfs_cwd == "/chats/abc"

    @pytest.mark.unit
    def test_cd_prefix_resolution_error(self, nav_commands, mock_navigator, mock_tui):
        """Test cd when prefix resolution raises ValueError"""
        mock_tui.vfs_cwd = "/chats"

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            # Prefix resolution raises error (multiple matches)
            mock_navigator.resolve_prefix.side_effect = ValueError("Multiple matches")
            mock_navigator.list_directory.return_value = []

            result = nav_commands.cmd_cd(["abc"])

            # Should fall back to using original path
            assert result.success is True

    @pytest.mark.unit
    def test_cd_short_prefix_no_resolution(
        self, nav_commands, mock_navigator, mock_tui
    ):
        """Test cd with prefix shorter than 3 chars doesn't trigger resolution"""
        mock_tui.vfs_cwd = "/chats"

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []

            result = nav_commands.cmd_cd(["ab"])

            # Prefix resolution should not be attempted for short strings
            mock_navigator.resolve_prefix.assert_not_called()
            assert result.success is True

    # cmd_cd Tests - Error Handling

    @pytest.mark.unit
    def test_cd_invalid_path(self, nav_commands, mock_navigator, mock_tui):
        """Test cd to invalid path"""
        with patch.object(
            VFSPathParser, "parse", side_effect=ValueError("Invalid path")
        ):
            result = nav_commands.cmd_cd(["/invalid"])

            assert result.success is False
            assert "cd: Invalid path" in result.error

    @pytest.mark.unit
    def test_cd_nonexistent_directory(self, nav_commands, mock_navigator, mock_tui):
        """Test cd to directory that doesn't exist"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.side_effect = ValueError(
                "Directory not found"
            )
            mock_navigator.resolve_prefix.return_value = None

            result = nav_commands.cmd_cd(["/nonexistent"])

            assert result.success is False
            assert "cd: Directory not found" in result.error

    @pytest.mark.unit
    def test_cd_to_file(self, nav_commands, mock_navigator, mock_tui):
        """Test cd to file path (not directory)"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = False  # It's a file

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.resolve_prefix.return_value = None

            result = nav_commands.cmd_cd(["/chats/abc123/m1/text"])

            # Should succeed because file paths don't trigger list_directory
            assert result.success is True

    # cmd_ls Tests - Basic Listing

    @pytest.mark.unit
    def test_ls_current_directory(self, nav_commands, mock_navigator, mock_tui):
        """Test ls with no arguments lists current directory"""
        mock_tui.vfs_cwd = "/chats"
        mock_parsed = Mock(spec=VFSPath)

        entries = [
            VFSEntry(name="abc123", is_directory=True, conversation_id="abc123"),
            VFSEntry(name="def456", is_directory=True, conversation_id="def456"),
        ]

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = entries

            result = nav_commands.cmd_ls([])

            assert result.success is True
            assert "abc123/" in result.output
            assert "def456/" in result.output

    @pytest.mark.unit
    def test_ls_absolute_path(self, nav_commands, mock_navigator, mock_tui):
        """Test ls with absolute path"""
        mock_parsed = Mock(spec=VFSPath)

        entries = [
            VFSEntry(name="chats", is_directory=True),
            VFSEntry(name="starred", is_directory=True),
        ]

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = entries

            result = nav_commands.cmd_ls(["/"])

            assert result.success is True
            assert "chats/" in result.output
            assert "starred/" in result.output

    @pytest.mark.unit
    def test_ls_relative_path(self, nav_commands, mock_navigator, mock_tui):
        """Test ls with relative path"""
        mock_tui.vfs_cwd = "/chats"
        mock_parsed = Mock(spec=VFSPath)

        entries = [
            VFSEntry(name="m1", is_directory=True, message_id="msg1"),
        ]

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = entries

            result = nav_commands.cmd_ls(["abc123"])

            assert result.success is True
            assert "m1/" in result.output
            # Should have called parse with combined path
            VFSPathParser.parse.assert_called_with("/chats/abc123")

    @pytest.mark.unit
    def test_ls_empty_directory(self, nav_commands, mock_navigator, mock_tui):
        """Test ls on empty directory"""
        mock_parsed = Mock(spec=VFSPath)

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []

            result = nav_commands.cmd_ls([])

            assert result.success is True
            assert result.output == ""

    @pytest.mark.unit
    def test_ls_files_no_trailing_slash(self, nav_commands, mock_navigator, mock_tui):
        """Test ls shows files without trailing slash"""
        mock_parsed = Mock(spec=VFSPath)

        entries = [
            VFSEntry(name="text", is_directory=False),
            VFSEntry(name="role", is_directory=False),
            VFSEntry(name="m1", is_directory=True),
        ]

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = entries

            result = nav_commands.cmd_ls([])

            assert result.success is True
            # Files should not have trailing slash
            assert "\ntext\n" in result.output or result.output.startswith("text\n")
            assert "\nrole\n" in result.output or "role\n" in result.output
            # Directories should have trailing slash
            assert "m1/" in result.output

    @pytest.mark.unit
    def test_ls_with_long_format_flag(self, nav_commands, mock_navigator, mock_tui):
        """Test ls -l flag (long format)"""
        mock_parsed = Mock(spec=VFSPath)

        entries = [
            VFSEntry(name="abc123", is_directory=True),
            VFSEntry(name="text", is_directory=False),
        ]

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = entries

            result = nav_commands.cmd_ls(["-l"])

            assert result.success is True
            # Long format still shows trailing slashes for directories
            assert "abc123/" in result.output

    @pytest.mark.unit
    def test_ls_relative_path_with_trailing_slash(
        self, nav_commands, mock_navigator, mock_tui
    ):
        """Test ls with relative path when cwd has trailing slash"""
        mock_tui.vfs_cwd = "/chats/"
        mock_parsed = Mock(spec=VFSPath)

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []

            result = nav_commands.cmd_ls(["abc123"])

            VFSPathParser.parse.assert_called_with("/chats/abc123")

    # cmd_ls Tests - Error Handling

    @pytest.mark.unit
    def test_ls_invalid_path(self, nav_commands, mock_navigator, mock_tui):
        """Test ls with invalid path"""
        with patch.object(
            VFSPathParser, "parse", side_effect=ValueError("Invalid path")
        ):
            result = nav_commands.cmd_ls(["/invalid"])

            assert result.success is False
            assert "ls: Invalid path" in result.error

    @pytest.mark.unit
    def test_ls_nonexistent_directory(self, nav_commands, mock_navigator, mock_tui):
        """Test ls on directory that doesn't exist"""
        mock_parsed = Mock(spec=VFSPath)

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.side_effect = ValueError("Not a directory")

            result = nav_commands.cmd_ls(["/nonexistent"])

            assert result.success is False
            assert "ls: Not a directory" in result.error

    # cmd_pwd Tests

    @pytest.mark.unit
    def test_pwd_root(self, nav_commands, mock_tui):
        """Test pwd at root"""
        mock_tui.vfs_cwd = "/"

        result = nav_commands.cmd_pwd([])

        assert result.success is True
        assert result.output == "/\n"

    @pytest.mark.unit
    def test_pwd_chats(self, nav_commands, mock_tui):
        """Test pwd in /chats"""
        mock_tui.vfs_cwd = "/chats"

        result = nav_commands.cmd_pwd([])

        assert result.success is True
        assert result.output == "/chats\n"

    @pytest.mark.unit
    def test_pwd_deep_path(self, nav_commands, mock_tui):
        """Test pwd in deep directory"""
        mock_tui.vfs_cwd = "/chats/abc123/m1/m2"

        result = nav_commands.cmd_pwd([])

        assert result.success is True
        assert result.output == "/chats/abc123/m1/m2\n"

    @pytest.mark.unit
    def test_pwd_ignores_arguments(self, nav_commands, mock_tui):
        """Test pwd ignores any arguments"""
        mock_tui.vfs_cwd = "/starred"

        result = nav_commands.cmd_pwd(["arg1", "arg2"])

        assert result.success is True
        assert result.output == "/starred\n"

    @pytest.mark.unit
    def test_pwd_ignores_stdin(self, nav_commands, mock_tui):
        """Test pwd ignores stdin"""
        mock_tui.vfs_cwd = "/pinned"

        result = nav_commands.cmd_pwd([], stdin="some input")

        assert result.success is True
        assert result.output == "/pinned\n"


class TestCreateNavigationCommands:
    """Test create_navigation_commands factory function"""

    @pytest.mark.unit
    def test_create_navigation_commands(self):
        """Test factory creates command dictionary"""
        mock_navigator = Mock(spec=VFSNavigator)
        mock_tui = Mock()
        mock_tui.vfs_cwd = "/"
        mock_tui._update_environment = Mock()

        commands = create_navigation_commands(mock_navigator, mock_tui)

        assert "cd" in commands
        assert "ls" in commands
        assert "pwd" in commands
        assert callable(commands["cd"])
        assert callable(commands["ls"])
        assert callable(commands["pwd"])

    @pytest.mark.unit
    def test_created_commands_are_bound(self):
        """Test that created commands are bound to same instance"""
        mock_navigator = Mock(spec=VFSNavigator)
        mock_tui = Mock()
        mock_tui.vfs_cwd = "/"
        mock_tui._update_environment = Mock()

        commands = create_navigation_commands(mock_navigator, mock_tui)

        # All commands should be methods of the same instance
        assert commands["cd"].__self__ is commands["ls"].__self__
        assert commands["ls"].__self__ is commands["pwd"].__self__


# Integration-style Tests


class TestNavigationIntegration:
    """Integration tests for navigation command workflows"""

    @pytest.fixture
    def setup_integration(self):
        """Setup for integration tests"""
        mock_navigator = Mock(spec=VFSNavigator)
        mock_tui = Mock()
        mock_tui.vfs_cwd = "/"
        mock_tui._update_environment = Mock()
        nav = NavigationCommands(mock_navigator, mock_tui)
        return nav, mock_navigator, mock_tui

    @pytest.mark.unit
    def test_cd_then_pwd(self, setup_integration):
        """Test cd followed by pwd shows new location"""
        nav, mock_navigator, mock_tui = setup_integration

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []
            mock_navigator.resolve_prefix.return_value = None

            # Change directory
            nav.cmd_cd(["/chats"])

            # Check current directory
            result = nav.cmd_pwd([])

            assert result.output == "/chats\n"

    @pytest.mark.unit
    def test_cd_then_ls(self, setup_integration):
        """Test cd followed by ls lists new location"""
        nav, mock_navigator, mock_tui = setup_integration

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        entries = [
            VFSEntry(name="abc123", is_directory=True),
        ]

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []
            mock_navigator.resolve_prefix.return_value = None

            # Change directory
            nav.cmd_cd(["/chats"])

            # List new directory
            mock_navigator.list_directory.return_value = entries
            result = nav.cmd_ls([])

            assert "abc123/" in result.output

    @pytest.mark.unit
    def test_relative_navigation_workflow(self, setup_integration):
        """Test navigating with relative paths"""
        nav, mock_navigator, mock_tui = setup_integration

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.is_directory = True

        with patch.object(VFSPathParser, "parse", return_value=mock_parsed):
            mock_navigator.list_directory.return_value = []
            mock_navigator.resolve_prefix.return_value = None

            # Start at root, go to chats
            nav.cmd_cd(["/chats"])
            assert mock_tui.vfs_cwd == "/chats"

            # Go to conversation (relative)
            nav.cmd_cd(["abc123"])
            assert mock_tui.vfs_cwd == "/chats/abc123"

            # Go up one level
            nav.cmd_cd([".."])
            assert mock_tui.vfs_cwd == "/chats"

            # Go back to root
            nav.cmd_cd(["/"])
            assert mock_tui.vfs_cwd == "/"
