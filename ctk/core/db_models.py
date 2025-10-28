"""
SQLAlchemy database models for CTK
"""

from datetime import datetime
from typing import Optional, List
import json
import enum

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Boolean, Float,
    ForeignKey, Table, JSON, Enum, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func
from sqlalchemy.types import ARRAY


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Metadata
    version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # openai, anthropic, etc.
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # gpt-4, claude-3, etc.
    project: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Organization timestamps
    starred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Full metadata as JSON (catch-all)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    messages: Mapped[List["MessageModel"]] = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )

    paths: Mapped[List["PathModel"]] = relationship(
        "PathModel",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )

    tags: Mapped[List["TagModel"]] = relationship(
        "TagModel",
        secondary=conversation_tags,
        back_populates="conversations"
    )

    embeddings: Mapped[List["EmbeddingModel"]] = relationship(
        "EmbeddingModel",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index('idx_conv_created', 'created_at'),
        Index('idx_conv_updated', 'updated_at'),
        Index('idx_conv_source', 'source'),
        Index('idx_conv_model', 'model'),
        Index('idx_conv_project', 'project'),
        Index('idx_conv_starred', 'starred_at'),
        Index('idx_conv_pinned', 'pinned_at'),
        Index('idx_conv_archived', 'archived_at'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'version': self.version,
            'format': self.format,
            'source': self.source,
            'model': self.model,
            'project': self.project,
            'starred_at': self.starred_at.isoformat() if self.starred_at else None,
            'pinned_at': self.pinned_at.isoformat() if self.pinned_at else None,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None,
            'tags': [tag.name for tag in self.tags],
            'metadata': self.metadata_json or {},
            'message_count': len(self.messages) if self.messages else 0,
        }


class MessageModel(Base):
    """SQLAlchemy model for messages"""
    __tablename__ = 'messages'

    # Primary key (unique across all conversations)
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # Foreign key to conversation
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey('conversations.id'))

    # Message fields
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum))
    content_json: Mapped[dict] = mapped_column(JSON)  # MessageContent as JSON
    parent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # For tree structure
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Additional metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel",
        back_populates="messages"
    )

    # Indexes
    __table_args__ = (
        Index('idx_msg_conversation', 'conversation_id'),
        Index('idx_msg_parent', 'parent_id'),
        Index('idx_msg_role', 'role'),
        Index('idx_msg_timestamp', 'timestamp'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role.value if self.role else None,
            'content': self.content_json,
            'parent_id': self.parent_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'metadata': self.metadata_json or {},
        }


class TagModel(Base):
    """SQLAlchemy model for tags"""
    __tablename__ = 'tags'

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Tag fields
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    conversations: Mapped[List["ConversationModel"]] = relationship(
        "ConversationModel",
        secondary=conversation_tags,
        back_populates="tags"
    )

    # Indexes
    __table_args__ = (
        Index('idx_tag_name', 'name'),
        Index('idx_tag_category', 'category'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PathModel(Base):
    """SQLAlchemy model for conversation paths (branches)"""
    __tablename__ = 'paths'

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to conversation
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey('conversations.id'))

    # Path fields
    name: Mapped[str] = mapped_column(String)  # e.g., "path_0", "path_1"
    message_ids_json: Mapped[list] = mapped_column(JSON)  # List of message IDs in order
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)  # Is this the main path?
    length: Mapped[int] = mapped_column(Integer)  # Number of messages in path
    leaf_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Last message in path

    # Relationships
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel",
        back_populates="paths"
    )

    # Indexes
    __table_args__ = (
        Index('idx_path_conversation', 'conversation_id'),
        Index('idx_path_primary', 'is_primary'),
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
            'leaf_message_id': self.leaf_message_id,
        }


class EmbeddingModel(Base):
    """SQLAlchemy model for conversation embeddings"""
    __tablename__ = 'conversation_embeddings'

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to conversation
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey('conversations.id'))

    # Embedding configuration
    provider: Mapped[str] = mapped_column(String)  # 'ollama', 'openai', 'tfidf', etc.
    model: Mapped[str] = mapped_column(String)  # Model name (e.g., 'nomic-embed-text', 'text-embedding-3-small')
    chunking_strategy: Mapped[str] = mapped_column(String)  # 'message', 'whole', etc.
    aggregation_strategy: Mapped[str] = mapped_column(String)  # 'weighted_mean', 'mean', etc.
    aggregation_weights: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Role weights

    # Embedding data
    embedding_json: Mapped[list] = mapped_column(JSON)  # List of floats (numpy array serialized)
    dimensions: Mapped[int] = mapped_column(Integer)  # Embedding dimensionality

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel",
        back_populates="embeddings"
    )

    # Indexes and constraints
    __table_args__ = (
        Index('idx_emb_conversation', 'conversation_id'),
        Index('idx_emb_provider', 'provider'),
        Index('idx_emb_model', 'model'),
        # Unique constraint: one embedding per conversation+provider+model+chunking+aggregation
        UniqueConstraint('conversation_id', 'provider', 'model', 'chunking_strategy',
                        'aggregation_strategy', name='uq_conversation_embedding'),
    )

    @hybrid_property
    def embedding(self) -> list:
        """Get embedding as list of floats"""
        return self.embedding_json

    @embedding.setter
    def embedding(self, value):
        """Set embedding from list of floats or numpy array"""
        if hasattr(value, 'tolist'):
            # Convert numpy array to list
            self.embedding_json = value.tolist()
        else:
            self.embedding_json = value

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'provider': self.provider,
            'model': self.model,
            'chunking_strategy': self.chunking_strategy,
            'aggregation_strategy': self.aggregation_strategy,
            'aggregation_weights': self.aggregation_weights,
            'dimensions': self.dimensions,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SimilarityModel(Base):
    """SQLAlchemy model for precomputed conversation similarities"""
    __tablename__ = 'similarities'

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Conversation pairs (always store with conversation1_id < conversation2_id)
    conversation1_id: Mapped[str] = mapped_column(String, ForeignKey('conversations.id'))
    conversation2_id: Mapped[str] = mapped_column(String, ForeignKey('conversations.id'))

    # Similarity configuration
    similarity: Mapped[float] = mapped_column(Float)  # Similarity score (0.0 to 1.0)
    metric: Mapped[str] = mapped_column(String)  # 'cosine', 'euclidean', etc.
    provider: Mapped[str] = mapped_column(String)  # Embedding provider used
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Embedding model

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Relationships
    conversation1: Mapped["ConversationModel"] = relationship(
        "ConversationModel",
        foreign_keys=[conversation1_id],
        backref="similarities_as_conv1"
    )

    conversation2: Mapped["ConversationModel"] = relationship(
        "ConversationModel",
        foreign_keys=[conversation2_id],
        backref="similarities_as_conv2"
    )

    # Indexes and constraints
    __table_args__ = (
        Index('idx_sim_conv1', 'conversation1_id'),
        Index('idx_sim_conv2', 'conversation2_id'),
        Index('idx_sim_metric', 'metric'),
        Index('idx_sim_provider', 'provider'),
        # Unique constraint: one similarity per pair+metric+provider combination
        UniqueConstraint('conversation1_id', 'conversation2_id', 'metric', 'provider',
                        name='uq_conversation_similarity'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'conversation1_id': self.conversation1_id,
            'conversation2_id': self.conversation2_id,
            'similarity': self.similarity,
            'metric': self.metric,
            'provider': self.provider,
            'model': self.model,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==================== Network Analysis Models ====================

class EmbeddingSessionModel(Base):
    """SQLAlchemy model for embedding sessions (tracks embedding generation runs)"""
    __tablename__ = 'embedding_sessions'

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Embedding configuration
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chunking_strategy: Mapped[str] = mapped_column(String, nullable=False)
    aggregation_strategy: Mapped[str] = mapped_column(String, nullable=False)
    role_weights_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Filters used (JSON serialized)
    filters_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Results
    num_conversations: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    # Indexes
    __table_args__ = (
        Index('idx_emb_session_created', 'created_at'),
        Index('idx_emb_session_current', 'is_current'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'provider': self.provider,
            'model': self.model,
            'chunking_strategy': self.chunking_strategy,
            'aggregation_strategy': self.aggregation_strategy,
            'role_weights': self.role_weights_json,
            'filters': self.filters_json,
            'num_conversations': self.num_conversations,
            'is_current': self.is_current,
        }


class CurrentGraphModel(Base):
    """SQLAlchemy model for current conversation graph metadata"""
    __tablename__ = 'current_graph'

    # Primary key (only one row allowed)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Embedding session reference
    embedding_session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('embedding_sessions.id'), nullable=True
    )

    # Graph build parameters
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    max_links_per_node: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # File reference
    graph_file_path: Mapped[str] = mapped_column(String, nullable=False)

    # Global metrics (cached)
    num_nodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_edges: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_degree: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_components: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    giant_component_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_path_length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    diameter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    global_clustering: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_local_clustering: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Community detection (if run)
    communities_algorithm: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    num_communities: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    modularity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationship
    embedding_session: Mapped[Optional["EmbeddingSessionModel"]] = relationship(
        "EmbeddingSessionModel", foreign_keys=[embedding_session_id]
    )

    # Constraint: only one row allowed
    __table_args__ = (
        CheckConstraint('id = 1', name='single_row_constraint'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'embedding_session_id': self.embedding_session_id,
            'threshold': self.threshold,
            'max_links_per_node': self.max_links_per_node,
            'graph_file_path': self.graph_file_path,
            'num_nodes': self.num_nodes,
            'num_edges': self.num_edges,
            'density': self.density,
            'avg_degree': self.avg_degree,
            'num_components': self.num_components,
            'giant_component_size': self.giant_component_size,
            'avg_path_length': self.avg_path_length,
            'diameter': self.diameter,
            'global_clustering': self.global_clustering,
            'avg_local_clustering': self.avg_local_clustering,
            'communities_algorithm': self.communities_algorithm,
            'num_communities': self.num_communities,
            'modularity': self.modularity,
        }


class CurrentCommunityModel(Base):
    """SQLAlchemy model for communities in current graph"""
    __tablename__ = 'current_communities'

    # Primary key
    community_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Algorithm used
    algorithm: Mapped[str] = mapped_column(String, nullable=False)

    # Community properties
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    internal_edges: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    external_edges: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Topics (TF-IDF extracted)
    topics_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Members
    conversation_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'community_id': self.community_id,
            'algorithm': self.algorithm,
            'size': self.size,
            'internal_edges': self.internal_edges,
            'external_edges': self.external_edges,
            'density': self.density,
            'topics': self.topics_json,
            'conversation_ids': self.conversation_ids_json,
        }


class CurrentNodeMetricsModel(Base):
    """SQLAlchemy model for node-level metrics in current graph"""
    __tablename__ = 'current_node_metrics'

    # Primary key
    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)

    # Basic metrics
    degree: Mapped[int] = mapped_column(Integer, nullable=False)
    clustering_coefficient: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Centrality measures (computed lazily)
    degree_centrality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    betweenness_centrality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    closeness_centrality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eigenvector_centrality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pagerank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Community membership
    community_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Index
    __table_args__ = (
        Index('idx_node_community', 'community_id'),
        Index('idx_node_degree', 'degree'),
        Index('idx_node_betweenness', 'betweenness_centrality'),
        Index('idx_node_pagerank', 'pagerank'),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'conversation_id': self.conversation_id,
            'degree': self.degree,
            'clustering_coefficient': self.clustering_coefficient,
            'degree_centrality': self.degree_centrality,
            'betweenness_centrality': self.betweenness_centrality,
            'closeness_centrality': self.closeness_centrality,
            'eigenvector_centrality': self.eigenvector_centrality,
            'pagerank': self.pagerank,
            'community_id': self.community_id,
        }
