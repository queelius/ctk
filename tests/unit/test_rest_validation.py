"""Unit tests for ctk.interfaces.rest._validation.

These pin down the bounds we enforce on client-supplied input, plus the
filename whitelist that the upload endpoint relies on.
"""

from __future__ import annotations

import pytest

from ctk.interfaces.rest._validation import (MAX_LIMIT, MAX_YAML_BYTES,
                                             check_yaml_size, clamp_limit,
                                             clamp_offset,
                                             safe_upload_filename,
                                             validate_export_format)


pytestmark = pytest.mark.unit


class TestClampLimit:
    def test_none_returns_default(self):
        assert clamp_limit(None) == 100

    def test_explicit_default(self):
        assert clamp_limit(None, default=42) == 42

    def test_within_bounds(self):
        assert clamp_limit(50) == 50

    def test_negative_clamped_up(self):
        assert clamp_limit(-10) == 1

    def test_zero_clamped_up(self):
        assert clamp_limit(0) == 1

    def test_too_large_clamped_down(self):
        assert clamp_limit(MAX_LIMIT + 1) == MAX_LIMIT
        assert clamp_limit(1_000_000_000) == MAX_LIMIT

    def test_non_int_falls_back_to_default(self):
        assert clamp_limit("banana") == 100  # type: ignore[arg-type]


class TestClampOffset:
    def test_none_is_zero(self):
        assert clamp_offset(None) == 0

    def test_negative_is_zero(self):
        assert clamp_offset(-42) == 0

    def test_huge_is_capped(self):
        assert clamp_offset(10**12) <= 10_000_000


class TestValidateExportFormat:
    @pytest.mark.parametrize("fmt", ["json", "jsonl", "markdown", "md", "csv", "html"])
    def test_allowed_formats_pass(self, fmt):
        assert validate_export_format(fmt) == fmt

    def test_none_defaults_to_jsonl(self):
        assert validate_export_format(None) == "jsonl"

    def test_case_insensitive(self):
        assert validate_export_format("JSON") == "json"

    @pytest.mark.parametrize("bad", [
        "exe",                 # arbitrary
        "md\nSet-Cookie: x",   # header injection attempt
        "../etc/passwd",
    ])
    def test_bad_formats_raise(self, bad):
        with pytest.raises(ValueError):
            validate_export_format(bad)

    def test_empty_string_defaults_to_jsonl(self):
        # Treated same as None — defensively fall back rather than 400.
        assert validate_export_format("") == "jsonl"


class TestSafeUploadFilename:
    @pytest.mark.parametrize("name", [
        "conversations.json",
        "export-2026.jsonl",
        "notes.md",
        "data_v2.txt",
    ])
    def test_whitelisted_extensions(self, name):
        basename, suffix = safe_upload_filename(name)
        assert basename == name
        assert suffix.startswith(".")

    def test_strips_path_components(self):
        with pytest.raises(ValueError):
            # After basename strip this would still be fine, but we also
            # reject characters outside our safe class, so `..` would
            # be rejected here for containing nothing after basename.
            safe_upload_filename("../../etc/passwd")

    def test_rejects_header_injection(self):
        with pytest.raises(ValueError):
            safe_upload_filename('file\nSet-Cookie: x.json')

    def test_rejects_missing_name(self):
        with pytest.raises(ValueError):
            safe_upload_filename("")
        with pytest.raises(ValueError):
            safe_upload_filename(None)

    def test_rejects_bad_extension(self):
        with pytest.raises(ValueError):
            safe_upload_filename("evil.sh")
        with pytest.raises(ValueError):
            safe_upload_filename("noext")


class TestCheckYamlSize:
    def test_small_body_ok(self):
        check_yaml_size("name: test\n")  # no raise

    def test_oversized_rejected(self):
        body = "x" * (MAX_YAML_BYTES + 1)
        with pytest.raises(ValueError):
            check_yaml_size(body)
