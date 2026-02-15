"""
Tests for ctk.integrations.exporters.hugo module.

Tests the Hugo page bundle exporter including:
- _get_target_dir: Organization strategies (none, tags, source, date)
- _generate_slug: URL-safe slug generation
- _format_role: Role display formatting
- _generate_frontmatter: YAML frontmatter generation
- export_to_file: End-to-end export with directory structure
"""

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.integrations.exporters.hugo import HugoExporter


@pytest.fixture
def exporter():
    """Create a HugoExporter instance."""
    return HugoExporter()


@pytest.fixture
def sample_metadata():
    """Create sample ConversationMetadata."""
    return ConversationMetadata(
        source="claude",
        model="claude-3",
        created_at=datetime(2024, 6, 15, 12, 0, 0),
        updated_at=datetime(2024, 6, 15, 14, 0, 0),
        tags=["python", "testing"],
        starred_at=datetime(2024, 6, 16),
        pinned_at=None,
        archived_at=None,
    )


@pytest.fixture
def sample_conversation(sample_metadata):
    """Create a simple conversation tree for testing."""
    conv = ConversationTree(
        id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        title="Test Conversation About Python",
        metadata=sample_metadata,
    )
    # Add a simple message path
    msg1 = Message(
        id="msg1",
        role=MessageRole.USER,
        content=MessageContent(text="Hello, how are you?"),
    )
    msg2 = Message(
        id="msg2",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="I'm doing well, thank you!"),
        parent_id="msg1",
    )
    conv.add_message(msg1)
    conv.add_message(msg2)
    return conv


@pytest.fixture
def minimal_conversation():
    """Conversation with minimal metadata (no tags, no source, no date)."""
    metadata = ConversationMetadata()
    # ConversationMetadata defaults created_at/updated_at to datetime.now()
    # so we must explicitly clear them to test "no date" code paths
    metadata.created_at = None
    metadata.updated_at = None
    metadata.source = None
    metadata.model = None
    metadata.tags = []
    metadata.starred_at = None
    metadata.pinned_at = None
    metadata.archived_at = None
    conv = ConversationTree(
        id="deadbeef-0000-0000-0000-000000000000",
        title="Minimal",
        metadata=metadata,
    )
    msg = Message(
        id="msg1",
        role=MessageRole.USER,
        content=MessageContent(text="Hello"),
    )
    conv.add_message(msg)
    return conv


# ==================== _get_target_dir ====================


class TestGetTargetDir:
    """Tests for organization strategy directory selection."""

    @pytest.mark.unit
    def test_none_strategy_returns_base(self, exporter, sample_conversation, tmp_path):
        """'none' strategy should return base directory unchanged."""
        result = exporter._get_target_dir(sample_conversation, tmp_path, "none")
        assert result == tmp_path

    @pytest.mark.unit
    def test_tags_strategy_uses_first_tag(self, exporter, sample_conversation, tmp_path):
        """'tags' strategy should use the first tag as subdirectory."""
        result = exporter._get_target_dir(sample_conversation, tmp_path, "tags")
        assert result == tmp_path / "python"

    @pytest.mark.unit
    def test_tags_strategy_no_tags(self, exporter, minimal_conversation, tmp_path):
        """'tags' strategy with no tags should use 'untagged'."""
        result = exporter._get_target_dir(minimal_conversation, tmp_path, "tags")
        assert result == tmp_path / "untagged"

    @pytest.mark.unit
    def test_tags_strategy_special_chars(self, exporter, tmp_path):
        """Tags with special characters should be sanitized to valid dir names."""
        metadata = ConversationMetadata(tags=["C++/C#"])
        conv = ConversationTree(id="test", title="Test", metadata=metadata)
        msg = Message(id="msg1", role=MessageRole.USER, content=MessageContent(text="x"))
        conv.add_message(msg)
        result = exporter._get_target_dir(conv, tmp_path, "tags")
        # Should not be empty or contain invalid chars
        dir_name = result.name
        assert dir_name  # Not empty
        assert "/" not in dir_name

    @pytest.mark.unit
    def test_tags_strategy_all_special_chars_fallback(self, exporter, tmp_path):
        """Tags with ALL special characters should fall back to 'untagged'."""
        metadata = ConversationMetadata(tags=["!!!@@@###"])
        conv = ConversationTree(id="test", title="Test", metadata=metadata)
        msg = Message(id="msg1", role=MessageRole.USER, content=MessageContent(text="x"))
        conv.add_message(msg)
        result = exporter._get_target_dir(conv, tmp_path, "tags")
        assert result == tmp_path / "untagged"

    @pytest.mark.unit
    def test_source_strategy(self, exporter, sample_conversation, tmp_path):
        """'source' strategy should use source name as subdirectory."""
        result = exporter._get_target_dir(sample_conversation, tmp_path, "source")
        assert result == tmp_path / "claude"

    @pytest.mark.unit
    def test_source_strategy_no_source(self, exporter, minimal_conversation, tmp_path):
        """'source' strategy with no source should use 'unknown'."""
        result = exporter._get_target_dir(minimal_conversation, tmp_path, "source")
        assert result == tmp_path / "unknown"

    @pytest.mark.unit
    def test_source_strategy_special_chars_fallback(self, exporter, tmp_path):
        """Source with all special chars should fall back to 'unknown'."""
        metadata = ConversationMetadata(source="@#$%")
        conv = ConversationTree(id="test", title="Test", metadata=metadata)
        msg = Message(id="msg1", role=MessageRole.USER, content=MessageContent(text="x"))
        conv.add_message(msg)
        result = exporter._get_target_dir(conv, tmp_path, "source")
        assert result == tmp_path / "unknown"

    @pytest.mark.unit
    def test_date_strategy(self, exporter, sample_conversation, tmp_path):
        """'date' strategy should organize by YYYY/MM."""
        result = exporter._get_target_dir(sample_conversation, tmp_path, "date")
        assert result == tmp_path / "2024" / "06"

    @pytest.mark.unit
    def test_date_strategy_no_date(self, exporter, minimal_conversation, tmp_path):
        """'date' strategy with no date should use 'undated'."""
        result = exporter._get_target_dir(minimal_conversation, tmp_path, "date")
        assert result == tmp_path / "undated"

    @pytest.mark.unit
    def test_unknown_strategy_returns_base(self, exporter, sample_conversation, tmp_path):
        """Unknown strategy should fall back to base directory."""
        result = exporter._get_target_dir(sample_conversation, tmp_path, "unknown_strategy")
        assert result == tmp_path


# ==================== _generate_slug ====================


class TestGenerateSlug:
    """Tests for URL-safe slug generation."""

    @pytest.mark.unit
    def test_basic_slug(self, exporter):
        """Simple title should produce clean slug with ID suffix."""
        result = exporter._generate_slug("Hello World", "a1b2c3d4")
        assert "hello-world" in result
        assert "a1b2c3d4" in result

    @pytest.mark.unit
    def test_special_characters_removed(self, exporter):
        """Special characters should be removed from slug."""
        result = exporter._generate_slug("Hello, World! @#$%", "abcdef12")
        assert "," not in result
        assert "!" not in result
        assert "@" not in result

    @pytest.mark.unit
    def test_long_title_truncated(self, exporter):
        """Titles longer than 50 chars should be truncated."""
        long_title = "a " * 40  # 80 chars
        result = exporter._generate_slug(long_title, "abcdef12")
        # Slug part (before ID suffix) should be reasonable length
        assert len(result) < 80

    @pytest.mark.unit
    def test_empty_title_uses_id(self, exporter):
        """Empty title should fall back to just the ID."""
        result = exporter._generate_slug("", "abcdef12")
        assert result == "abcdef12"

    @pytest.mark.unit
    def test_untitled_generates_slug(self, exporter):
        """'untitled' should produce a valid slug."""
        result = exporter._generate_slug("untitled", "abcdef12")
        assert "untitled" in result

    @pytest.mark.unit
    def test_unicode_handling(self, exporter):
        """Unicode characters should be handled gracefully."""
        result = exporter._generate_slug("Test with unicode", "abcdef12")
        assert isinstance(result, str)
        assert len(result) > 0


# ==================== _format_role ====================


class TestFormatRole:
    """Tests for role display formatting."""

    @pytest.mark.unit
    def test_user_role(self, exporter):
        assert exporter._format_role("user") == "User"

    @pytest.mark.unit
    def test_assistant_role(self, exporter):
        assert exporter._format_role("assistant") == "Assistant"

    @pytest.mark.unit
    def test_system_role(self, exporter):
        assert exporter._format_role("system") == "System"

    @pytest.mark.unit
    def test_tool_role(self, exporter):
        assert exporter._format_role("tool") == "Tool"

    @pytest.mark.unit
    def test_human_alias(self, exporter):
        assert exporter._format_role("human") == "User"

    @pytest.mark.unit
    def test_ai_alias(self, exporter):
        assert exporter._format_role("ai") == "Assistant"

    @pytest.mark.unit
    def test_unknown_role_capitalized(self, exporter):
        assert exporter._format_role("moderator") == "Moderator"

    @pytest.mark.unit
    def test_case_insensitive(self, exporter):
        assert exporter._format_role("USER") == "User"
        assert exporter._format_role("Assistant") == "Assistant"


# ==================== _generate_frontmatter ====================


class TestGenerateFrontmatter:
    """Tests for YAML frontmatter generation."""

    @pytest.mark.unit
    def test_includes_title(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert 'title: "Test Conversation About Python"' in fm

    @pytest.mark.unit
    def test_includes_date(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert "date: 2024-06-15" in fm

    @pytest.mark.unit
    def test_includes_lastmod(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert "lastmod:" in fm

    @pytest.mark.unit
    def test_draft_false_by_default(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert "draft: false" in fm

    @pytest.mark.unit
    def test_draft_true_when_requested(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, True)
        assert "draft: true" in fm

    @pytest.mark.unit
    def test_includes_tags(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert '"python"' in fm
        assert '"testing"' in fm

    @pytest.mark.unit
    def test_includes_source_category(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert 'categories: ["claude"]' in fm

    @pytest.mark.unit
    def test_includes_conversation_id(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert sample_conversation.id in fm

    @pytest.mark.unit
    def test_includes_starred_flag(self, exporter, sample_conversation):
        fm = exporter._generate_frontmatter(sample_conversation, False)
        assert "starred: true" in fm

    @pytest.mark.unit
    def test_minimal_metadata(self, exporter, minimal_conversation):
        """Minimal metadata should still produce valid frontmatter."""
        fm = exporter._generate_frontmatter(minimal_conversation, False)
        assert "title:" in fm
        assert "draft: false" in fm

    @pytest.mark.unit
    def test_title_with_quotes_escaped(self, exporter):
        """Quotes in title should be escaped for YAML safety."""
        metadata = ConversationMetadata()
        conv = ConversationTree(
            id="test",
            title='He said "hello"',
            metadata=metadata,
        )
        fm = exporter._generate_frontmatter(conv, False)
        assert '\\"hello\\"' in fm


# ==================== export_to_file (integration) ====================


class TestExportToFile:
    """Integration tests for the full export pipeline."""

    @pytest.mark.unit
    def test_creates_index_md(self, exporter, sample_conversation, tmp_path):
        """Export should create an index.md file."""
        exporter.export_to_file([sample_conversation], str(tmp_path))
        # Find the index.md somewhere in the output
        index_files = list(tmp_path.rglob("index.md"))
        assert len(index_files) >= 1

    @pytest.mark.unit
    def test_index_md_has_frontmatter(self, exporter, sample_conversation, tmp_path):
        """index.md should contain YAML frontmatter delimiters."""
        exporter.export_to_file([sample_conversation], str(tmp_path))
        index_files = list(tmp_path.rglob("index.md"))
        assert len(index_files) >= 1
        content = index_files[0].read_text()
        assert content.startswith("---\n")
        assert "---\n\n" in content

    @pytest.mark.unit
    def test_index_md_has_messages(self, exporter, sample_conversation, tmp_path):
        """index.md should contain conversation messages."""
        exporter.export_to_file([sample_conversation], str(tmp_path))
        index_files = list(tmp_path.rglob("index.md"))
        content = index_files[0].read_text()
        assert "Hello, how are you?" in content
        assert "I'm doing well, thank you!" in content

    @pytest.mark.unit
    def test_date_prefix_in_bundle_name(self, exporter, sample_conversation, tmp_path):
        """Bundle directory should include date prefix by default."""
        exporter.export_to_file(
            [sample_conversation], str(tmp_path), hugo_organize="none"
        )
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) >= 1
        assert "2024-06-15" in dirs[0].name

    @pytest.mark.unit
    def test_no_date_prefix(self, exporter, sample_conversation, tmp_path):
        """date_prefix=False should omit date from bundle name."""
        exporter.export_to_file(
            [sample_conversation],
            str(tmp_path),
            date_prefix=False,
            hugo_organize="none",
        )
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) >= 1
        # Should NOT start with date pattern
        assert not dirs[0].name.startswith("2024-")

    @pytest.mark.unit
    def test_organize_by_date(self, exporter, sample_conversation, tmp_path):
        """date organization should create YYYY/MM subdirectories."""
        exporter.export_to_file(
            [sample_conversation], str(tmp_path), hugo_organize="date"
        )
        # Should have 2024/06/ structure
        assert (tmp_path / "2024" / "06").exists()

    @pytest.mark.unit
    def test_organize_by_tags(self, exporter, sample_conversation, tmp_path):
        """tags organization should create tag subdirectory."""
        exporter.export_to_file(
            [sample_conversation], str(tmp_path), hugo_organize="tags"
        )
        assert (tmp_path / "python").exists()

    @pytest.mark.unit
    def test_multiple_conversations(self, exporter, sample_conversation, minimal_conversation, tmp_path):
        """Multiple conversations should each get their own bundle."""
        exporter.export_to_file(
            [sample_conversation, minimal_conversation],
            str(tmp_path),
            hugo_organize="none",
        )
        index_files = list(tmp_path.rglob("index.md"))
        assert len(index_files) == 2

    @pytest.mark.unit
    def test_empty_conversation_list(self, exporter, tmp_path):
        """Empty conversation list should create output dir but no bundles."""
        exporter.export_to_file([], str(tmp_path))
        assert tmp_path.exists()
        index_files = list(tmp_path.rglob("index.md"))
        assert len(index_files) == 0
