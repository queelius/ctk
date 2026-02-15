"""
Tests for ctk.core.input_validation module.

Tests the validation functions that sanitize CLI and API inputs:
- validate_conversation_id
- validate_file_path
- validate_path_selection
- validate_export_format
- validate_string
- validate_boolean
- validate_integer
"""

from pathlib import Path

import pytest

from ctk.core.input_validation import (
    ValidationError,
    validate_boolean,
    validate_conversation_id,
    validate_export_format,
    validate_file_path,
    validate_integer,
    validate_path_selection,
    validate_string,
)


# ==================== ValidationError ====================


class TestValidationError:
    """ValidationError should be a distinct exception type."""

    @pytest.mark.unit
    def test_is_exception(self):
        """ValidationError should be catchable as an Exception."""
        with pytest.raises(ValidationError):
            raise ValidationError("test error")

    @pytest.mark.unit
    def test_message_preserved(self):
        """Error message should be accessible from the exception."""
        with pytest.raises(ValidationError, match="specific message"):
            raise ValidationError("specific message")


# ==================== validate_conversation_id ====================


class TestValidateConversationId:
    """Tests for conversation ID validation."""

    @pytest.mark.unit
    def test_none_returns_none(self):
        assert validate_conversation_id(None) is None

    @pytest.mark.unit
    def test_valid_uuid_format(self):
        assert validate_conversation_id("abc-123-def-456") == "abc-123-def-456"

    @pytest.mark.unit
    def test_valid_hex_id(self):
        assert validate_conversation_id("a1b2c3d4") == "a1b2c3d4"

    @pytest.mark.unit
    def test_valid_id_with_underscores(self):
        assert validate_conversation_id("conv_001_abc") == "conv_001_abc"

    @pytest.mark.unit
    def test_valid_alphanumeric(self):
        assert validate_conversation_id("abc123XYZ") == "abc123XYZ"

    @pytest.mark.unit
    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_conversation_id("")

    @pytest.mark.unit
    def test_non_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_conversation_id(12345)

    @pytest.mark.unit
    def test_too_long_rejected(self):
        with pytest.raises(ValidationError):
            validate_conversation_id("a" * 201)

    @pytest.mark.unit
    def test_exactly_200_chars_accepted(self):
        id_200 = "a" * 200
        assert validate_conversation_id(id_200) == id_200

    @pytest.mark.unit
    def test_special_characters_rejected(self):
        bad_ids = [
            "abc; DROP TABLE",
            "conv/../../etc",
            "id with spaces",
            "id@domain.com",
            "id<script>",
        ]
        for bad_id in bad_ids:
            with pytest.raises(ValidationError):
                validate_conversation_id(bad_id)

    @pytest.mark.unit
    def test_sql_injection_rejected(self):
        with pytest.raises(ValidationError):
            validate_conversation_id("'; DROP TABLE conversations; --")

    @pytest.mark.unit
    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError):
            validate_conversation_id("../../etc/passwd")

    @pytest.mark.unit
    def test_allow_partial_true_accepts_short_hex(self):
        """With allow_partial=True (default), short hex IDs are fine."""
        assert validate_conversation_id("a1b2c3d4", allow_partial=True) == "a1b2c3d4"

    @pytest.mark.unit
    def test_allow_partial_false_rejects_short_hex(self):
        """With allow_partial=False, only full UUIDs should be accepted."""
        with pytest.raises(ValidationError, match="Full UUID required"):
            validate_conversation_id("a1b2c3d4", allow_partial=False)

    @pytest.mark.unit
    def test_allow_partial_false_accepts_full_uuid(self):
        """Full UUID should pass with allow_partial=False."""
        full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert validate_conversation_id(full_uuid, allow_partial=False) == full_uuid


# ==================== validate_file_path ====================


class TestValidateFilePath:
    """Tests for file path validation."""

    @pytest.mark.unit
    def test_valid_absolute_path(self, tmp_path):
        result = validate_file_path(str(tmp_path))
        assert isinstance(result, Path)

    @pytest.mark.unit
    def test_valid_relative_path(self):
        result = validate_file_path("some/relative/path")
        assert result.is_absolute()

    @pytest.mark.unit
    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_path("")

    @pytest.mark.unit
    def test_non_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_path(12345)

    @pytest.mark.unit
    def test_must_exist_when_missing(self, tmp_path):
        nonexistent = str(tmp_path / "does_not_exist.txt")
        with pytest.raises(ValidationError):
            validate_file_path(nonexistent, must_exist=True)

    @pytest.mark.unit
    def test_must_exist_when_present(self, tmp_path):
        existing = tmp_path / "exists.txt"
        existing.write_text("content")
        result = validate_file_path(str(existing), must_exist=True)
        assert result == existing

    @pytest.mark.unit
    def test_directory_rejected_when_not_allowed(self, tmp_path):
        with pytest.raises(ValidationError):
            validate_file_path(str(tmp_path), allow_dir=False)

    @pytest.mark.unit
    def test_file_rejected_when_not_allowed(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        with pytest.raises(ValidationError):
            validate_file_path(str(test_file), allow_file=False)

    @pytest.mark.unit
    def test_dot_dot_resolved(self, tmp_path):
        path_with_dots = str(tmp_path / "subdir" / ".." / "file.txt")
        result = validate_file_path(path_with_dots)
        assert ".." not in str(result)

    @pytest.mark.unit
    def test_nonexistent_path_accepted_when_not_required(self):
        result = validate_file_path("/tmp/some_nonexistent_file_xyz.txt", must_exist=False)
        assert isinstance(result, Path)

    @pytest.mark.unit
    def test_allow_relative_false_rejects_relative(self):
        """Relative paths should be rejected when allow_relative=False."""
        with pytest.raises(ValidationError, match="Absolute path required"):
            validate_file_path("relative/path.txt", allow_relative=False)

    @pytest.mark.unit
    def test_allow_relative_false_accepts_absolute(self, tmp_path):
        """Absolute paths should pass when allow_relative=False."""
        result = validate_file_path(str(tmp_path), allow_relative=False)
        assert isinstance(result, Path)

    @pytest.mark.unit
    def test_file_and_dir_both_allowed_by_default(self, tmp_path):
        """Both files and directories should be allowed by default."""
        # Test directory
        result = validate_file_path(str(tmp_path))
        assert isinstance(result, Path)

        # Test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        result = validate_file_path(str(test_file))
        assert isinstance(result, Path)


# ==================== validate_path_selection ====================


class TestValidatePathSelection:
    """Tests for path selection parameter validation."""

    @pytest.mark.unit
    def test_none_returns_none(self):
        assert validate_path_selection(None) is None

    @pytest.mark.unit
    def test_valid_longest(self):
        assert validate_path_selection("longest") == "longest"

    @pytest.mark.unit
    def test_valid_first(self):
        assert validate_path_selection("first") == "first"

    @pytest.mark.unit
    def test_valid_last(self):
        assert validate_path_selection("last") == "last"

    @pytest.mark.unit
    def test_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            validate_path_selection("shortest")

    @pytest.mark.unit
    def test_case_sensitive(self):
        with pytest.raises(ValidationError):
            validate_path_selection("Longest")

    @pytest.mark.unit
    def test_non_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_path_selection(1)

    @pytest.mark.unit
    def test_error_message_lists_valid_options(self):
        with pytest.raises(ValidationError, match="first"):
            validate_path_selection("invalid")


# ==================== validate_export_format ====================


class TestValidateExportFormat:
    """Tests for export format validation."""

    @pytest.mark.unit
    def test_none_returns_none(self):
        assert validate_export_format(None) is None

    @pytest.mark.unit
    def test_valid_formats(self):
        valid_formats = ["json", "jsonl", "markdown", "md", "html5", "hugo", "echo"]
        for fmt in valid_formats:
            assert validate_export_format(fmt) == fmt

    @pytest.mark.unit
    def test_format_with_hyphens(self):
        assert validate_export_format("my-format") == "my-format"

    @pytest.mark.unit
    def test_format_with_underscores(self):
        assert validate_export_format("my_format") == "my_format"

    @pytest.mark.unit
    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_export_format("")

    @pytest.mark.unit
    def test_too_long_rejected(self):
        with pytest.raises(ValidationError):
            validate_export_format("a" * 51)

    @pytest.mark.unit
    def test_special_characters_rejected(self):
        bad_formats = ["json;hack", "format/path", "fmt<script>", "fmt with space"]
        for bad_fmt in bad_formats:
            with pytest.raises(ValidationError):
                validate_export_format(bad_fmt)

    @pytest.mark.unit
    def test_non_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_export_format(42)


# ==================== validate_string ====================


class TestValidateString:
    """Tests for general string validation."""

    @pytest.mark.unit
    def test_none_returns_none(self):
        assert validate_string(None) is None

    @pytest.mark.unit
    def test_valid_string_passthrough(self):
        assert validate_string("hello world") == "hello world"

    @pytest.mark.unit
    def test_empty_string_allowed_by_default(self):
        assert validate_string("") == ""

    @pytest.mark.unit
    def test_empty_string_rejected_when_not_allowed(self):
        with pytest.raises(ValidationError):
            validate_string("", allow_empty=False)

    @pytest.mark.unit
    def test_max_length_enforced(self):
        with pytest.raises(ValidationError):
            validate_string("a" * 101, max_length=100)

    @pytest.mark.unit
    def test_exactly_at_max_length_accepted(self):
        s = "a" * 100
        assert validate_string(s, max_length=100) == s

    @pytest.mark.unit
    def test_non_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_string(42)

    @pytest.mark.unit
    def test_custom_name_in_error(self):
        with pytest.raises(ValidationError, match="title"):
            validate_string(42, name="title")

    @pytest.mark.unit
    def test_default_max_length_is_10000(self):
        assert validate_string("x" * 10000) == "x" * 10000
        with pytest.raises(ValidationError):
            validate_string("x" * 10001)


# ==================== validate_boolean ====================


class TestValidateBoolean:
    """Tests for boolean validation and coercion."""

    @pytest.mark.unit
    def test_true_bool(self):
        assert validate_boolean(True) is True

    @pytest.mark.unit
    def test_false_bool(self):
        assert validate_boolean(False) is False

    @pytest.mark.unit
    def test_string_true_variants(self):
        for val in ("true", "True", "TRUE", "1", "yes", "Yes", "YES", "on", "ON"):
            assert validate_boolean(val) is True, f"'{val}' should be True"

    @pytest.mark.unit
    def test_string_false_variants(self):
        for val in ("false", "False", "FALSE", "0", "no", "No", "NO", "off", "OFF"):
            assert validate_boolean(val) is False, f"'{val}' should be False"

    @pytest.mark.unit
    def test_int_zero_is_false(self):
        assert validate_boolean(0) is False

    @pytest.mark.unit
    def test_int_one_is_true(self):
        assert validate_boolean(1) is True

    @pytest.mark.unit
    def test_int_two_rejected(self):
        with pytest.raises(ValidationError):
            validate_boolean(2)

    @pytest.mark.unit
    def test_negative_int_rejected(self):
        with pytest.raises(ValidationError):
            validate_boolean(-1)

    @pytest.mark.unit
    def test_invalid_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_boolean("maybe")

    @pytest.mark.unit
    def test_none_rejected(self):
        with pytest.raises(ValidationError):
            validate_boolean(None)

    @pytest.mark.unit
    def test_list_rejected(self):
        with pytest.raises(ValidationError):
            validate_boolean([True])

    @pytest.mark.unit
    def test_float_rejected(self):
        with pytest.raises(ValidationError):
            validate_boolean(1.0)

    @pytest.mark.unit
    def test_custom_name_in_error(self):
        with pytest.raises(ValidationError, match="verbose"):
            validate_boolean("maybe", name="verbose")


# ==================== validate_integer ====================


class TestValidateInteger:
    """Tests for integer validation and coercion."""

    @pytest.mark.unit
    def test_valid_int_in_range(self):
        assert validate_integer(5) == 5

    @pytest.mark.unit
    def test_min_boundary(self):
        assert validate_integer(0, min_val=0) == 0

    @pytest.mark.unit
    def test_max_boundary(self):
        assert validate_integer(100, max_val=100) == 100

    @pytest.mark.unit
    def test_below_min_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer(-1, min_val=0)

    @pytest.mark.unit
    def test_above_max_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer(101, max_val=100)

    @pytest.mark.unit
    def test_string_coercion(self):
        assert validate_integer("42") == 42

    @pytest.mark.unit
    def test_invalid_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer("not_a_number")

    @pytest.mark.unit
    def test_float_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer("3.14")

    @pytest.mark.unit
    def test_bool_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer(True)

    @pytest.mark.unit
    def test_bool_false_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer(False)

    @pytest.mark.unit
    def test_none_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer(None)

    @pytest.mark.unit
    def test_float_type_rejected(self):
        with pytest.raises(ValidationError):
            validate_integer(3.14)

    @pytest.mark.unit
    def test_custom_name_in_error(self):
        with pytest.raises(ValidationError, match="limit"):
            validate_integer("abc", name="limit")

    @pytest.mark.unit
    def test_negative_string_coercion(self):
        assert validate_integer("-5", min_val=-10, max_val=10) == -5

    @pytest.mark.unit
    def test_default_range_is_0_to_10000(self):
        assert validate_integer(0) == 0
        assert validate_integer(10000) == 10000
        with pytest.raises(ValidationError):
            validate_integer(-1)
        with pytest.raises(ValidationError):
            validate_integer(10001)
