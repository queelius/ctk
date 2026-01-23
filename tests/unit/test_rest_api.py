"""
Comprehensive tests for the REST API endpoints.
"""

import json
# Mock flask_cors before importing RestInterface
import sys
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

sys.modules["flask_cors"] = MagicMock()

from ctk.core.models import (ConversationTree, Message, MessageContent,
                             MessageRole)
from ctk.interfaces.base import InterfaceResponse, ResponseStatus
from ctk.interfaces.rest.api import RestInterface


@pytest.fixture
def mock_db():
    """Create a mock database"""
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    return db


@pytest.fixture
def rest_interface(mock_db):
    """Create a RestInterface with mocked database"""
    with patch.object(RestInterface, "db", new_callable=PropertyMock) as mock_db_prop:
        mock_db_prop.return_value = mock_db
        interface = RestInterface(db_path=":memory:")
        interface._db = mock_db
        yield interface


@pytest.fixture
def sample_conversation():
    """Create a sample conversation for testing"""
    conv = ConversationTree(title="Test Conversation")
    msg1 = Message(role=MessageRole.USER, content=MessageContent(text="Hello"))
    msg2 = Message(
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="Hi there!"),
        parent_id=msg1.id,
    )
    conv.add_message(msg1)
    conv.add_message(msg2)
    return conv


class TestOrganizationEndpoints:
    """Tests for organization endpoints (star, pin, archive, etc.)"""

    def test_star_conversation_success(self, rest_interface, mock_db):
        """Test starring a conversation"""
        mock_db.star_conversation = MagicMock()

        response = rest_interface.star_conversation("conv-123", star=True)

        assert response.status == ResponseStatus.SUCCESS
        assert "starred" in response.message
        mock_db.star_conversation.assert_called_once_with("conv-123", star=True)

    def test_unstar_conversation_success(self, rest_interface, mock_db):
        """Test unstarring a conversation"""
        mock_db.star_conversation = MagicMock()

        response = rest_interface.star_conversation("conv-123", star=False)

        assert response.status == ResponseStatus.SUCCESS
        assert "unstarred" in response.message
        mock_db.star_conversation.assert_called_once_with("conv-123", star=False)

    def test_pin_conversation_success(self, rest_interface, mock_db):
        """Test pinning a conversation"""
        mock_db.pin_conversation = MagicMock()

        response = rest_interface.pin_conversation("conv-123", pin=True)

        assert response.status == ResponseStatus.SUCCESS
        assert "pinned" in response.message
        mock_db.pin_conversation.assert_called_once_with("conv-123", pin=True)

    def test_unpin_conversation_success(self, rest_interface, mock_db):
        """Test unpinning a conversation"""
        mock_db.pin_conversation = MagicMock()

        response = rest_interface.pin_conversation("conv-123", pin=False)

        assert response.status == ResponseStatus.SUCCESS
        assert "unpinned" in response.message

    def test_archive_conversation_success(self, rest_interface, mock_db):
        """Test archiving a conversation"""
        mock_db.archive_conversation = MagicMock()

        response = rest_interface.archive_conversation("conv-123", archive=True)

        assert response.status == ResponseStatus.SUCCESS
        assert "archived" in response.message
        mock_db.archive_conversation.assert_called_once_with("conv-123", archive=True)

    def test_unarchive_conversation_success(self, rest_interface, mock_db):
        """Test unarchiving a conversation"""
        mock_db.archive_conversation = MagicMock()

        response = rest_interface.archive_conversation("conv-123", archive=False)

        assert response.status == ResponseStatus.SUCCESS
        assert "unarchived" in response.message

    def test_rename_conversation_success(self, rest_interface, mock_db):
        """Test renaming a conversation"""
        mock_db.update_conversation_metadata = MagicMock()

        response = rest_interface.rename_conversation("conv-123", "New Title")

        assert response.status == ResponseStatus.SUCCESS
        assert "renamed" in response.message
        mock_db.update_conversation_metadata.assert_called_once_with(
            "conv-123", title="New Title"
        )

    def test_duplicate_conversation_success(self, rest_interface, mock_db):
        """Test duplicating a conversation"""
        new_conv = MagicMock()
        new_conv.id = "new-conv-456"
        mock_db.duplicate_conversation = MagicMock(return_value=new_conv)

        response = rest_interface.duplicate_conversation(
            "conv-123", "Copy of Conversation"
        )

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["new_conversation_id"] == "new-conv-456"
        mock_db.duplicate_conversation.assert_called_once_with(
            "conv-123", new_title="Copy of Conversation"
        )

    def test_star_conversation_no_db(self):
        """Test starring when database not initialized"""
        # Create interface without patching db property to test actual no-db behavior
        with patch.object(
            RestInterface, "db", new_callable=PropertyMock
        ) as mock_db_prop:
            mock_db_prop.return_value = None
            interface = RestInterface(db_path=None)

            response = interface.star_conversation("conv-123", star=True)

            assert response.status == ResponseStatus.ERROR
            assert "not initialized" in response.message


class TestTagEndpoints:
    """Tests for tag management endpoints"""

    def test_list_tags_success(self, rest_interface, mock_db):
        """Test listing all tags"""
        mock_db.get_all_tags = MagicMock(
            return_value=[
                {"name": "work", "count": 10},
                {"name": "personal", "count": 5},
            ]
        )

        response = rest_interface.list_tags()

        assert response.status == ResponseStatus.SUCCESS
        assert len(response.data["tags"]) == 2
        mock_db.get_all_tags.assert_called_once_with(with_counts=True)

    def test_add_tags_success(self, rest_interface, mock_db):
        """Test adding tags to a conversation"""
        mock_db.add_tags = MagicMock()

        response = rest_interface.add_tags("conv-123", ["work", "important"])

        assert response.status == ResponseStatus.SUCCESS
        assert "2 tags" in response.message
        mock_db.add_tags.assert_called_once_with("conv-123", ["work", "important"])

    def test_remove_tag_success(self, rest_interface, mock_db):
        """Test removing a tag from a conversation"""
        mock_db.remove_tag = MagicMock()

        response = rest_interface.remove_tag("conv-123", "work")

        assert response.status == ResponseStatus.SUCCESS
        assert "Removed tag" in response.message
        mock_db.remove_tag.assert_called_once_with("conv-123", "work")

    def test_list_conversations_by_tag_success(self, rest_interface, mock_db):
        """Test listing conversations by tag"""
        mock_conv = MagicMock()
        mock_conv.to_dict = MagicMock(return_value={"id": "conv-1", "title": "Test"})
        mock_db.list_conversations_by_tag = MagicMock(return_value=[mock_conv])

        response = rest_interface.list_conversations_by_tag("work", limit=50, offset=0)

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["total"] == 1
        mock_db.list_conversations_by_tag.assert_called_once_with("work")


class TestMetadataEndpoints:
    """Tests for metadata endpoints"""

    def test_list_models_success(self, rest_interface, mock_db):
        """Test listing all models"""
        mock_db.get_models = MagicMock(
            return_value=[
                {"model": "gpt-4", "count": 100},
                {"model": "claude-3", "count": 50},
            ]
        )

        response = rest_interface.list_models()

        assert response.status == ResponseStatus.SUCCESS
        assert len(response.data["models"]) == 2

    def test_list_sources_success(self, rest_interface, mock_db):
        """Test listing all sources"""
        mock_db.get_sources = MagicMock(
            return_value=[
                {"source": "ChatGPT", "count": 80},
                {"source": "Claude", "count": 40},
            ]
        )

        response = rest_interface.list_sources()

        assert response.status == ResponseStatus.SUCCESS
        assert len(response.data["sources"]) == 2

    def test_get_timeline_success(self, rest_interface, mock_db):
        """Test getting conversation timeline"""
        mock_db.get_conversation_timeline = MagicMock(
            return_value=[
                {"date": "2024-01-01", "count": 10},
                {"date": "2024-01-02", "count": 15},
            ]
        )

        response = rest_interface.get_timeline(granularity="day", limit=30)

        assert response.status == ResponseStatus.SUCCESS
        assert len(response.data["timeline"]) == 2
        mock_db.get_conversation_timeline.assert_called_once_with(
            granularity="day", limit=30
        )


class TestTreePathEndpoints:
    """Tests for tree/path endpoints"""

    def test_get_conversation_tree_success(
        self, rest_interface, mock_db, sample_conversation
    ):
        """Test getting conversation tree structure"""
        mock_db.load_conversation = MagicMock(return_value=sample_conversation)

        response = rest_interface.get_conversation_tree(sample_conversation.id)

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["title"] == "Test Conversation"
        assert "roots" in response.data
        assert "branch_count" in response.data
        assert "path_count" in response.data

    def test_get_conversation_tree_not_found(self, rest_interface, mock_db):
        """Test getting tree for non-existent conversation"""
        mock_db.load_conversation = MagicMock(return_value=None)

        response = rest_interface.get_conversation_tree("non-existent")

        assert response.status == ResponseStatus.ERROR
        assert "not found" in response.message

    def test_list_conversation_paths_success(
        self, rest_interface, mock_db, sample_conversation
    ):
        """Test listing all paths in a conversation"""
        mock_db.load_conversation = MagicMock(return_value=sample_conversation)

        response = rest_interface.list_conversation_paths(sample_conversation.id)

        assert response.status == ResponseStatus.SUCCESS
        assert "paths" in response.data
        assert response.data["total"] >= 1

    def test_get_conversation_path_success(
        self, rest_interface, mock_db, sample_conversation
    ):
        """Test getting a specific path"""
        mock_db.load_conversation = MagicMock(return_value=sample_conversation)

        response = rest_interface.get_conversation_path(sample_conversation.id, 0)

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["path_index"] == 0
        assert "messages" in response.data

    def test_get_conversation_path_out_of_range(
        self, rest_interface, mock_db, sample_conversation
    ):
        """Test getting a path with invalid index"""
        mock_db.load_conversation = MagicMock(return_value=sample_conversation)

        response = rest_interface.get_conversation_path(sample_conversation.id, 999)

        assert response.status == ResponseStatus.ERROR
        assert "out of range" in response.message


class TestViewsEndpoints:
    """Tests for views endpoints"""

    def test_list_views_success(self, rest_interface):
        """Test listing all views"""
        mock_view_store = MagicMock()
        mock_view_store.list_views_detailed = MagicMock(
            return_value=[
                {"name": "favorites", "title": "My Favorites"},
                {"name": "work", "title": "Work Conversations"},
            ]
        )

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.list_views()

        assert response.status == ResponseStatus.SUCCESS
        assert len(response.data["views"]) == 2

    def test_create_view_success(self, rest_interface):
        """Test creating a new view"""
        mock_view_store = MagicMock()
        mock_view = MagicMock()
        mock_view_store.create_view = MagicMock(return_value=mock_view)
        mock_view_store.save = MagicMock()

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.create_view(
                {
                    "name": "test-view",
                    "title": "Test View",
                    "description": "A test view",
                }
            )

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["name"] == "test-view"

    def test_create_view_missing_name(self, rest_interface):
        """Test creating a view without name"""
        mock_view_store = MagicMock()

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.create_view({"title": "No Name"})

        assert response.status == ResponseStatus.ERROR
        assert "name is required" in response.message

    def test_get_view_json_success(self, rest_interface):
        """Test getting a view as JSON"""
        mock_view_store = MagicMock()
        mock_view = MagicMock()
        mock_view.to_dict = MagicMock(
            return_value={"name": "test-view", "title": "Test View"}
        )
        mock_view_store.load = MagicMock(return_value=mock_view)

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.get_view("test-view", format_type="json")

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["name"] == "test-view"

    def test_get_view_yaml_success(self, rest_interface):
        """Test getting a view as YAML"""
        mock_view_store = MagicMock()
        mock_view = MagicMock()
        mock_view.to_dict = MagicMock(
            return_value={"name": "test-view", "title": "Test View"}
        )
        mock_view_store.load = MagicMock(return_value=mock_view)

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.get_view("test-view", format_type="yaml")

        assert response.status == ResponseStatus.SUCCESS
        assert "name:" in response.data  # YAML format

    def test_get_view_not_found(self, rest_interface):
        """Test getting a non-existent view"""
        mock_view_store = MagicMock()
        mock_view_store.load = MagicMock(return_value=None)

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.get_view("non-existent")

        assert response.status == ResponseStatus.ERROR
        assert "not found" in response.message

    def test_delete_view_success(self, rest_interface):
        """Test deleting a view"""
        mock_view_store = MagicMock()
        mock_view_store.load = MagicMock(return_value=MagicMock())
        mock_view_store.delete = MagicMock()

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.delete_view("test-view")

        assert response.status == ResponseStatus.SUCCESS
        mock_view_store.delete.assert_called_once_with("test-view")

    def test_evaluate_view_success(self, rest_interface, mock_db):
        """Test evaluating a view"""
        mock_view_store = MagicMock()
        mock_evaluated = MagicMock()
        mock_evaluated.title = "Test View"
        mock_evaluated.items = [
            MagicMock(
                conversation_id="conv-1",
                title_override="Title 1",
                annotation="Note",
                path=None,
            )
        ]
        mock_view_store.evaluate = MagicMock(return_value=mock_evaluated)

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.evaluate_view("test-view")

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["item_count"] == 1

    def test_add_to_view_success(self, rest_interface):
        """Test adding conversations to a view"""
        mock_view_store = MagicMock()
        mock_view_store.add_to_view = MagicMock()

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.add_to_view("test-view", ["conv-1", "conv-2"], {})

        assert response.status == ResponseStatus.SUCCESS
        assert "2 conversations" in response.message

    def test_remove_from_view_success(self, rest_interface):
        """Test removing a conversation from a view"""
        mock_view_store = MagicMock()
        mock_view_store.remove_from_view = MagicMock()

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.remove_from_view("test-view", "conv-1")

        assert response.status == ResponseStatus.SUCCESS

    def test_check_view_success(self, rest_interface, mock_db):
        """Test checking a view for drift"""
        mock_view_store = MagicMock()
        mock_view_store.check_view = MagicMock(
            return_value={"valid": True, "missing": [], "drifted": []}
        )

        with patch.object(
            rest_interface, "_get_view_store", return_value=mock_view_store
        ):
            response = rest_interface.check_view("test-view")

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["valid"] == True


class TestSearchEndpoints:
    """Tests for enhanced search functionality"""

    def test_search_with_basic_query(self, rest_interface, mock_db):
        """Test basic search"""
        mock_result = MagicMock()
        mock_result.to_dict = MagicMock(return_value={"id": "conv-1", "title": "Test"})
        mock_db.search_conversations = MagicMock(return_value=[mock_result])

        response = rest_interface.search_conversations("python", limit=10)

        assert response.status == ResponseStatus.SUCCESS
        assert response.data["total"] == 1

    def test_search_with_advanced_filters(self, rest_interface, mock_db):
        """Test search with advanced filters"""
        mock_result = MagicMock()
        mock_result.to_dict = MagicMock(return_value={"id": "conv-1", "title": "Test"})
        mock_db.search_conversations = MagicMock(return_value=[mock_result])

        options = {
            "title_only": True,
            "date_from": "2024-01-01",
            "date_to": "2024-12-31",
            "source": "ChatGPT",
            "model": "gpt-4",
            "starred": True,
            "order_by": "created_at",
            "ascending": False,
        }

        response = rest_interface.search_conversations(
            "test", limit=50, options=options
        )

        assert response.status == ResponseStatus.SUCCESS
        mock_db.search_conversations.assert_called_once()
        call_kwargs = mock_db.search_conversations.call_args[1]
        assert call_kwargs["title_only"] == True
        assert call_kwargs["source"] == "ChatGPT"
        assert call_kwargs["starred"] == True

    def test_search_with_message_count_filters(self, rest_interface, mock_db):
        """Test search with message count filters"""
        mock_db.search_conversations = MagicMock(return_value=[])

        options = {"min_messages": 5, "max_messages": 100, "has_branches": True}

        response = rest_interface.search_conversations("", limit=100, options=options)

        assert response.status == ResponseStatus.SUCCESS
        call_kwargs = mock_db.search_conversations.call_args[1]
        assert call_kwargs["min_messages"] == 5
        assert call_kwargs["max_messages"] == 100
        assert call_kwargs["has_branches"] == True


class TestErrorHandling:
    """Tests for error handling"""

    def test_star_conversation_exception(self, rest_interface, mock_db):
        """Test error handling when starring fails"""
        mock_db.star_conversation = MagicMock(side_effect=Exception("Database error"))

        response = rest_interface.star_conversation("conv-123", star=True)

        assert response.status == ResponseStatus.ERROR
        assert "error" in response.message.lower()

    def test_list_tags_exception(self, rest_interface, mock_db):
        """Test error handling when listing tags fails"""
        mock_db.get_all_tags = MagicMock(side_effect=Exception("Database error"))

        response = rest_interface.list_tags()

        assert response.status == ResponseStatus.ERROR

    def test_view_store_not_available(self, rest_interface):
        """Test when view store is not available"""
        rest_interface.db_path = None

        response = rest_interface.list_views()

        assert response.status == ResponseStatus.ERROR
        assert "not initialized" in response.message


class TestInterfaceResponse:
    """Tests for InterfaceResponse helper methods"""

    def test_success_response(self):
        """Test creating a success response"""
        response = InterfaceResponse.success(data={"key": "value"}, message="Success!")

        assert response.status == ResponseStatus.SUCCESS
        assert response.data == {"key": "value"}
        assert response.message == "Success!"

    def test_error_response(self):
        """Test creating an error response"""
        response = InterfaceResponse.error(
            message="Something went wrong", errors=["Error 1"]
        )

        assert response.status == ResponseStatus.ERROR
        assert response.message == "Something went wrong"
        assert "Error 1" in response.errors

    def test_to_dict(self):
        """Test converting response to dictionary"""
        response = InterfaceResponse.success(data={"id": 1}, message="OK")
        result = response.to_dict()

        assert result["status"] == "success"
        assert result["data"] == {"id": 1}
        assert result["message"] == "OK"
