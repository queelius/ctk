"""
Unit tests for semantic and index commands

Tests the semantic search/similar and index build/status/clear
command implementations.
"""

import pytest

from ctk.core.command_dispatcher import CommandResult
from ctk.core.commands.semantic import (IndexCommands, SemanticCommands,
                                        create_semantic_commands)
from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)
from ctk.core.vfs_navigator import VFSNavigator


class MockTUI:
    """Mock TUI instance for testing"""

    def __init__(self, vfs_cwd="/"):
        self.vfs_cwd = vfs_cwd


@pytest.fixture
def test_db(tmp_path):
    """Create test database with sample conversations"""
    db_path = tmp_path / "test_semantic.db"
    db = ConversationDB(str(db_path))

    # Conversations with overlapping vocabulary to ensure nonzero similarity
    conversations = [
        {
            "id": "aabbcc001122334455667788",
            "title": "Python Machine Learning Tutorial",
            "messages": [
                ("user", "How do I train a machine learning model in Python?"),
                (
                    "assistant",
                    "You can use Python libraries like scikit-learn or PyTorch "
                    "for machine learning model training and data analysis.",
                ),
                (
                    "user",
                    "Which Python framework is better for data science beginners?",
                ),
                (
                    "assistant",
                    "For data science beginners, scikit-learn is great for machine "
                    "learning while pandas handles data processing in Python.",
                ),
            ],
        },
        {
            "id": "ddeeff112233445566778899",
            "title": "Python Data Analysis with Pandas",
            "messages": [
                ("user", "How to analyze data using Python pandas library?"),
                (
                    "assistant",
                    "Python pandas is excellent for data analysis. Use DataFrames "
                    "for data processing and machine learning preparation.",
                ),
                ("user", "What Python tools work well with pandas for data science?"),
                (
                    "assistant",
                    "For data science in Python, combine pandas with scikit-learn "
                    "for machine learning and matplotlib for data visualization.",
                ),
            ],
        },
        {
            "id": "112233aabbccddeeff009988",
            "title": "JavaScript Web Development",
            "messages": [
                ("user", "How to build a React web application with JavaScript?"),
                (
                    "assistant",
                    "Use create-react-app or Vite to scaffold a JavaScript React "
                    "project for web development.",
                ),
                ("user", "What JavaScript web frameworks are popular?"),
                (
                    "assistant",
                    "Popular JavaScript web frameworks include React, Vue, and "
                    "Angular for modern web development.",
                ),
            ],
        },
    ]

    for conv_data in conversations:
        conv = ConversationTree(
            id=conv_data["id"],
            title=conv_data["title"],
            metadata=ConversationMetadata(source="test"),
        )

        parent_id = None
        for i, (role, content) in enumerate(conv_data["messages"]):
            msg = Message(
                id=f"{conv_data['id']}_msg_{i}",
                role=MessageRole(role),
                content=MessageContent(text=content),
                parent_id=parent_id,
            )
            conv.add_message(msg)
            parent_id = msg.id

        db.save_conversation(conv)

    yield db
    db.close()


@pytest.fixture
def empty_db(tmp_path):
    """Create empty test database"""
    db_path = tmp_path / "empty_semantic.db"
    db = ConversationDB(str(db_path))
    yield db
    db.close()


@pytest.fixture
def semantic_handler(test_db):
    """Create semantic command handler"""
    navigator = VFSNavigator(test_db)
    tui_instance = MockTUI(vfs_cwd="/")
    return SemanticCommands(test_db, navigator, tui_instance)


@pytest.fixture
def index_handler(test_db):
    """Create index command handler"""
    navigator = VFSNavigator(test_db)
    tui_instance = MockTUI(vfs_cwd="/")
    return IndexCommands(test_db, navigator, tui_instance)


# ==================== Factory Function Tests ====================


class TestCreateSemanticCommands:
    """Test the factory function"""

    @pytest.mark.unit
    def test_returns_dict_with_expected_keys(self, test_db):
        """Factory returns dict with 'semantic' and 'index' keys"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        commands = create_semantic_commands(test_db, navigator, tui_instance)

        assert isinstance(commands, dict)
        assert "semantic" in commands
        assert "index" in commands

    @pytest.mark.unit
    def test_commands_are_callable(self, test_db):
        """All returned commands are callable"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        commands = create_semantic_commands(test_db, navigator, tui_instance)

        for name, handler in commands.items():
            assert callable(handler), f"Command '{name}' is not callable"

    @pytest.mark.unit
    def test_semantic_command_is_functional(self, test_db):
        """The semantic command handler works when invoked"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        commands = create_semantic_commands(test_db, navigator, tui_instance)
        result = commands["semantic"]([], stdin="")

        assert isinstance(result, CommandResult)
        assert result.success is False  # No args = usage error

    @pytest.mark.unit
    def test_index_command_is_functional(self, test_db):
        """The index command handler works when invoked"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        commands = create_semantic_commands(test_db, navigator, tui_instance)
        result = commands["index"]([], stdin="")

        assert isinstance(result, CommandResult)
        assert result.success is False  # No args = usage error


# ==================== Semantic Command Tests ====================


class TestSemanticCommand:
    """Test semantic command dispatch"""

    @pytest.mark.unit
    def test_no_args_shows_usage(self, semantic_handler):
        """Calling semantic with no args shows usage"""
        result = semantic_handler.cmd_semantic([], stdin="")

        assert result.success is False
        assert "Usage" in result.error or "usage" in result.error.lower()

    @pytest.mark.unit
    def test_unknown_subcommand(self, semantic_handler):
        """Unknown subcommand returns error"""
        result = semantic_handler.cmd_semantic(["unknown"], stdin="")

        assert result.success is False
        assert "unknown subcommand" in result.error

    @pytest.mark.unit
    def test_search_subcommand_dispatches(self, semantic_handler):
        """'search' subcommand dispatches correctly"""
        result = semantic_handler.cmd_semantic(["search"], stdin="")

        # Should fail because no query, but should reach the search handler
        assert result.success is False
        assert "query required" in result.error

    @pytest.mark.unit
    def test_similar_subcommand_dispatches(self, semantic_handler):
        """'similar' subcommand dispatches correctly"""
        result = semantic_handler.cmd_semantic(["similar"], stdin="")

        # Should fail because no ID, but should reach the similar handler
        assert result.success is False
        assert "conversation ID required" in result.error


# ==================== Semantic Search Tests ====================


class TestSemanticSearch:
    """Test semantic search command"""

    @pytest.mark.unit
    def test_search_no_embeddings(self, semantic_handler):
        """Search with no embeddings returns informational message"""
        result = semantic_handler.cmd_semantic(["search", "python"], stdin="")

        assert result.success is True
        assert "index build" in result.output.lower()

    @pytest.mark.unit
    def test_search_no_query(self, semantic_handler):
        """Search with no query returns error"""
        result = semantic_handler.cmd_semantic(["search"], stdin="")

        assert result.success is False
        assert "query required" in result.error

    @pytest.mark.unit
    def test_search_with_embeddings(self, test_db):
        """Search returns results when embeddings exist"""
        # First build the index
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        index_handler = IndexCommands(test_db, navigator, tui_instance)

        build_result = index_handler.cmd_index(["build"], stdin="")
        assert build_result.success is True

        # Now search
        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)
        result = semantic_handler.cmd_semantic(["search", "python", "neural"], stdin="")

        assert result.success is True
        assert result.output  # Should have some output

    @pytest.mark.unit
    def test_search_multi_word_query(self, test_db):
        """Search with multiple words joins them"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        index_handler = IndexCommands(test_db, navigator, tui_instance)
        index_handler.cmd_index(["build"], stdin="")

        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)
        result = semantic_handler.cmd_semantic(
            ["search", "machine", "learning", "python"], stdin=""
        )

        assert result.success is True


# ==================== Semantic Similar Tests ====================


class TestSemanticSimilar:
    """Test semantic similar command"""

    @pytest.mark.unit
    def test_similar_no_id(self, semantic_handler):
        """Similar with no ID returns error"""
        result = semantic_handler.cmd_semantic(["similar"], stdin="")

        assert result.success is False
        assert "conversation ID required" in result.error

    @pytest.mark.unit
    def test_similar_no_embeddings(self, semantic_handler):
        """Similar with no embeddings returns informational message"""
        result = semantic_handler.cmd_semantic(
            ["similar", "aabbcc001122334455667788"], stdin=""
        )

        assert result.success is True
        assert "index build" in result.output.lower()

    @pytest.mark.unit
    def test_similar_nonexistent_conversation(self, semantic_handler):
        """Similar with nonexistent ID returns error"""
        result = semantic_handler.cmd_semantic(
            ["similar", "nonexistent_id_xxxxxxxxx"], stdin=""
        )

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.unit
    def test_similar_dot_not_in_conversation(self, semantic_handler):
        """Similar with '.' when not in a conversation returns error"""
        semantic_handler.tui.vfs_cwd = "/"

        result = semantic_handler.cmd_semantic(["similar", "."], stdin="")

        assert result.success is False
        assert "not in a conversation" in result.error

    @pytest.mark.unit
    def test_similar_dot_in_conversation(self, test_db):
        """Similar with '.' resolves current conversation"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI(vfs_cwd="/chats/aabbcc001122334455667788")

        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)
        result = semantic_handler.cmd_semantic(["similar", "."], stdin="")

        # Should succeed (with informational message about no embeddings)
        assert result.success is True
        assert "index build" in result.output.lower()

    @pytest.mark.unit
    def test_similar_with_embeddings(self, test_db):
        """Similar returns results when embeddings exist"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        # Build index first
        index_handler = IndexCommands(test_db, navigator, tui_instance)
        build_result = index_handler.cmd_index(["build"], stdin="")
        assert build_result.success is True

        # Now find similar
        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)
        result = semantic_handler.cmd_semantic(
            ["similar", "aabbcc001122334455667788"], stdin=""
        )

        assert result.success is True
        assert "Similar to:" in result.output

    @pytest.mark.unit
    def test_similar_with_prefix_id(self, test_db):
        """Similar resolves prefix IDs via db.resolve_identifier"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        # Build index
        index_handler = IndexCommands(test_db, navigator, tui_instance)
        index_handler.cmd_index(["build"], stdin="")

        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)
        # Use prefix of the first conversation ID
        result = semantic_handler.cmd_semantic(["similar", "aabbcc"], stdin="")

        assert result.success is True
        assert "Similar to:" in result.output


# ==================== Index Command Tests ====================


class TestIndexCommand:
    """Test index command dispatch"""

    @pytest.mark.unit
    def test_no_args_shows_usage(self, index_handler):
        """Calling index with no args shows usage"""
        result = index_handler.cmd_index([], stdin="")

        assert result.success is False
        assert "Usage" in result.error or "usage" in result.error.lower()

    @pytest.mark.unit
    def test_unknown_subcommand(self, index_handler):
        """Unknown subcommand returns error"""
        result = index_handler.cmd_index(["unknown"], stdin="")

        assert result.success is False
        assert "unknown subcommand" in result.error


# ==================== Index Build Tests ====================


class TestIndexBuild:
    """Test index build command"""

    @pytest.mark.unit
    def test_build_default(self, index_handler):
        """Build with defaults succeeds"""
        result = index_handler.cmd_index(["build"], stdin="")

        assert result.success is True
        assert "Built 3 embeddings" in result.output

    @pytest.mark.unit
    def test_build_with_limit(self, index_handler):
        """Build with --limit restricts count"""
        result = index_handler.cmd_index(["build", "--limit", "2"], stdin="")

        assert result.success is True
        assert "Built 2 embeddings" in result.output

    @pytest.mark.unit
    def test_build_with_provider(self, index_handler):
        """Build with --provider tfidf works"""
        result = index_handler.cmd_index(["build", "--provider", "tfidf"], stdin="")

        assert result.success is True
        assert "Built" in result.output

    @pytest.mark.unit
    def test_build_unsupported_provider(self, index_handler):
        """Build with unsupported provider returns error"""
        result = index_handler.cmd_index(["build", "--provider", "openai"], stdin="")

        assert result.success is False
        assert "unsupported provider" in result.error

    @pytest.mark.unit
    def test_build_invalid_limit(self, index_handler):
        """Build with invalid limit returns error"""
        result = index_handler.cmd_index(["build", "--limit", "abc"], stdin="")

        assert result.success is False
        assert "invalid limit" in result.error

    @pytest.mark.unit
    def test_build_unknown_option(self, index_handler):
        """Build with unknown option returns error"""
        result = index_handler.cmd_index(["build", "--foo"], stdin="")

        assert result.success is False
        assert "unknown option" in result.error

    @pytest.mark.unit
    def test_build_empty_database(self, empty_db):
        """Build on empty database returns informational message"""
        navigator = VFSNavigator(empty_db)
        tui_instance = MockTUI()
        handler = IndexCommands(empty_db, navigator, tui_instance)

        result = handler.cmd_index(["build"], stdin="")

        assert result.success is True
        assert "No conversations to index" in result.output

    @pytest.mark.unit
    def test_build_creates_embeddings_in_db(self, test_db, index_handler):
        """Build actually stores embeddings in the database"""
        # Verify no embeddings before
        embeddings_before = test_db.get_all_embeddings()
        assert len(embeddings_before) == 0

        result = index_handler.cmd_index(["build"], stdin="")
        assert result.success is True

        # Verify embeddings after
        embeddings_after = test_db.get_all_embeddings()
        assert len(embeddings_after) == 3

    @pytest.mark.unit
    def test_build_idempotent(self, index_handler, test_db):
        """Building twice updates existing embeddings (doesn't duplicate)"""
        result1 = index_handler.cmd_index(["build"], stdin="")
        assert result1.success is True

        result2 = index_handler.cmd_index(["build"], stdin="")
        assert result2.success is True

        # Should still have exactly 3 embeddings (updated, not duplicated)
        embeddings = test_db.get_all_embeddings()
        assert len(embeddings) == 3


# ==================== Index Status Tests ====================


class TestIndexStatus:
    """Test index status command"""

    @pytest.mark.unit
    def test_status_no_embeddings(self, index_handler):
        """Status with no embeddings shows 0"""
        result = index_handler.cmd_index(["status"], stdin="")

        assert result.success is True
        assert "Indexed: 0" in result.output
        assert "0%" in result.output

    @pytest.mark.unit
    def test_status_with_embeddings(self, test_db):
        """Status with embeddings shows correct counts"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        handler = IndexCommands(test_db, navigator, tui_instance)

        # Build first
        handler.cmd_index(["build"], stdin="")

        # Check status
        result = handler.cmd_index(["status"], stdin="")

        assert result.success is True
        assert "Indexed: 3" in result.output
        assert "100%" in result.output
        assert "tfidf" in result.output

    @pytest.mark.unit
    def test_status_shows_total_conversations(self, index_handler):
        """Status shows total conversation count"""
        result = index_handler.cmd_index(["status"], stdin="")

        assert result.success is True
        assert "Total conversations: 3" in result.output

    @pytest.mark.unit
    def test_status_empty_database(self, empty_db):
        """Status on empty database shows zeros"""
        navigator = VFSNavigator(empty_db)
        tui_instance = MockTUI()
        handler = IndexCommands(empty_db, navigator, tui_instance)

        result = handler.cmd_index(["status"], stdin="")

        assert result.success is True
        assert "Indexed: 0" in result.output
        assert "Total conversations: 0" in result.output


# ==================== Index Clear Tests ====================


class TestIndexClear:
    """Test index clear command"""

    @pytest.mark.unit
    def test_clear_when_empty(self, index_handler):
        """Clear when no embeddings succeeds with message"""
        result = index_handler.cmd_index(["clear"], stdin="")

        assert result.success is True
        assert "No embeddings to clear" in result.output

    @pytest.mark.unit
    def test_clear_after_build(self, test_db):
        """Clear removes all embeddings"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        handler = IndexCommands(test_db, navigator, tui_instance)

        # Build first
        handler.cmd_index(["build"], stdin="")

        # Verify embeddings exist
        assert len(test_db.get_all_embeddings()) == 3

        # Clear
        result = handler.cmd_index(["clear"], stdin="")

        assert result.success is True
        assert "Cleared 3 embeddings" in result.output

        # Verify embeddings gone
        assert len(test_db.get_all_embeddings()) == 0

    @pytest.mark.unit
    def test_clear_with_provider_filter(self, test_db):
        """Clear with --provider only removes matching embeddings"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        handler = IndexCommands(test_db, navigator, tui_instance)

        # Build
        handler.cmd_index(["build"], stdin="")

        # Clear only tfidf
        result = handler.cmd_index(["clear", "--provider", "tfidf"], stdin="")

        assert result.success is True
        assert "Cleared 3 embeddings" in result.output

    @pytest.mark.unit
    def test_clear_nonexistent_provider(self, test_db):
        """Clear with nonexistent provider clears nothing"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        handler = IndexCommands(test_db, navigator, tui_instance)

        # Build with tfidf
        handler.cmd_index(["build"], stdin="")

        # Clear with different provider
        result = handler.cmd_index(["clear", "--provider", "openai"], stdin="")

        assert result.success is True
        assert "No embeddings to clear" in result.output

        # Verify tfidf embeddings still exist
        assert len(test_db.get_all_embeddings()) == 3

    @pytest.mark.unit
    def test_clear_unknown_option(self, index_handler):
        """Clear with unknown option returns error"""
        result = index_handler.cmd_index(["clear", "--foo"], stdin="")

        assert result.success is False
        assert "unknown option" in result.error


# ==================== VFS Context Resolution Tests ====================


class TestVFSContextResolution:
    """Test resolving current conversation from VFS path"""

    @pytest.mark.unit
    def test_resolve_from_chats_path(self, test_db):
        """Resolves conversation ID from /chats/<id> path"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI(vfs_cwd="/chats/aabbcc001122334455667788")
        handler = SemanticCommands(test_db, navigator, tui_instance)

        conv_id = handler._resolve_current_conversation()
        assert conv_id == "aabbcc001122334455667788"

    @pytest.mark.unit
    def test_resolve_from_root(self, test_db):
        """Returns None when at root"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI(vfs_cwd="/")
        handler = SemanticCommands(test_db, navigator, tui_instance)

        conv_id = handler._resolve_current_conversation()
        assert conv_id is None

    @pytest.mark.unit
    def test_resolve_from_message_path(self, test_db):
        """Resolves conversation ID from message path"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI(vfs_cwd="/chats/aabbcc001122334455667788/m1/m2")
        handler = SemanticCommands(test_db, navigator, tui_instance)

        conv_id = handler._resolve_current_conversation()
        assert conv_id == "aabbcc001122334455667788"

    @pytest.mark.unit
    def test_resolve_no_tui(self, test_db):
        """Returns None when no TUI instance"""
        navigator = VFSNavigator(test_db)
        handler = SemanticCommands(test_db, navigator, tui_instance=None)

        conv_id = handler._resolve_current_conversation()
        assert conv_id is None


# ==================== Integration Tests (Build + Search) ====================


class TestBuildAndSearch:
    """Test full workflows of building and then searching"""

    @pytest.mark.unit
    def test_build_then_search(self, test_db):
        """Full workflow: build index, then search"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        # Build
        index_handler = IndexCommands(test_db, navigator, tui_instance)
        build_result = index_handler.cmd_index(["build"], stdin="")
        assert build_result.success is True

        # Search
        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)
        search_result = semantic_handler.cmd_semantic(
            ["search", "neural", "network"], stdin=""
        )
        assert search_result.success is True
        assert search_result.output  # Should have output

    @pytest.mark.unit
    def test_build_then_similar(self, test_db):
        """Full workflow: build index, then find similar"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        # Build
        index_handler = IndexCommands(test_db, navigator, tui_instance)
        build_result = index_handler.cmd_index(["build"], stdin="")
        assert build_result.success is True

        # Find similar
        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)
        similar_result = semantic_handler.cmd_semantic(
            ["similar", "aabbcc001122334455667788"], stdin=""
        )
        assert similar_result.success is True
        assert "Similar to:" in similar_result.output

    @pytest.mark.unit
    def test_build_clear_search(self, test_db):
        """Build, clear, then search should say no embeddings"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        index_handler = IndexCommands(test_db, navigator, tui_instance)
        semantic_handler = SemanticCommands(test_db, navigator, tui_instance)

        # Build
        index_handler.cmd_index(["build"], stdin="")

        # Clear
        index_handler.cmd_index(["clear"], stdin="")

        # Search should say no embeddings
        result = semantic_handler.cmd_semantic(["search", "python"], stdin="")
        assert result.success is True
        assert "index build" in result.output.lower()

    @pytest.mark.unit
    def test_build_status_clear_status(self, test_db):
        """Full lifecycle: build, check status, clear, check status"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()
        handler = IndexCommands(test_db, navigator, tui_instance)

        # Initial status
        status1 = handler.cmd_index(["status"], stdin="")
        assert "Indexed: 0" in status1.output

        # Build
        handler.cmd_index(["build"], stdin="")

        # Status after build
        status2 = handler.cmd_index(["status"], stdin="")
        assert "Indexed: 3" in status2.output

        # Clear
        handler.cmd_index(["clear"], stdin="")

        # Status after clear
        status3 = handler.cmd_index(["status"], stdin="")
        assert "Indexed: 0" in status3.output
