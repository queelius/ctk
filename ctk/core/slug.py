"""
Slug generation utilities for CTK.

Provides functions for creating URL-friendly slugs from conversation titles.
"""

import re
import unicodedata
from typing import Optional


def generate_slug(title: Optional[str], max_length: int = 60) -> Optional[str]:
    """
    Generate a URL-friendly slug from a conversation title.

    Args:
        title: The conversation title to convert
        max_length: Maximum length of the slug (default 60)

    Returns:
        A lowercase, hyphen-separated slug, or None if title is empty

    Examples:
        >>> generate_slug("Discussion about Python type hints")
        'discussion-about-python-type-hints'
        >>> generate_slug("What's the best way to handle errors?")
        'whats-the-best-way-to-handle-errors'
        >>> generate_slug("API Integration: OAuth2 & JWT")
        'api-integration-oauth2-jwt'
    """
    if not title:
        return None

    # Normalize unicode characters
    slug = unicodedata.normalize("NFKD", title)
    slug = slug.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase
    slug = slug.lower()

    # Replace common separators with hyphens
    slug = re.sub(r"[:\-_/\\|]", "-", slug)

    # Handle contractions - keep the letters, just remove apostrophe
    slug = re.sub(r"'s\b", "s", slug)  # "what's" -> "whats"
    slug = re.sub(r"n't\b", "nt", slug)  # "don't" -> "dont"
    slug = re.sub(r"'ll\b", "ll", slug)  # "we'll" -> "well"
    slug = re.sub(r"'re\b", "re", slug)  # "they're" -> "theyre"
    slug = re.sub(r"'ve\b", "ve", slug)  # "I've" -> "ive"
    slug = re.sub(r"'d\b", "d", slug)  # "I'd" -> "id"
    slug = re.sub(r"'", "", slug)  # Remove remaining apostrophes

    # Replace any non-alphanumeric characters with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)

    # Remove leading/trailing hyphens
    slug = slug.strip("-")

    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)

    # Truncate to max length, respecting word boundaries
    if len(slug) > max_length:
        # Try to break at a hyphen
        truncated = slug[:max_length]
        last_hyphen = truncated.rfind("-")
        if last_hyphen > max_length // 2:
            slug = truncated[:last_hyphen]
        else:
            slug = truncated.rstrip("-")

    return slug if slug else None


def make_unique_slug(base_slug: str, existing_slugs: set, max_suffix: int = 100) -> str:
    """
    Make a slug unique by appending a numeric suffix if needed.

    Args:
        base_slug: The base slug to make unique
        existing_slugs: Set of existing slugs to check against
        max_suffix: Maximum suffix number to try (default 100)

    Returns:
        A unique slug (possibly with numeric suffix)

    Examples:
        >>> make_unique_slug("hello-world", {"hello-world"})
        'hello-world-2'
        >>> make_unique_slug("test", {"test", "test-2"})
        'test-3'
    """
    if base_slug not in existing_slugs:
        return base_slug

    for i in range(2, max_suffix + 1):
        candidate = f"{base_slug}-{i}"
        if candidate not in existing_slugs:
            return candidate

    # Fallback: use timestamp
    import time

    return f"{base_slug}-{int(time.time())}"


def slug_matches(slug: str, query: str) -> bool:
    """
    Check if a query matches a slug (supports partial matching).

    Args:
        slug: The full slug to match against
        query: The query string (may be partial)

    Returns:
        True if query matches slug

    Examples:
        >>> slug_matches("discussion-python-hints", "discussion")
        True
        >>> slug_matches("discussion-python-hints", "python")
        True
        >>> slug_matches("discussion-python-hints", "disc-py")
        False
    """
    if not slug or not query:
        return False

    # Exact match
    if slug == query:
        return True

    # Prefix match
    if slug.startswith(query):
        return True

    # Word-based partial match (all query words must appear in order)
    query_words = query.split("-")
    slug_words = slug.split("-")

    query_idx = 0
    for slug_word in slug_words:
        if query_idx < len(query_words) and slug_word.startswith(
            query_words[query_idx]
        ):
            query_idx += 1
        if query_idx == len(query_words):
            return True

    return False
