"""Tests for ctk.core.constants module."""

import pytest

from ctk.core import constants


class TestTimeoutConstants:
    """Verify timeout constants exist and have sensible values."""

    def test_default_timeout(self):
        assert constants.DEFAULT_TIMEOUT == 120

    def test_health_check_timeout(self):
        assert constants.HEALTH_CHECK_TIMEOUT == 5

    def test_model_list_timeout(self):
        assert constants.MODEL_LIST_TIMEOUT == 30

    def test_short_timeout(self):
        assert constants.SHORT_TIMEOUT == 2

    def test_embedding_timeout(self):
        assert constants.EMBEDDING_TIMEOUT == 60

    def test_migration_lock_timeout(self):
        assert constants.MIGRATION_LOCK_TIMEOUT == 30.0


class TestLimitConstants:
    """Verify limit constants exist and have sensible values."""

    def test_default_search_limit(self):
        assert constants.DEFAULT_SEARCH_LIMIT == 1000

    def test_default_timeline_limit(self):
        assert constants.DEFAULT_TIMELINE_LIMIT == 30

    def test_max_query_length(self):
        assert constants.MAX_QUERY_LENGTH == 10000

    def test_max_title_length(self):
        assert constants.MAX_TITLE_LENGTH == 1000

    def test_max_id_length(self):
        assert constants.MAX_ID_LENGTH == 200

    def test_max_result_limit(self):
        assert constants.MAX_RESULT_LIMIT == 10000

    def test_search_buffer(self):
        assert constants.SEARCH_BUFFER == 100

    def test_title_match_boost(self):
        assert constants.TITLE_MATCH_BOOST == 10

    def test_ambiguity_check_limit(self):
        assert constants.AMBIGUITY_CHECK_LIMIT == 2


class TestDisplayConstants:
    """Verify display constants."""

    def test_title_truncate_width(self):
        assert constants.TITLE_TRUNCATE_WIDTH == 60

    def test_title_truncate_width_short(self):
        assert constants.TITLE_TRUNCATE_WIDTH_SHORT == 50


class TestEstimationConstants:
    """Verify estimation constants."""

    def test_chars_per_token(self):
        assert constants.CHARS_PER_TOKEN == 4
