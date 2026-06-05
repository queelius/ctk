"""Tests for ctk/core/network_tools.py.

Covers:
- execute_network_tool dispatch: find_similar_conversations and list_neighbors
- _resolve_id: full id, prefix match, missing id
- Empty similarity graph returns sensible empty/not-found strings
- Populated similarity graph returns formatted results
- Unknown tool name returns error string
- Module-level provider registration
"""

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.core.network_tools import (
    _resolve_id,
    execute_network_tool,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tree(conv_id: str, title: str = "Test") -> ConversationTree:
    """Return a minimal ConversationTree with one user message."""
    tree = ConversationTree(
        id=conv_id,
        title=title,
        metadata=ConversationMetadata(
            source="test",
            model="test-model",
            created_at=None,
            updated_at=None,
        ),
    )
    msg = Message(
        role=MessageRole.USER,
        content=MessageContent(text=f"Hello from {conv_id}"),
        parent_id=None,
    )
    tree.add_message(msg)
    return tree


def _insert_similarity(db, id1: str, id2: str, score: float) -> None:
    """Insert a SimilarityModel row directly (ids must already be saved conversations)."""
    from ctk.core.db_models import SimilarityModel

    # Canonical ordering: id1 < id2
    if id1 > id2:
        id1, id2 = id2, id1

    with db.session_scope() as session:
        row = SimilarityModel(
            conversation1_id=id1,
            conversation2_id=id2,
            similarity=score,
            metric="cosine",
            provider="test",
            model=None,
        )
        session.add(row)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_db():
    """In-memory DB with no conversations or similarities."""
    return ConversationDB(":memory:")


@pytest.fixture
def populated_db():
    """In-memory DB with three conversations and one similarity pair."""
    db = ConversationDB(":memory:")
    db.save_conversation(_make_tree("aaaa-1111", "Python Tips"))
    db.save_conversation(_make_tree("bbbb-2222", "Cooking Basics"))
    db.save_conversation(_make_tree("cccc-3333", "Gardening"))
    _insert_similarity(db, "aaaa-1111", "bbbb-2222", 0.75)
    return db


@pytest.fixture
def multi_sim_db():
    """In-memory DB with several similarity pairs."""
    db = ConversationDB(":memory:")
    for cid in ["a-001", "a-002", "a-003", "a-004"]:
        db.save_conversation(_make_tree(cid, f"Conv {cid}"))
    _insert_similarity(db, "a-001", "a-002", 0.90)
    _insert_similarity(db, "a-001", "a-003", 0.70)
    _insert_similarity(db, "a-001", "a-004", 0.50)
    return db


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveId:
    def test_resolves_full_id(self, populated_db):
        result = _resolve_id(populated_db, "aaaa-1111")
        assert result == "aaaa-1111"

    def test_resolves_prefix(self, populated_db):
        # "bbbb" uniquely identifies "bbbb-2222"
        result = _resolve_id(populated_db, "bbbb")
        assert result == "bbbb-2222"

    def test_returns_none_for_missing_id(self, populated_db):
        result = _resolve_id(populated_db, "zzzz-not-there")
        assert result is None

    def test_returns_none_for_empty_string(self, populated_db):
        result = _resolve_id(populated_db, "")
        assert result is None

    def test_returns_none_on_empty_db(self, empty_db):
        result = _resolve_id(empty_db, "aaaa")
        assert result is None

    def test_resolves_another_full_id(self, populated_db):
        result = _resolve_id(populated_db, "cccc-3333")
        assert result == "cccc-3333"


# ---------------------------------------------------------------------------
# execute_network_tool: unknown tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteNetworkToolUnknown:
    def test_unknown_tool_returns_error(self, empty_db):
        result = execute_network_tool(empty_db, "nonexistent_tool", {})
        assert result.startswith("Error:")
        assert "nonexistent_tool" in result


# ---------------------------------------------------------------------------
# execute_network_tool: find_similar_conversations (empty graph)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindSimilarEmpty:
    def test_no_conversation_found(self, empty_db):
        result = execute_network_tool(
            empty_db,
            "find_similar_conversations",
            {"conversation_id": "not-here"},
        )
        assert result.startswith("Error:")
        assert "not-here" in result

    def test_no_similarities_recorded(self, populated_db):
        # cccc-3333 exists but has no similarity rows
        result = execute_network_tool(
            populated_db,
            "find_similar_conversations",
            {"conversation_id": "cccc-3333"},
        )
        assert "no similarities recorded" in result.lower()

    def test_empty_string_conversation_id(self, empty_db):
        result = execute_network_tool(
            empty_db,
            "find_similar_conversations",
            {"conversation_id": ""},
        )
        assert result.startswith("Error:")

    def test_missing_conversation_id_key(self, empty_db):
        # args.get("conversation_id", "") returns "" -> _resolve_id("") -> None
        result = execute_network_tool(
            empty_db,
            "find_similar_conversations",
            {},
        )
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# execute_network_tool: find_similar_conversations (populated graph)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindSimilarPopulated:
    def test_returns_similar_conversation(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "find_similar_conversations",
            {"conversation_id": "aaaa-1111"},
        )
        # Should mention the other conversation's id prefix
        assert "bbbb" in result
        assert "0.750" in result

    def test_reverse_direction_works(self, populated_db):
        # Pair is stored canonically; querying from bbbb side should also work
        result = execute_network_tool(
            populated_db,
            "find_similar_conversations",
            {"conversation_id": "bbbb-2222"},
        )
        assert "aaaa" in result

    def test_prefix_resolution_then_similarity(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "find_similar_conversations",
            {"conversation_id": "aaaa"},
        )
        assert "bbbb" in result

    def test_limit_respected(self, multi_sim_db):
        result = execute_network_tool(
            multi_sim_db,
            "find_similar_conversations",
            {"conversation_id": "a-001", "limit": 1},
        )
        lines = [l for l in result.strip().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_min_similarity_filters(self, multi_sim_db):
        # With min_similarity=0.8 only the 0.90 pair should survive
        result = execute_network_tool(
            multi_sim_db,
            "find_similar_conversations",
            {"conversation_id": "a-001", "min_similarity": 0.80},
        )
        assert "a-002" in result
        # a-003 (0.70) and a-004 (0.50) should be absent
        assert "a-003" not in result
        assert "a-004" not in result

    def test_min_similarity_too_high_returns_empty_message(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "find_similar_conversations",
            {"conversation_id": "aaaa-1111", "min_similarity": 0.999},
        )
        assert "no similarities recorded" in result.lower()

    def test_returns_title_in_output(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "find_similar_conversations",
            {"conversation_id": "aaaa-1111"},
        )
        assert "Cooking Basics" in result

    def test_default_limit_is_ten(self, multi_sim_db):
        # Default limit is 10, we only have 3 pairs; all should appear
        result = execute_network_tool(
            multi_sim_db,
            "find_similar_conversations",
            {"conversation_id": "a-001"},
        )
        lines = [l for l in result.strip().splitlines() if l.strip()]
        assert len(lines) == 3  # three similarity rows stored


# ---------------------------------------------------------------------------
# execute_network_tool: list_neighbors (empty graph)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListNeighborsEmpty:
    def test_no_conversation_found(self, empty_db):
        result = execute_network_tool(
            empty_db,
            "list_neighbors",
            {"conversation_id": "not-here"},
        )
        assert result.startswith("Error:")
        assert "not-here" in result

    def test_no_neighbors(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "list_neighbors",
            {"conversation_id": "cccc-3333"},
        )
        assert "no neighbors found" in result.lower()

    def test_empty_conversation_id(self, empty_db):
        result = execute_network_tool(
            empty_db,
            "list_neighbors",
            {"conversation_id": ""},
        )
        assert result.startswith("Error:")

    def test_missing_conversation_id_key(self, empty_db):
        result = execute_network_tool(
            empty_db,
            "list_neighbors",
            {},
        )
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# execute_network_tool: list_neighbors (populated graph)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListNeighborsPopulated:
    def test_returns_neighbor(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "list_neighbors",
            {"conversation_id": "aaaa-1111"},
        )
        assert "bbbb" in result

    def test_reverse_direction(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "list_neighbors",
            {"conversation_id": "bbbb-2222"},
        )
        assert "aaaa" in result

    def test_prefix_resolution(self, populated_db):
        result = execute_network_tool(
            populated_db,
            "list_neighbors",
            {"conversation_id": "aaaa"},
        )
        assert "bbbb" in result

    def test_limit_respected(self, multi_sim_db):
        result = execute_network_tool(
            multi_sim_db,
            "list_neighbors",
            {"conversation_id": "a-001", "limit": 2},
        )
        lines = [l for l in result.strip().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_default_limit_is_twenty(self, multi_sim_db):
        # Default limit is 20; only 3 pairs stored
        result = execute_network_tool(
            multi_sim_db,
            "list_neighbors",
            {"conversation_id": "a-001"},
        )
        lines = [l for l in result.strip().splitlines() if l.strip()]
        assert len(lines) == 3

    def test_neighbors_sorted_descending(self, multi_sim_db):
        result = execute_network_tool(
            multi_sim_db,
            "list_neighbors",
            {"conversation_id": "a-001"},
        )
        # Extract scores from lines like "a-002xx  Conv ...  (0.900)"
        import re
        scores = re.findall(r"\((\d+\.\d+)\)", result)
        scores = [float(s) for s in scores]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Module-level provider registration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProviderRegistration:
    def test_network_provider_is_registered(self):
        from ctk.core import network_tools  # noqa: F401 (imported for side effects)
        from ctk.core.tools_registry import iter_providers

        names = [p.name for p in iter_providers()]
        assert "ctk.network" in names

    def test_network_provider_has_two_tools(self):
        from ctk.core.tools_registry import iter_providers

        providers = {p.name: p for p in iter_providers()}
        net = providers.get("ctk.network")
        assert net is not None
        tool_names = [t["name"] for t in net.tools]
        assert "find_similar_conversations" in tool_names
        assert "list_neighbors" in tool_names

    def test_find_similar_schema_requires_conversation_id(self):
        from ctk.core.tools_registry import iter_providers

        providers = {p.name: p for p in iter_providers()}
        net = providers["ctk.network"]
        find_tool = next(t for t in net.tools if t["name"] == "find_similar_conversations")
        assert "conversation_id" in find_tool["input_schema"]["required"]

    def test_list_neighbors_schema_requires_conversation_id(self):
        from ctk.core.tools_registry import iter_providers

        providers = {p.name: p for p in iter_providers()}
        net = providers["ctk.network"]
        nb_tool = next(t for t in net.tools if t["name"] == "list_neighbors")
        assert "conversation_id" in nb_tool["input_schema"]["required"]
