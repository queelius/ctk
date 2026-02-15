"""
Tests for ctk.core.utils module.

Tests the shared utility functions:
- parse_timestamp: Handles Unix epoch, ISO 8601, datetime passthrough
- try_parse_json: Handles dict, JSON string, and invalid inputs
"""

from datetime import datetime, timezone

import pytest

from ctk.core.utils import parse_timestamp, try_parse_json


# ==================== parse_timestamp ====================


class TestParseTimestamp:
    """Tests for the parse_timestamp utility."""

    @pytest.mark.unit
    def test_none_returns_default(self):
        """None input should return the default value."""
        assert parse_timestamp(None) is None

    @pytest.mark.unit
    def test_none_with_custom_default(self):
        """None input should return the specified default."""
        default = datetime(2024, 1, 1)
        assert parse_timestamp(None, default=default) == default

    @pytest.mark.unit
    def test_datetime_passthrough(self):
        """datetime objects should be returned unchanged."""
        dt = datetime(2024, 6, 15, 12, 30, 0)
        assert parse_timestamp(dt) is dt

    # --- Unix timestamps ---

    @pytest.mark.unit
    def test_unix_timestamp_seconds(self):
        """Integer Unix timestamp (seconds) should be parsed."""
        # Use a timestamp and verify it round-trips correctly
        result = parse_timestamp(1704067200)
        assert isinstance(result, datetime)
        # The exact year depends on timezone, so just verify it's a valid datetime
        assert result.year in (2023, 2024)  # timezone-dependent

    @pytest.mark.unit
    def test_unix_timestamp_float(self):
        """Float Unix timestamp should be parsed."""
        result = parse_timestamp(1704067200.5)
        assert isinstance(result, datetime)

    @pytest.mark.unit
    def test_unix_timestamp_milliseconds(self):
        """Millisecond timestamps (>1e10) should be auto-divided by 1000."""
        # 1704067200000 ms = 1704067200 seconds
        result_ms = parse_timestamp(1704067200000)
        result_s = parse_timestamp(1704067200)
        assert result_ms is not None
        assert result_s is not None
        # Both should produce the same year/month/day
        assert result_ms.year == result_s.year
        assert result_ms.month == result_s.month
        assert result_ms.day == result_s.day

    @pytest.mark.unit
    def test_negative_unix_timestamp_returns_default(self):
        """Extremely negative timestamps should return default (platform-dependent)."""
        result = parse_timestamp(-99999999999999)
        assert result is None

    @pytest.mark.unit
    def test_overflow_unix_timestamp_returns_default(self):
        """Overflow timestamps should return default."""
        result = parse_timestamp(99999999999999999)
        assert result is None

    # --- ISO 8601 strings ---

    @pytest.mark.unit
    def test_iso_format_with_z(self):
        """ISO 8601 with Z timezone should be parsed."""
        result = parse_timestamp("2024-01-01T00:00:00Z")
        assert isinstance(result, datetime)
        assert result.year == 2024

    @pytest.mark.unit
    def test_iso_format_with_offset(self):
        """ISO 8601 with timezone offset should be parsed."""
        result = parse_timestamp("2024-06-15T12:30:00+05:00")
        assert isinstance(result, datetime)
        assert result.year == 2024

    @pytest.mark.unit
    def test_iso_format_no_timezone(self):
        """ISO 8601 without timezone should be parsed."""
        result = parse_timestamp("2024-06-15T12:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 6

    @pytest.mark.unit
    def test_iso_date_only(self):
        """ISO date-only string should be parsed."""
        result = parse_timestamp("2024-01-15")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    # --- Custom formats ---

    @pytest.mark.unit
    def test_custom_format_with_microseconds(self):
        """Custom format YYYY-MM-DD HH:MM:SS.ffffff should parse."""
        result = parse_timestamp("2024-06-15 12:30:45.123456")
        assert isinstance(result, datetime)
        assert result.year == 2024

    @pytest.mark.unit
    def test_custom_format_slash_ymd(self):
        """Custom format YYYY/MM/DD HH:MM:SS should parse."""
        result = parse_timestamp("2024/06/15 12:30:45")
        assert isinstance(result, datetime)
        assert result.year == 2024

    @pytest.mark.unit
    def test_custom_format_slash_mdy(self):
        """Custom format MM/DD/YYYY HH:MM:SS should parse."""
        result = parse_timestamp("06/15/2024 12:30:45")
        assert isinstance(result, datetime)
        assert result.month == 6
        assert result.day == 15

    # --- Invalid inputs ---

    @pytest.mark.unit
    def test_invalid_string_returns_default(self):
        """Unparseable strings should return default."""
        assert parse_timestamp("not-a-date") is None

    @pytest.mark.unit
    def test_empty_string_returns_default(self):
        """Empty string should return default."""
        assert parse_timestamp("") is None

    @pytest.mark.unit
    def test_unsupported_type_returns_default(self):
        """Unsupported types (list, dict) should return default."""
        assert parse_timestamp([1, 2, 3]) is None
        assert parse_timestamp({"ts": 123}) is None

    @pytest.mark.unit
    def test_invalid_string_with_custom_default(self):
        """Invalid string should return specified default."""
        default = datetime(2000, 1, 1)
        result = parse_timestamp("garbage", default=default)
        assert result == default


# ==================== try_parse_json ====================


class TestTryParseJson:
    """Tests for the try_parse_json utility."""

    @pytest.mark.unit
    def test_dict_passthrough(self):
        """Dict input should be returned as-is."""
        d = {"key": "value"}
        assert try_parse_json(d) is d

    @pytest.mark.unit
    def test_valid_json_string(self):
        """Valid JSON string should be parsed to dict."""
        result = try_parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    @pytest.mark.unit
    def test_json_array_string(self):
        """Valid JSON array string should be parsed."""
        result = try_parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    @pytest.mark.unit
    def test_invalid_json_returns_none(self):
        """Invalid JSON string should return None."""
        assert try_parse_json("not json at all") is None

    @pytest.mark.unit
    def test_empty_string_returns_none(self):
        """Empty string should return None (not valid JSON)."""
        assert try_parse_json("") is None

    @pytest.mark.unit
    def test_none_returns_none(self):
        """None input should return None."""
        assert try_parse_json(None) is None

    @pytest.mark.unit
    def test_int_returns_none(self):
        """Integer input should return None."""
        assert try_parse_json(42) is None

    @pytest.mark.unit
    def test_list_returns_none(self):
        """List input should return None (not dict, not str)."""
        assert try_parse_json([1, 2]) is None

    @pytest.mark.unit
    def test_nested_json(self):
        """Nested JSON should be parsed correctly."""
        result = try_parse_json('{"a": {"b": [1, 2]}}')
        assert result == {"a": {"b": [1, 2]}}

    @pytest.mark.unit
    def test_json_with_unicode(self):
        """JSON with unicode characters should parse."""
        result = try_parse_json('{"emoji": "\\u2764"}')
        assert result is not None
        assert "emoji" in result
