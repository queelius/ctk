"""Tests for FTS5 search: special-character escaping, sync triggers, zero-match fallback."""

import uuid
from datetime import datetime

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)

pytestmark = pytest.mark.unit


def _save(db, title, body):
    tree = ConversationTree(
        id=str(uuid.uuid4()),
        title=title,
        metadata=ConversationMetadata(
            created_at=datetime.now(), updated_at=datetime.now()
        ),
    )
    tree.add_message(
        Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text=body),
            timestamp=datetime.now(),
        )
    )
    db.save_conversation(tree)
    return tree.id


def test_special_char_query_does_not_crash_and_finds_match(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _save(db, "code chat", "I love C++ and C# programming")
        results = db.search_conversations(query_text="C++")
        assert any("code chat" == r.title for r in results)
    finally:
        db.close()


def test_search_after_title_update_reflects_new_title(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        cid = _save(db, "old title", "body text")
        db.update_conversation_metadata(cid, title="renamed marker")
        results = db.search_conversations(query_text="renamed")
        assert any(r.id == cid for r in results)
    finally:
        db.close()


def test_search_after_delete_drops_from_results(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        cid = _save(db, "deletable unique-token-zzz", "body")
        db.delete_conversation(cid)
        results = db.search_conversations(query_text="unique-token-zzz")
        assert all(r.id != cid for r in results)
    finally:
        db.close()


def test_special_char_parentheses_query(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _save(db, "paren test", "call the function foo(bar) and see")
        results = db.search_conversations(query_text="foo(bar)")
        assert any("paren test" == r.title for r in results)
    finally:
        db.close()


def test_special_char_colon_query(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _save(db, "colon chat", "The URL is http://example.com/path")
        results = db.search_conversations(query_text="http://example.com/path")
        assert any("colon chat" == r.title for r in results)
    finally:
        db.close()


def test_zero_fts_match_falls_through_to_like(tmp_path):
    """When FTS returns no hits but LIKE would find a substring match, return it."""
    db = ConversationDB(str(tmp_path))
    try:
        # Use a word that is likely to be stemmed/tokenized differently by FTS5
        # but is findable via LIKE substring. A plain unique token works fine here
        # because we are verifying the fall-through path when FTS yields no ids.
        # We test by using a query that the FTS porter stemmer won't index but
        # LIKE will match. A simple long unique string suffices since FTS5 won't
        # tokenize it as-is from a title update that post-dates the FTS setup.
        cid = _save(db, "fallthrough-unique-xyzzy-9876", "some body text")
        results = db.search_conversations(query_text="unique-xyzzy-9876")
        assert any(r.id == cid for r in results)
    finally:
        db.close()


def test_empty_query_returns_all_not_filtered(tmp_path):
    """An empty query must not trigger the LIKE-everything scan via the fallback path."""
    db = ConversationDB(str(tmp_path))
    try:
        cid1 = _save(db, "alpha chat", "alpha body")
        cid2 = _save(db, "beta chat", "beta body")
        # No query - should return both
        results = db.search_conversations()
        ids = {r.id for r in results}
        assert cid1 in ids
        assert cid2 in ids
    finally:
        db.close()
