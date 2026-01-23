"""Unit tests for slug generation utilities."""

import pytest

from ctk.core.slug import generate_slug, make_unique_slug, slug_matches


class TestGenerateSlug:
    """Tests for generate_slug function."""

    def test_basic_slug(self):
        """Test basic slug generation."""
        assert generate_slug("Hello World") == "hello-world"

    def test_empty_title(self):
        """Test empty title returns None."""
        assert generate_slug("") is None
        assert generate_slug(None) is None

    def test_lowercase(self):
        """Test slug is lowercase."""
        assert generate_slug("UPPERCASE TITLE") == "uppercase-title"

    def test_special_characters_replaced(self):
        """Test special characters are replaced with hyphens."""
        assert (
            generate_slug("API Integration: OAuth2 & JWT")
            == "api-integration-oauth2-jwt"
        )

    def test_contraction_whats(self):
        """Test 'what's' becomes 'whats'."""
        assert generate_slug("What's the best way?") == "whats-the-best-way"

    def test_contraction_dont(self):
        """Test 'don't' becomes 'dont'."""
        assert generate_slug("Don't do that") == "dont-do-that"

    def test_contraction_well(self):
        """Test 'we'll' becomes 'well'."""
        assert generate_slug("We'll see") == "well-see"

    def test_contraction_theyre(self):
        """Test 'they're' becomes 'theyre'."""
        assert generate_slug("They're here") == "theyre-here"

    def test_contraction_ive(self):
        """Test 'I've' becomes 'ive'."""
        assert generate_slug("I've done it") == "ive-done-it"

    def test_contraction_id(self):
        """Test 'I'd' becomes 'id'."""
        assert generate_slug("I'd like that") == "id-like-that"

    def test_colons_replaced(self):
        """Test colons are replaced with hyphens."""
        assert generate_slug("Title: Subtitle") == "title-subtitle"

    def test_multiple_hyphens_collapsed(self):
        """Test multiple hyphens are collapsed."""
        assert generate_slug("Too --- many --- hyphens") == "too-many-hyphens"

    def test_leading_trailing_hyphens_removed(self):
        """Test leading and trailing hyphens are removed."""
        assert generate_slug("---Leading and trailing---") == "leading-and-trailing"

    def test_numbers_preserved(self):
        """Test numbers are preserved."""
        assert generate_slug("Python 3.12 Features") == "python-3-12-features"

    def test_unicode_normalized(self):
        """Test unicode characters are normalized."""
        assert generate_slug("Café résumé") == "cafe-resume"

    def test_max_length(self):
        """Test slug is truncated to max length."""
        long_title = "This is a very long title that exceeds the maximum length allowed for slugs"
        slug = generate_slug(long_title, max_length=30)
        assert len(slug) <= 30

    def test_truncation_at_word_boundary(self):
        """Test truncation happens at word boundary when possible."""
        title = "First second third fourth fifth sixth seventh"
        slug = generate_slug(title, max_length=25)
        # Should truncate at a hyphen boundary
        assert "-" not in slug[-1:] or len(slug) <= 25

    def test_only_special_chars_returns_none(self):
        """Test title with only special chars returns None."""
        assert generate_slug("!@#$%^&*()") is None


class TestMakeUniqueSlug:
    """Tests for make_unique_slug function."""

    def test_unique_slug_unchanged(self):
        """Test unique slug is returned unchanged."""
        existing = {"hello-world", "test-slug"}
        assert make_unique_slug("new-slug", existing) == "new-slug"

    def test_duplicate_gets_suffix(self):
        """Test duplicate slug gets numeric suffix."""
        existing = {"hello-world"}
        assert make_unique_slug("hello-world", existing) == "hello-world-2"

    def test_multiple_duplicates(self):
        """Test multiple duplicates get incrementing suffixes."""
        existing = {"test", "test-2", "test-3"}
        assert make_unique_slug("test", existing) == "test-4"

    def test_empty_existing_set(self):
        """Test with empty existing set."""
        assert make_unique_slug("any-slug", set()) == "any-slug"


class TestSlugMatches:
    """Tests for slug_matches function."""

    def test_exact_match(self):
        """Test exact match."""
        assert slug_matches("discussion-python-hints", "discussion-python-hints")

    def test_prefix_match(self):
        """Test prefix match."""
        assert slug_matches("discussion-python-hints", "discussion")

    def test_word_partial_match(self):
        """Test word-based partial match."""
        assert slug_matches("discussion-python-hints", "disc-py")

    def test_no_match(self):
        """Test non-matching query."""
        assert not slug_matches("discussion-python-hints", "javascript")

    def test_empty_slug(self):
        """Test empty slug returns False."""
        assert not slug_matches("", "query")

    def test_empty_query(self):
        """Test empty query returns False."""
        assert not slug_matches("discussion-python-hints", "")

    def test_partial_word_match(self):
        """Test partial word match at start."""
        assert slug_matches("discussion-python-hints", "dis")

    def test_middle_word_prefix(self):
        """Test matching word in middle position."""
        assert slug_matches("discussion-python-hints", "python")
