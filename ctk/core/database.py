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
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError

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
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError) as e:
                raise ValueError(f"Cannot create database directory: {e}") from e
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
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Database integrity error: {e}")
            raise
        except OperationalError as e:
            session.rollback()
            logger.error(f"Database operational error: {e}")
            raise
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error in database transaction: {e}")
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
            
            # Save messages with unique IDs
            # Create a mapping of old IDs to new IDs
            id_mapping = {}
            for msg_id, message in conversation.message_map.items():
                # Create unique ID by combining conversation ID and message ID
                unique_id = f"{conversation.id}_{message.id}"
                id_mapping[message.id] = unique_id

                # Map parent_id to new unique ID
                unique_parent_id = None
                if message.parent_id:
                    unique_parent_id = f"{conversation.id}_{message.parent_id}"

                # Check if this message already exists
                existing_msg = session.query(MessageModel).filter_by(id=unique_id).first()
                if not existing_msg:
                    msg_model = MessageModel(
                        id=unique_id,
                        conversation_id=conversation.id,
                        role=RoleEnum(message.role.value),
                        content_json=message.content.to_dict(),
                        parent_id=unique_parent_id,
                        timestamp=message.timestamp,
                        metadata_json=message.metadata
                    )
                    session.add(msg_model)
            
            # Save paths with updated message IDs
            paths = conversation.get_all_paths()
            for idx, path in enumerate(paths):
                # Map message IDs to their unique database IDs
                unique_message_ids = [f"{conversation.id}_{msg.id}" for msg in path]
                path_model = PathModel(
                    conversation_id=conversation.id,
                    name=f"path_{idx}",
                    message_ids_json=unique_message_ids,
                    is_primary=(idx == 0),  # First path is primary
                    length=len(path),
                    leaf_message_id=f"{conversation.id}_{path[-1].id}" if path else None
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
            
            # Load messages and strip conversation ID prefix
            messages = session.query(MessageModel).filter_by(
                conversation_id=conversation_id
            ).all()

            # Create mapping from unique IDs to original IDs
            id_mapping = {}
            for msg_model in messages:
                # Strip conversation ID prefix to get original message ID
                original_id = msg_model.id
                if original_id.startswith(f"{conversation_id}_"):
                    original_id = original_id[len(conversation_id) + 1:]
                id_mapping[msg_model.id] = original_id

            for msg_model in messages:
                content = MessageContent.from_dict(msg_model.content_json)

                # Get original IDs
                original_id = id_mapping.get(msg_model.id, msg_model.id)
                original_parent_id = None
                if msg_model.parent_id:
                    original_parent_id = id_mapping.get(msg_model.parent_id, msg_model.parent_id)

                message = Message(
                    id=original_id,
                    role=MessageRole.from_string(msg_model.role.value),
                    content=content,
                    timestamp=msg_model.timestamp,
                    parent_id=original_parent_id,
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
                           query_text: str = None,
                           limit: int = 100,
                           offset: int = 0,
                           title_only: bool = False,
                           content_only: bool = False,
                           date_from: datetime = None,
                           date_to: datetime = None,
                           source: str = None,
                           model: str = None,
                           tags: List[str] = None,
                           min_messages: int = None,
                           max_messages: int = None,
                           has_branches: bool = None,
                           order_by: str = 'updated_at',
                           ascending: bool = False) -> List[Dict[str, Any]]:
        """
        Advanced search with multiple filters

        Args:
            query_text: Text to search for
            limit: Maximum number of results
            offset: Number of results to skip
            title_only: Search only in titles
            content_only: Search only in message content
            date_from: Filter by created after date
            date_to: Filter by created before date
            source: Filter by source platform
            model: Filter by model used
            tags: Filter by tags (any match)
            min_messages: Minimum number of messages
            max_messages: Maximum number of messages
            has_branches: Filter by branching conversations
            order_by: Field to order by (created_at, updated_at, title, message_count)
            ascending: Sort order

        Returns:
            List of conversation metadata dictionaries
        """
        with self.session_scope() as session:
            # Base query with message count
            query = session.query(
                ConversationModel,
                func.count(MessageModel.id).label('message_count')
            ).outerjoin(MessageModel)

            # Text search
            if query_text:
                if title_only:
                    query = query.filter(
                        ConversationModel.title.ilike(f"%{query_text}%")
                    )
                elif content_only:
                    if "sqlite" in str(self.engine.url):
                        query = query.filter(
                            text("json_extract(messages.content_json, '$.text') LIKE :query")
                        ).params(query=f"%{query_text}%")
                    else:
                        query = query.filter(
                            MessageModel.content_json['text'].astext.ilike(f"%{query_text}%")
                        )
                else:
                    # Search both title and content
                    if "sqlite" in str(self.engine.url):
                        query = query.filter(
                            or_(
                                ConversationModel.title.ilike(f"%{query_text}%"),
                                text("json_extract(messages.content_json, '$.text') LIKE :query")
                            )
                        ).params(query=f"%{query_text}%")
                    else:
                        query = query.filter(
                            or_(
                                ConversationModel.title.ilike(f"%{query_text}%"),
                                MessageModel.content_json['text'].astext.ilike(f"%{query_text}%")
                            )
                        )

            # Date filters
            if date_from:
                query = query.filter(ConversationModel.created_at >= date_from)
            if date_to:
                query = query.filter(ConversationModel.created_at <= date_to)

            # Source and model filters
            if source:
                query = query.filter(ConversationModel.source == source)
            if model:
                query = query.filter(ConversationModel.model.ilike(f"%{model}%"))

            # Tag filters
            if tags:
                query = query.join(ConversationModel.tags).filter(
                    TagModel.name.in_(tags)
                )

            # Group by for message count
            query = query.group_by(ConversationModel.id)

            # Message count filters
            if min_messages is not None:
                query = query.having(func.count(MessageModel.id) >= min_messages)
            if max_messages is not None:
                query = query.having(func.count(MessageModel.id) <= max_messages)

            # Branching filter (requires subquery)
            if has_branches is not None:
                branch_subquery = session.query(
                    PathModel.conversation_id,
                    func.count(PathModel.id).label('path_count')
                ).group_by(PathModel.conversation_id).subquery()

                query = query.outerjoin(
                    branch_subquery,
                    ConversationModel.id == branch_subquery.c.conversation_id
                )

                if has_branches:
                    query = query.filter(branch_subquery.c.path_count > 1)
                else:
                    query = query.filter(
                        or_(branch_subquery.c.path_count == 1,
                            branch_subquery.c.path_count.is_(None))
                    )

            # Ordering
            if order_by == 'message_count':
                # Special case for message count ordering
                if ascending:
                    query = query.order_by(text('message_count ASC'))
                else:
                    query = query.order_by(text('message_count DESC'))
            else:
                order_field = {
                    'created_at': ConversationModel.created_at,
                    'updated_at': ConversationModel.updated_at,
                    'title': ConversationModel.title,
                }.get(order_by, ConversationModel.updated_at)

                if ascending:
                    query = query.order_by(order_field.asc())
                else:
                    query = query.order_by(order_field.desc())

            # Apply pagination
            results = query.offset(offset).limit(limit).all()

            # Convert to dictionaries
            output = []
            for conv, msg_count in results:
                conv_dict = conv.to_dict()
                conv_dict['message_count'] = msg_count
                output.append(conv_dict)

            return output
    
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

        # Deduplicate tag names
        unique_tag_names = list(set(tag_names))

        # Add new tags
        for tag_name in unique_tag_names:
            # Get or create tag
            tag = session.query(TagModel).filter_by(name=tag_name).first()
            if not tag:
                # Determine category from tag format
                category = None
                if ':' in tag_name:
                    category = tag_name.split(':')[0]

                tag = TagModel(name=tag_name, category=category)
                session.add(tag)

            # Only add if not already in tags (shouldn't happen after clear, but safe)
            if tag not in conv_model.tags:
                conv_model.tags.append(tag)
    
    def get_all_tags(self, with_counts: bool = True) -> List[Dict[str, Any]]:
        """Get all tags with usage counts"""
        with self.session_scope() as session:
            if with_counts:
                # Get tags with usage counts - proper join sequence
                results = session.query(
                    TagModel,
                    func.count(ConversationModel.id).label('usage_count')
                ).select_from(TagModel).outerjoin(
                    conversation_tags,
                    TagModel.id == conversation_tags.c.tag_id
                ).outerjoin(
                    ConversationModel,
                    conversation_tags.c.conversation_id == ConversationModel.id
                ).group_by(TagModel.id).all()

                tags = []
                for tag, count in results:
                    tag_dict = tag.to_dict()
                    tag_dict['usage_count'] = count
                    tags.append(tag_dict)
                return tags
            else:
                tags = session.query(TagModel).all()
                return [tag.to_dict() for tag in tags]

    def get_models(self) -> List[Dict[str, int]]:
        """Get all unique models with conversation counts"""
        with self.session_scope() as session:
            results = session.query(
                ConversationModel.model,
                func.count(ConversationModel.id).label('count')
            ).filter(
                ConversationModel.model.isnot(None)
            ).group_by(
                ConversationModel.model
            ).order_by(
                text('count DESC')
            ).all()

            return [{'model': model, 'count': count} for model, count in results]

    def get_sources(self) -> List[Dict[str, int]]:
        """Get all unique sources with conversation counts"""
        with self.session_scope() as session:
            results = session.query(
                ConversationModel.source,
                func.count(ConversationModel.id).label('count')
            ).filter(
                ConversationModel.source.isnot(None)
            ).group_by(
                ConversationModel.source
            ).order_by(
                text('count DESC')
            ).all()

            return [{'source': source, 'count': count} for source, count in results]

    def get_conversation_timeline(self,
                                  granularity: str = 'day',
                                  limit: int = 30) -> List[Dict[str, Any]]:
        """Get conversation counts over time"""
        with self.session_scope() as session:
            # SQLite-specific date formatting
            if "sqlite" in str(self.engine.url):
                if granularity == 'day':
                    date_format = "date(created_at)"
                elif granularity == 'week':
                    date_format = "strftime('%Y-%W', created_at)"
                elif granularity == 'month':
                    date_format = "strftime('%Y-%m', created_at)"
                elif granularity == 'year':
                    date_format = "strftime('%Y', created_at)"
                else:
                    date_format = "date(created_at)"

                results = session.execute(
                    text(f"""
                        SELECT {date_format} as period, COUNT(id) as count
                        FROM conversations
                        GROUP BY {date_format}
                        ORDER BY {date_format} DESC
                        LIMIT :limit
                    """),
                    {"limit": limit}
                ).fetchall()
            else:
                # PostgreSQL date formatting
                if granularity == 'day':
                    date_trunc = func.date_trunc('day', ConversationModel.created_at)
                elif granularity == 'week':
                    date_trunc = func.date_trunc('week', ConversationModel.created_at)
                elif granularity == 'month':
                    date_trunc = func.date_trunc('month', ConversationModel.created_at)
                elif granularity == 'year':
                    date_trunc = func.date_trunc('year', ConversationModel.created_at)
                else:
                    date_trunc = func.date_trunc('day', ConversationModel.created_at)

                results = session.query(
                    date_trunc.label('period'),
                    func.count(ConversationModel.id).label('count')
                ).group_by(
                    date_trunc
                ).order_by(
                    date_trunc.desc()
                ).limit(limit).all()

            return [{'period': str(period), 'count': count} for period, count in results]
    
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