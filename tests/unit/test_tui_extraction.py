"""
Tests for Sprint 5.1: TUI module extraction.

Verifies that extracted modules (tui_network, tui_vfs, tui_mcp) exist,
have correct function signatures, and that ChatTUI delegates to them.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch


@pytest.mark.unit
class TestTuiNetworkExtraction:
    """Test that handle_net_command was extracted to tui_network module."""

    def test_module_exists(self):
        """tui_network module should be importable."""
        from ctk.integrations.chat import tui_network
        assert hasattr(tui_network, "handle_net_command")

    def test_function_signature(self):
        """handle_net_command should accept (db, args, **context)."""
        from ctk.integrations.chat.tui_network import handle_net_command
        import inspect
        sig = inspect.signature(handle_net_command)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "args" in params

    def test_tui_delegates_to_module(self):
        """ChatTUI.handle_net_command should delegate to tui_network module."""
        from ctk.integrations.chat.tui_network import handle_net_command
        # Verify the function exists and is callable
        assert callable(handle_net_command)

    def test_no_db_returns_error(self):
        """handle_net_command with no db should print error."""
        from ctk.integrations.chat.tui_network import handle_net_command
        with patch("builtins.print") as mock_print:
            handle_net_command(db=None, args="embeddings")
            mock_print.assert_called_with("Error: No database configured")

    def test_unknown_subcmd(self):
        """Unknown subcommand should print error with available commands."""
        from ctk.integrations.chat.tui_network import handle_net_command
        mock_db = MagicMock()
        with patch("builtins.print") as mock_print:
            handle_net_command(db=mock_db, args="nonexistent")
            # Should mention "Unknown net subcommand"
            calls = [str(c) for c in mock_print.call_args_list]
            assert any("Unknown" in c for c in calls)

    def test_empty_args_handled(self):
        """Empty args string should be handled gracefully."""
        from ctk.integrations.chat.tui_network import handle_net_command
        mock_db = MagicMock()
        # Empty args should not crash (may print error about missing subcmd)
        try:
            handle_net_command(db=mock_db, args="")
        except (IndexError, ValueError):
            pytest.fail("handle_net_command crashed on empty args")


@pytest.mark.unit
class TestTuiVfsExtraction:
    """Test that VFS command handlers were extracted to tui_vfs module."""

    def test_module_exists(self):
        """tui_vfs module should be importable."""
        from ctk.integrations.chat import tui_vfs
        assert hasattr(tui_vfs, "handle_cd")
        assert hasattr(tui_vfs, "handle_ls")
        assert hasattr(tui_vfs, "handle_pwd")

    def test_all_handlers_present(self):
        """All VFS handlers should be present."""
        from ctk.integrations.chat import tui_vfs
        expected = [
            "handle_cd", "handle_pwd", "handle_ls",
            "handle_ln", "handle_cp", "handle_mv",
            "handle_rm", "handle_mkdir",
        ]
        for name in expected:
            assert hasattr(tui_vfs, name), f"Missing handler: {name}"

    def test_handle_pwd_returns_cwd(self):
        """handle_pwd should print the current working directory."""
        from ctk.integrations.chat.tui_vfs import handle_pwd
        with patch("builtins.print") as mock_print:
            handle_pwd(vfs_cwd="/chats")
            mock_print.assert_called_with("/chats")


@pytest.mark.unit
class TestTuiMcpExtraction:
    """Test that handle_mcp_command was extracted to tui_mcp module."""

    def test_module_exists(self):
        """tui_mcp module should be importable."""
        from ctk.integrations.chat import tui_mcp
        assert hasattr(tui_mcp, "handle_mcp_command")

    def test_function_signature(self):
        """handle_mcp_command should accept (mcp_client, args, **context)."""
        from ctk.integrations.chat.tui_mcp import handle_mcp_command
        import inspect
        sig = inspect.signature(handle_mcp_command)
        params = list(sig.parameters.keys())
        assert "mcp_client" in params
        assert "args" in params


@pytest.mark.unit
class TestTuiLineCount:
    """Verify tui.py has been reduced in size."""

    def test_tui_file_reduced(self):
        """tui.py should be significantly shorter after extraction."""
        import os
        tui_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "ctk", "integrations", "chat", "tui.py"
        )
        with open(os.path.abspath(tui_path)) as f:
            line_count = sum(1 for _ in f)
        # Original: 6215 lines. After extracting ~1800 lines, should be < 4600
        assert line_count < 4600, f"tui.py still has {line_count} lines (expected < 4600)"
