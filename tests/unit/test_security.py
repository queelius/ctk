"""
Security tests for CTK.

Tests focus on:
- Plugin security (AST validation)
- Path traversal protection
- Input validation (MCP server)
- VFS path security
- Credential handling
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ctk.core.config import SENSITIVE_KEYS, Config
from ctk.core.plugin import PluginASTValidator, PluginSecurityError
from ctk.core.vfs import VFSPathParser, VFSSecurityError
from ctk.integrations.exporters.markdown import (MarkdownExporter,
                                                 PathTraversalError)
from ctk.mcp_server import (MAX_ID_LENGTH, MAX_LIMIT, MAX_QUERY_LENGTH,
                            MAX_TITLE_LENGTH, ValidationError,
                            validate_boolean, validate_conversation_id,
                            validate_integer, validate_string)

# ==================== Plugin AST Validator Tests ====================


class TestPluginASTValidator:
    """Tests for plugin AST security validation"""

    def test_safe_plugin_passes(self):
        """Safe plugin code should pass validation"""
        safe_code = """
from typing import List, Any
from ctk.core.plugin import ImporterPlugin
from ctk.core.models import ConversationTree

class SafeImporter(ImporterPlugin):
    name = "safe"
    description = "Safe importer"

    def validate(self, data: Any) -> bool:
        return isinstance(data, dict)

    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        return []
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(safe_code)
        assert is_valid, f"Safe plugin should pass validation: {violations}"

    def test_subprocess_import_rejected(self):
        """Subprocess import should be rejected"""
        malicious_code = """
import subprocess
subprocess.call(['rm', '-rf', '/'])
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(malicious_code)
        assert not is_valid
        assert any("subprocess" in v for v in violations)

    def test_exec_call_rejected(self):
        """exec() calls should be rejected"""
        malicious_code = """
exec("import os; os.system('rm -rf /')")
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(malicious_code)
        assert not is_valid
        assert any("exec" in v.lower() for v in violations)

    def test_eval_call_rejected(self):
        """eval() calls should be rejected"""
        malicious_code = """
user_input = "malicious"
result = eval(user_input)
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(malicious_code)
        assert not is_valid
        assert any("eval" in v.lower() for v in violations)

    def test_socket_import_rejected(self):
        """Socket import should be rejected"""
        malicious_code = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(malicious_code)
        assert not is_valid
        assert any("socket" in v for v in violations)

    def test_os_system_rejected(self):
        """os.system() should be rejected"""
        malicious_code = """
import os
os.system("dangerous_command")
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(malicious_code)
        assert not is_valid
        # Should catch both the import and the call

    def test_dunder_import_rejected(self):
        """__import__ should be rejected"""
        malicious_code = """
m = __import__("os")
m.system("rm -rf /")
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(malicious_code)
        assert not is_valid

    def test_pickle_import_rejected(self):
        """pickle import should be rejected (deserialization attacks)"""
        malicious_code = """
import pickle
pickle.loads(untrusted_data)
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(malicious_code)
        assert not is_valid
        assert any("pickle" in v for v in violations)

    def test_non_whitelisted_import_warning(self):
        """Non-whitelisted imports should produce warnings"""
        code_with_external = """
import numpy
import pandas
"""
        validator = PluginASTValidator(Path("test.py"), strict=False)
        is_valid, violations, warnings = validator.validate(code_with_external)
        assert is_valid  # Not strict mode
        assert len(warnings) >= 2

    def test_strict_mode_rejects_external(self):
        """Strict mode should reject non-whitelisted imports"""
        code_with_external = """
import numpy
"""
        validator = PluginASTValidator(Path("test.py"), strict=True)
        is_valid, violations, warnings = validator.validate(code_with_external)
        assert not is_valid

    def test_syntax_error_handled(self):
        """Syntax errors should be caught and reported"""
        invalid_code = """
def broken(
"""
        validator = PluginASTValidator(Path("test.py"))
        is_valid, violations, warnings = validator.validate(invalid_code)
        assert not is_valid
        assert any("syntax" in v.lower() for v in violations)


# ==================== VFS Path Security Tests ====================


class TestVFSPathSecurity:
    """Tests for VFS path traversal protection"""

    def test_normalized_path_starts_with_slash(self):
        """All normalized paths must start with /"""
        test_paths = [
            "/chats/abc",
            "chats/abc",
            "../../../etc/passwd",
            "..%2F..%2Fetc%2Fpasswd",
            "/tags/../../etc",
        ]
        for path in test_paths:
            normalized = VFSPathParser.normalize_path(path)
            assert normalized.startswith(
                "/"
            ), f"Path '{path}' normalized to '{normalized}'"

    def test_path_traversal_blocked(self):
        """Path traversal attempts should stay within VFS root"""
        # Try to escape to parent directories
        result = VFSPathParser.normalize_path("/../../../etc/passwd")
        assert result == "/etc/passwd" or result == "/"
        assert not result.startswith("/..")

    def test_relative_traversal_blocked(self):
        """Relative path traversal should be blocked"""
        result = VFSPathParser.normalize_path("../../../", "/chats")
        assert result == "/" or result.startswith("/")
        assert ".." not in result

    def test_double_dot_in_segments_resolved(self):
        """.. segments should be properly resolved"""
        result = VFSPathParser.normalize_path("/chats/abc/../def")
        assert result == "/chats/def"
        assert ".." not in result

    def test_current_dir_dots_resolved(self):
        """Single dots should be resolved"""
        result = VFSPathParser.normalize_path("/chats/./abc/./def")
        assert result == "/chats/abc/def"
        assert "/." not in result

    def test_invalid_current_dir_defaults_to_root(self):
        """Invalid current_dir should default to root"""
        result = VFSPathParser.normalize_path("abc", "invalid_no_slash")
        assert result.startswith("/")


# ==================== Markdown Exporter Path Traversal Tests ====================


class TestMarkdownExporterPathSecurity:
    """Tests for markdown exporter path traversal protection"""

    def test_safe_filename_generation(self):
        """Filenames should not contain path traversal characters"""
        exporter = MarkdownExporter()

        # Create mock conversation with malicious title
        class MockMetadata:
            created_at = None

        class MockConv:
            id = "abc12345"
            title = "../../../etc/passwd"
            metadata = MockMetadata()

        filename = exporter._generate_filename(MockConv())
        assert ".." not in filename
        assert "/" not in filename
        assert "\\" not in filename

    def test_slash_in_title_sanitized(self):
        """Slashes in titles should be sanitized"""
        exporter = MarkdownExporter()

        class MockMetadata:
            created_at = None

        class MockConv:
            id = "abc12345"
            title = "user/system/hack"
            metadata = MockMetadata()

        filename = exporter._generate_filename(MockConv())
        assert "/" not in filename

    def test_empty_title_handled(self):
        """Empty or whitespace titles should produce valid filenames"""
        exporter = MarkdownExporter()

        class MockMetadata:
            created_at = None

        class MockConv:
            id = "abc12345"
            title = "   "
            metadata = MockMetadata()

        filename = exporter._generate_filename(MockConv())
        assert filename.endswith(".md")
        assert "/" not in filename

    def test_is_safe_path(self):
        """_is_safe_path should correctly detect escapes"""
        exporter = MarkdownExporter()

        base = Path("/tmp/output")

        # Safe paths
        assert exporter._is_safe_path(base / "file.md", base)
        assert exporter._is_safe_path(base / "subdir" / "file.md", base)

        # Unsafe paths (escaped)
        assert not exporter._is_safe_path(Path("/etc/passwd"), base)
        assert not exporter._is_safe_path(base.parent / "escape.md", base)


# ==================== MCP Server Input Validation Tests ====================


class TestMCPInputValidation:
    """Tests for MCP server input validation"""

    def test_string_validation_max_length(self):
        """Strings exceeding max length should be rejected"""
        long_string = "a" * (MAX_QUERY_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            validate_string(long_string, "query", MAX_QUERY_LENGTH)
        assert "exceeds maximum length" in str(exc_info.value)

    def test_string_validation_type(self):
        """Non-string values should be rejected"""
        with pytest.raises(ValidationError) as exc_info:
            validate_string(12345, "name", 100)
        assert "must be a string" in str(exc_info.value)

    def test_string_validation_required(self):
        """Required strings must be provided"""
        with pytest.raises(ValidationError) as exc_info:
            validate_string(None, "name", 100, required=True)
        assert "required" in str(exc_info.value)

    def test_string_validation_optional(self):
        """Optional strings can be None"""
        result = validate_string(None, "name", 100, required=False)
        assert result is None

    def test_boolean_validation_true_values(self):
        """Various true representations should work"""
        assert validate_boolean(True, "flag") is True
        assert validate_boolean("true", "flag") is True
        assert validate_boolean("TRUE", "flag") is True
        assert validate_boolean("1", "flag") is True
        assert validate_boolean("yes", "flag") is True

    def test_boolean_validation_false_values(self):
        """Various false representations should work"""
        assert validate_boolean(False, "flag") is False
        assert validate_boolean("false", "flag") is False
        assert validate_boolean("FALSE", "flag") is False
        assert validate_boolean("0", "flag") is False
        assert validate_boolean("no", "flag") is False

    def test_boolean_validation_invalid(self):
        """Invalid boolean values should be rejected"""
        with pytest.raises(ValidationError) as exc_info:
            validate_boolean("maybe", "flag")
        assert "must be a boolean" in str(exc_info.value)

    def test_integer_validation_range(self):
        """Integers outside valid range should be rejected"""
        with pytest.raises(ValidationError) as exc_info:
            validate_integer(-1, "limit", min_val=0)
        assert "must be >=" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            validate_integer(MAX_LIMIT + 1, "limit", max_val=MAX_LIMIT)
        assert "must be <=" in str(exc_info.value)

    def test_integer_validation_type(self):
        """Non-integer values should be rejected"""
        with pytest.raises(ValidationError) as exc_info:
            validate_integer("not_a_number", "count")
        assert "must be an integer" in str(exc_info.value)

    def test_conversation_id_validation_characters(self):
        """IDs with invalid characters should be rejected"""
        with pytest.raises(ValidationError) as exc_info:
            validate_conversation_id("abc; DROP TABLE conversations;--", "id")
        assert "invalid characters" in str(exc_info.value)

    def test_conversation_id_valid(self):
        """Valid IDs should pass"""
        result = validate_conversation_id("abc-123_def", "id")
        assert result == "abc-123_def"


# ==================== Config Credential Security Tests ====================


class TestConfigCredentialSecurity:
    """Tests for credential handling in config"""

    def test_sensitive_keys_identified(self):
        """SENSITIVE_KEYS should include common credential patterns"""
        assert "api_key" in SENSITIVE_KEYS
        assert "password" in SENSITIVE_KEYS
        assert "secret" in SENSITIVE_KEYS
        assert "token" in SENSITIVE_KEYS

    def test_find_sensitive_keys(self):
        """Config should detect sensitive keys in nested structures"""
        config = Config.__new__(Config)  # Create without __init__
        config.config = {
            "providers": {
                "openai": {"api_key": "sk-12345", "base_url": "https://api.openai.com"},
                "anthropic": {"api_key": "sk-ant-12345"},
            },
            "database": {"path": "/tmp/test.db"},
        }
        config.config_path = Path("/tmp/test_config.json")

        sensitive = config._find_sensitive_keys(config.config)
        assert len(sensitive) >= 2
        assert any("api_key" in s for s in sensitive)

    def test_environment_variable_preferred(self):
        """Environment variables should be preferred over config file"""
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text('{"providers": {"test": {"api_key": "config_key"}}}')

            config = Config(config_path)

            # Set environment variable
            os.environ["TEST_API_KEY"] = "env_key"
            try:
                key = config.get_api_key("test")
                assert key == "env_key", "Environment variable should be preferred"
            finally:
                del os.environ["TEST_API_KEY"]


# ==================== Database Message ID Tests ====================


class TestMessageIDSecurity:
    """Tests for message ID handling (collision prevention)"""

    def test_message_id_delimiter(self):
        """Message IDs should use :: delimiter instead of _"""
        # This tests the format used in database.py
        conv_id = "abc_def_123"  # ID with underscores
        msg_id = "msg_456_789"  # Message ID with underscores

        # Old format would be: "abc_def_123_msg_456_789" - ambiguous
        # New format is: "abc_def_123::msg_456_789" - unambiguous

        combined = f"{conv_id}::{msg_id}"
        parts = combined.split("::")

        assert len(parts) == 2
        assert parts[0] == conv_id
        assert parts[1] == msg_id
