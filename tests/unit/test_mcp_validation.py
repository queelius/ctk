"""Tests for MCP validation utilities."""

import pytest

from ctk.interfaces.mcp.validation import (
    ValidationError,
    validate_boolean,
    validate_conversation_id,
    validate_integer,
    validate_string,
)


class TestValidateString:
    def test_returns_none_when_none_and_not_required(self):
        assert validate_string(None, "x", 100) is None

    def test_raises_when_none_and_required(self):
        with pytest.raises(ValidationError, match="required"):
            validate_string(None, "x", 100, required=True)

    def test_returns_string_when_valid(self):
        assert validate_string("hello", "x", 100) == "hello"

    def test_raises_when_exceeds_max_length(self):
        with pytest.raises(ValidationError, match="maximum length"):
            validate_string("toolong", "x", 3)

    def test_raises_when_not_string(self):
        with pytest.raises(ValidationError, match="must be a string"):
            validate_string(123, "x", 100)


class TestValidateBoolean:
    def test_returns_none_when_none(self):
        assert validate_boolean(None, "x") is None

    def test_returns_bool_directly(self):
        assert validate_boolean(True, "x") is True
        assert validate_boolean(False, "x") is False

    def test_parses_string_true(self):
        for val in ("true", "1", "yes", "True", "YES"):
            assert validate_boolean(val, "x") is True

    def test_parses_string_false(self):
        for val in ("false", "0", "no", "False", "NO"):
            assert validate_boolean(val, "x") is False

    def test_raises_on_invalid(self):
        with pytest.raises(ValidationError, match="must be a boolean"):
            validate_boolean("maybe", "x")


class TestValidateInteger:
    def test_returns_none_when_none(self):
        assert validate_integer(None, "x") is None

    def test_returns_int_directly(self):
        assert validate_integer(5, "x") == 5

    def test_parses_string_int(self):
        assert validate_integer("42", "x") == 42

    def test_raises_below_min(self):
        with pytest.raises(ValidationError, match=">="):
            validate_integer(-1, "x", min_val=0)

    def test_raises_above_max(self):
        with pytest.raises(ValidationError, match="<="):
            validate_integer(999, "x", max_val=100)

    def test_raises_on_bool(self):
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_integer(True, "x")


class TestValidateConversationId:
    def test_valid_id(self):
        assert validate_conversation_id("abc-123_def") == "abc-123_def"

    def test_raises_when_none(self):
        with pytest.raises(ValidationError, match="required"):
            validate_conversation_id(None)

    def test_raises_on_invalid_chars(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_conversation_id("id with spaces")

    def test_raises_on_injection(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_conversation_id("id'; DROP TABLE--")
