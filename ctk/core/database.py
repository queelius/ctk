"""
SQLAlchemy database backend for conversation storage
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from contextlib import contextmanager
import logging

from sqlalchemy import create_engine, select, and_, or_, func, text
from sqlalchemy.orm import Session, sessionmaker, scoped_session
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from .db_models import Base, ConversationModel, MessageModel, TagModel, PathModel, RoleEnum, conversation_tags
from .models import ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata

logger = logging.getLogger(__name__)


class ConversationDB:
    """SQLAlchemy-based database for storing conversations"""
    
    def __init__(self, db_path: str = "conversations.db", echo: bool = False):
        """
        Initialize database connection
        
        Args:
            db_path: Path to database file or connection string
            echo: If True, log all SQL statements
        """
        self.db_path = Path(db_path) if not db_path.startswith("postgresql://") else db_path
        
        # Create parent directory if needed
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            connection_string = f"sqlite:///{self.db_path}"
            # Use StaticPool for SQLite to avoid connection issues in tests
            self.engine = create_engine(
                connection_string,
                echo=echo,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool
            )
        else:
            # PostgreSQL or other database
            connection_string = db_path
            self.engine = create_engine(connection_string, echo=echo)
        
        # Create session factory
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        # Create tables if they don't exist
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema"""
        Base.metadata.create_all(self.engine)
        logger.info(f"Database schema initialized at {self.db_path}")
    
    @contextmanager
    def session_scope(self):
        """Provide a transactional scope for database operations"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def save_conversation(self, conversation: ConversationTree) -> str:
        """
        Save a conversation to the database
        
        Args:
            conversation: ConversationTree object to save
            
        Returns:
            The conversation ID
        """
        with self.session_scope() as session:
            # Check if conversation exists
            existing = session.get(ConversationModel, conversation.id)
            
            if existing:
                # Update existing conversation
                conv_model = existing
                # Clear existing messages and paths for full refresh
                session.query(MessageModel).filter_by(conversation_id=conversation.id).delete()
                session.query(PathModel).filter_by(conversation_id=conversation.id).delete()
            else:
                # Create new conversation
                conv_model = ConversationModel(id=conversation.id)
                session.add(conv_model)
            
            # Update conversation fields
            conv_model.title = conversation.title
            conv_model.created_at = conversation.metadata.created_at
            conv_model.updated_at = conversation.metadata.updated_at
            conv_model.version = conversation.metadata.version
            conv_model.format = conversation.metadata.format
            conv_model.source = conversation.metadata.source
            conv_model.model = conversation.metadata.model
            conv_model.project = conversation.metadata.project
            
            # Store full metadata as JSON
            conv_model.metadata_json = conversation.metadata.to_dict()
            
            # Handle tags
            self._update_tags(session, conv_model, conversation.metadata.tags)
            
            # Save messages
            for msg_id, message in conversation.message_map.items():
                msg_model = MessageModel(
                    id=message.id,
                    conversation_id=conversation.id,
                    role=RoleEnum(message.role.value),
                    content_json=message.content.to_dict(),
                    parent_id=message.parent_id,
                    timestamp=message.timestamp,
                    metadata_json=message.metadata
                )
                session.add(msg_model)
            
            # Save paths
            paths = conversation.get_all_paths()
            for idx, path in enumerate(paths):
                path_model = PathModel(
                    conversation_id=conversation.id,
                    name=f"path_{idx}",
                    message_ids_json=[msg.id for msg in path],
                    is_primary=(idx == 0),  # First path is primary
                    length=len(path),
                    leaf_message_id=path[-1].id if path else None
                )
                session.add(path_model)
            
            session.commit()
            logger.info(f"Saved conversation {conversation.id} with {len(conversation.message_map)} messages")
            
        return conversation.id
    
    def load_conversation(self, conversation_id: str) -> Optional[ConversationTree]:
        """
        Load a conversation from the database
        
        Args:
            conversation_id: ID of the conversation to load
            
        Returns:
            ConversationTree object or None if not found
        """
        with self.session_scope() as session:
            # Load conversation
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return None
            
            # Create ConversationTree
            metadata = ConversationMetadata.from_dict(conv_model.metadata_json or {})
            
            # Override with direct fields
            metadata.source = conv_model.source
            metadata.model = conv_model.model
            metadata.project = conv_model.project
            metadata.created_at = conv_model.created_at
            metadata.updated_at = conv_model.updated_at
            
            # Load tags
            metadata.tags = [tag.name for tag in conv_model.tags]
            
            conversation = ConversationTree(
                id=conv_model.id,
                title=conv_model.title,
                metadata=metadata
            )
            
            # Load messages
            messages = session.query(MessageModel).filter_by(
                conversation_id=conversation_id
            ).all()
            
            for msg_model in messages:
                content = MessageContent.from_dict(msg_model.content_json)
                message = Message(
                    id=msg_model.id,
                    role=MessageRole.from_string(msg_model.role.value),
                    content=content,
                    timestamp=msg_model.timestamp,
                    parent_id=msg_model.parent_id,
                    metadata=msg_model.metadata_json or {}
                )
                conversation.add_message(message)
            
            logger.info(f"Loaded conversation {conversation_id} with {len(messages)} messages")
            return conversation
    
    def list_conversations(self, 
                         limit: int = 100, 
                         offset: int = 0,
                         source: Optional[str] = None,
                         project: Optional[str] = None,
                         tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List conversations with optional filtering
        
        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            source: Filter by source
            project: Filter by project
            tag: Filter by tag name
            
        Returns:
            List of conversation metadata dictionaries
        """
        with self.session_scope() as session:
            query = session.query(ConversationModel)
            
            # Apply filters
            if source:
                query = query.filter(ConversationModel.source == source)
            if project:
                query = query.filter(ConversationModel.project == project)
            if tag:
                query = query.join(ConversationModel.tags).filter(TagModel.name == tag)
            
            # Order by updated_at descending
            query = query.order_by(ConversationModel.updated_at.desc())
            
            # Apply pagination
            conversations = query.offset(offset).limit(limit).all()
            
            return [conv.to_dict() for conv in conversations]
    
    def search_conversations(self, 
                           query_text: str, 
                           limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search conversations by text
        
        Args:
            query_text: Search query
            limit: Maximum number of results
            
        Returns:
            List of conversation metadata dictionaries
        """
        with self.session_scope() as session:
            # Search in conversation titles
            title_query = session.query(ConversationModel).filter(
                ConversationModel.title.ilike(f"%{query_text}%")
            )
            
            # Search in message content (JSON field search)
            # Note: This is database-specific. SQLite uses JSON extract, PostgreSQL uses JSONB operators
            if "sqlite" in str(self.engine.url):
                # SQLite JSON search
                message_query = session.query(ConversationModel).join(
                    MessageModel
                ).filter(
                    text(f"json_extract(messages.content_json, '$.text') LIKE :query")
                ).params(query=f"%{query_text}%")
            else:
                # PostgreSQL JSONB search
                message_query = session.query(ConversationModel).join(
                    MessageModel
                ).filter(
                    MessageModel.content_json['text'].astext.ilike(f"%{query_text}%")
                )
            
            # Combine queries and get unique results
            results = title_query.union(message_query).limit(limit).all()
            
            return [conv.to_dict() for conv in results]
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation and all related data
        
        Args:
            conversation_id: ID of conversation to delete
            
        Returns:
            True if deleted, False if not found
        """
        with self.session_scope() as session:
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return False
            
            # Cascading delete will handle messages and paths
            session.delete(conv_model)
            session.commit()
            logger.info(f"Deleted conversation {conversation_id}")
            return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get database statistics
        
        Returns:
            Dictionary with statistics
        """
        with self.session_scope() as session:
            total_conversations = session.query(func.count(ConversationModel.id)).scalar()
            total_messages = session.query(func.count(MessageModel.id)).scalar()
            total_tags = session.query(func.count(TagModel.id)).scalar()
            
            # Messages by role
            messages_by_role = {}
            role_counts = session.query(
                MessageModel.role,
                func.count(MessageModel.id)
            ).group_by(MessageModel.role).all()
            
            for role, count in role_counts:
                messages_by_role[role.value] = count
            
            # Conversations by source
            conversations_by_source = {}
            source_counts = session.query(
                ConversationModel.source,
                func.count(ConversationModel.id)
            ).group_by(ConversationModel.source).all()
            
            for source, count in source_counts:
                if source:
                    conversations_by_source[source] = count
            
            # Most used tags
            top_tags = session.query(
                TagModel.name,
                func.count(ConversationModel.id).label('usage_count')
            ).select_from(
                TagModel
            ).join(
                conversation_tags
            ).join(
                ConversationModel
            ).group_by(
                TagModel.name
            ).order_by(
                text('usage_count DESC')
            ).limit(10).all()
            
            return {
                'total_conversations': total_conversations,
                'total_messages': total_messages,
                'total_tags': total_tags,
                'messages_by_role': messages_by_role,
                'conversations_by_source': conversations_by_source,
                'top_tags': [{'name': name, 'count': count} for name, count in top_tags]
            }
    
    def _update_tags(self, session: Session, conv_model: ConversationModel, tag_names: List[str]):
        """Update tags for a conversation"""
        # Clear existing tags
        conv_model.tags = []
        
        # Add new tags
        for tag_name in tag_names:
            # Get or create tag
            tag = session.query(TagModel).filter_by(name=tag_name).first()
            if not tag:
                # Determine category from tag format
                category = None
                if ':' in tag_name:
                    category = tag_name.split(':')[0]
                
                tag = TagModel(name=tag_name, category=category)
                session.add(tag)
            
            conv_model.tags.append(tag)
    
    def get_all_tags(self) -> List[Dict[str, Any]]:
        """Get all tags with usage counts"""
        with self.session_scope() as session:
            tags = session.query(TagModel).all()
            return [tag.to_dict() for tag in tags]
    
    def close(self):
        """Close database connection"""
        self.Session.remove()
        self.engine.dispose()
        logger.info("Database connection closed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()