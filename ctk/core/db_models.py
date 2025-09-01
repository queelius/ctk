"""
SQLAlchemy database models for CTK
"""

from datetime import datetime
from typing import Optional, List
import json
import enum

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Boolean, 
    ForeignKey, Table, JSON, Enum, Index, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


# Association table for many-to-many relationship between conversations and tags
conversation_tags = Table(
    'conversation_tags',
    Base.metadata,
    Column('conversation_id', String, ForeignKey('conversations.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)


class RoleEnum(enum.Enum):
    """Message role enumeration"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"
    TOOL_RESULT = "tool_result"


class ConversationModel(Base):
    """SQLAlchemy model for conversations"""
    __tablename__ = 'conversations'
    
    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True)
    
    # Basic fields
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Metadata as JSON
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Extracted metadata fields for querying
    version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    project: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Relationships
    messages: Mapped[List["MessageModel"]] = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    tags: Mapped[List["TagModel"]] = relationship(
        "TagModel",
        secondary=conversation_tags,
        back_populates="conversations",
        lazy="dynamic"
    )
    
    paths: Mapped[List["PathModel"]] = relationship(
        "PathModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_conv_source', 'source'),
        Index('idx_conv_model', 'model'),
        Index('idx_conv_project', 'project'),
        Index('idx_conv_updated', 'updated_at'),
    )
    
    @hybrid_property
    def message_count(self) -> int:
        """Get total message count"""
        return self.messages.count()
    
    @hybrid_property
    def root_messages(self):
        """Get root messages (no parent)"""
        return self.messages.filter(MessageModel.parent_id == None)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata_json,
            'source': self.source,
            'model': self.model,
            'project': self.project,
            'message_count': self.message_count,
            'tags': [tag.name for tag in self.tags]
        }


class MessageModel(Base):
    """SQLAlchemy model for messages"""
    __tablename__ = 'messages'
    
    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True)
    
    # Foreign key to conversation
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey('conversations.id'))
    
    # Message fields
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum))
    content_json: Mapped[dict] = mapped_column(JSON)  # Full MessageContent as JSON
    
    # Tree structure (self-referential)
    parent_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey('messages.id'), nullable=True)
    
    # Timestamps
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel",
        back_populates="messages"
    )
    
    # Self-referential relationship for tree structure
    parent: Mapped[Optional["MessageModel"]] = relationship(
        "MessageModel",
        remote_side=[id],
        backref="children"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_msg_conversation', 'conversation_id'),
        Index('idx_msg_parent', 'parent_id'),
        Index('idx_msg_role', 'role'),
        Index('idx_msg_timestamp', 'timestamp'),
    )
    
    @hybrid_property
    def child_count(self) -> int:
        """Get number of direct children"""
        return len(self.children)
    
    @hybrid_property
    def is_leaf(self) -> bool:
        """Check if this is a leaf node"""
        return len(self.children) == 0
    
    @hybrid_property
    def is_root(self) -> bool:
        """Check if this is a root node"""
        return self.parent_id is None
    
    def get_path_to_root(self) -> List["MessageModel"]:
        """Get all messages from this node to root"""
        path = []
        current = self
        while current:
            path.append(current)
            current = current.parent
        return list(reversed(path))
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role.value,
            'content': self.content_json,
            'parent_id': self.parent_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'metadata': self.metadata_json,
            'child_count': self.child_count
        }


class TagModel(Base):
    """SQLAlchemy model for tags"""
    __tablename__ = 'tags'
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Tag name (unique)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    
    # Tag metadata
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., "project", "topic", "language"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # For UI display
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Relationships
    conversations: Mapped[List["ConversationModel"]] = relationship(
        "ConversationModel",
        secondary=conversation_tags,
        back_populates="tags",
        lazy="dynamic"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_tag_category', 'category'),
    )
    
    @hybrid_property
    def usage_count(self) -> int:
        """Get number of conversations using this tag"""
        return self.conversations.count()
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'description': self.description,
            'color': self.color,
            'usage_count': self.usage_count
        }


class PathModel(Base):
    """SQLAlchemy model for conversation paths"""
    __tablename__ = 'paths'
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to conversation
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey('conversations.id'))
    
    # Path information
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # e.g., "main", "alternative-1"
    message_ids_json: Mapped[list] = mapped_column(JSON)  # Ordered list of message IDs
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Path metadata
    length: Mapped[int] = mapped_column(Integer, default=0)
    leaf_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel",
        back_populates="paths"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_path_conversation', 'conversation_id'),
        Index('idx_path_primary', 'is_primary'),
        UniqueConstraint('conversation_id', 'name', name='uq_conversation_path_name'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'name': self.name,
            'message_ids': self.message_ids_json,
            'is_primary': self.is_primary,
            'length': self.length,
            'leaf_message_id': self.leaf_message_id
        }