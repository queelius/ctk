"""
Base interface class that all CTK interfaces must implement
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import logging

from ctk.core.models import ConversationTree, Message
from ctk.core.database import ConversationDB


class ResponseStatus(Enum):
    """Status codes for interface responses"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class InterfaceResponse:
    """Standard response structure for all interfaces"""
    status: ResponseStatus
    data: Optional[Any] = None
    message: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'status': self.status.value,
            'data': self.data,
            'message': self.message,
            'errors': self.errors,
            'warnings': self.warnings,
            'metadata': self.metadata
        }

    @classmethod
    def success(cls, data: Any = None, message: str = None) -> 'InterfaceResponse':
        """Create a success response"""
        return cls(
            status=ResponseStatus.SUCCESS,
            data=data,
            message=message
        )

    @classmethod
    def error(cls, message: str, errors: List[str] = None) -> 'InterfaceResponse':
        """Create an error response"""
        return cls(
            status=ResponseStatus.ERROR,
            message=message,
            errors=errors or []
        )


class BaseInterface(ABC):
    """
    Base class for all CTK interfaces.
    Each interface (CLI, REST, MCP, Web) must implement these methods.
    """

    def __init__(self, db_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the interface

        Args:
            db_path: Path to the database file
            config: Configuration dictionary for the interface
        """
        self.db_path = db_path
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._db: Optional[ConversationDB] = None

    @property
    def db(self) -> ConversationDB:
        """Lazy-load database connection"""
        if self._db is None and self.db_path:
            self._db = ConversationDB(self.db_path)
        return self._db

    @abstractmethod
    def initialize(self) -> InterfaceResponse:
        """
        Initialize the interface (setup routes, connections, etc.)
        Must be implemented by each interface.
        """
        pass

    @abstractmethod
    def shutdown(self) -> InterfaceResponse:
        """
        Clean shutdown of the interface
        Must be implemented by each interface.
        """
        pass

    # Core operations that all interfaces should support

    @abstractmethod
    def import_conversations(
        self,
        source: Union[str, Dict, List],
        format: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **kwargs
    ) -> InterfaceResponse:
        """
        Import conversations from various sources

        Args:
            source: File path, dictionary, or list of conversations
            format: Import format (auto-detect if None)
            tags: Tags to apply to imported conversations
            **kwargs: Additional format-specific options
        """
        pass

    @abstractmethod
    def export_conversations(
        self,
        output: str,
        format: str = "jsonl",
        conversation_ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> InterfaceResponse:
        """
        Export conversations to various formats

        Args:
            output: Output file path or stream
            format: Export format (jsonl, json, markdown, etc.)
            conversation_ids: Specific conversation IDs to export
            filters: Filter criteria for conversations
            **kwargs: Additional format-specific options
        """
        pass

    @abstractmethod
    def search_conversations(
        self,
        query: str,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> InterfaceResponse:
        """
        Search conversations

        Args:
            query: Search query string
            limit: Maximum number of results
            filters: Additional filter criteria
            **kwargs: Additional search options
        """
        pass

    @abstractmethod
    def list_conversations(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "updated_at",
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> InterfaceResponse:
        """
        List conversations with pagination

        Args:
            limit: Number of conversations to return
            offset: Pagination offset
            sort_by: Sort field
            filters: Filter criteria
            **kwargs: Additional listing options
        """
        pass

    @abstractmethod
    def get_conversation(
        self,
        conversation_id: str,
        include_paths: bool = False,
        **kwargs
    ) -> InterfaceResponse:
        """
        Get a specific conversation

        Args:
            conversation_id: ID of the conversation
            include_paths: Whether to include all conversation paths
            **kwargs: Additional options
        """
        pass

    @abstractmethod
    def update_conversation(
        self,
        conversation_id: str,
        updates: Dict[str, Any],
        **kwargs
    ) -> InterfaceResponse:
        """
        Update a conversation's metadata

        Args:
            conversation_id: ID of the conversation
            updates: Dictionary of updates to apply
            **kwargs: Additional options
        """
        pass

    @abstractmethod
    def delete_conversation(
        self,
        conversation_id: str,
        **kwargs
    ) -> InterfaceResponse:
        """
        Delete a conversation

        Args:
            conversation_id: ID of the conversation to delete
            **kwargs: Additional options
        """
        pass

    @abstractmethod
    def get_statistics(self, **kwargs) -> InterfaceResponse:
        """
        Get database statistics

        Args:
            **kwargs: Additional options for statistics
        """
        pass

    # Helper methods that can be shared across interfaces

    def validate_format(self, format: str, valid_formats: List[str]) -> bool:
        """Validate that a format is supported"""
        return format.lower() in [f.lower() for f in valid_formats]

    def apply_filters(
        self,
        query,
        filters: Dict[str, Any]
    ):
        """Apply common filters to a database query"""
        if 'source' in filters:
            query = query.filter_by(source=filters['source'])
        if 'model' in filters:
            query = query.filter_by(model=filters['model'])
        if 'project' in filters:
            query = query.filter_by(project=filters['project'])
        if 'tags' in filters:
            # Handle tag filtering
            pass
        return query

    def handle_error(self, exception: Exception) -> InterfaceResponse:
        """Standard error handling"""
        self.logger.error(f"Error in {self.__class__.__name__}: {str(exception)}", exc_info=True)
        return InterfaceResponse.error(
            message=f"An error occurred: {str(exception)}",
            errors=[str(exception)]
        )