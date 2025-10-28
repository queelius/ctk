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

from .db_models import (
    Base, ConversationModel, MessageModel, TagModel, PathModel,
    EmbeddingModel, SimilarityModel, RoleEnum, conversation_tags,
    EmbeddingSessionModel, CurrentGraphModel, CurrentCommunityModel, CurrentNodeMetricsModel
)
from .models import (
    ConversationTree,
    ConversationSummary,
    Message,
    MessageContent,
    MessageRole,
    ConversationMetadata
)

logger = logging.getLogger(__name__)


class ConversationDB:
    """SQLAlchemy-based database for storing conversations"""

    def __init__(self, db_path: str = "conversations", echo: bool = False):
        """
        Initialize database connection

        Args:
            db_path: Path to database directory (will contain conversations.db and media/)
            echo: If True, log all SQL statements
        """
        # Handle directory structure
        if db_path.startswith("postgresql://"):
            # PostgreSQL - use as-is
            self.db_dir = None
            self.db_path = db_path
            connection_string = db_path
            self.engine = create_engine(connection_string, echo=echo)
        else:
            # SQLite - use directory structure
            self.db_dir = Path(db_path)
            self.db_path = self.db_dir / "conversations.db"
            self.media_dir = self.db_dir / "media"

            # Create directory structure
            try:
                self.db_dir.mkdir(parents=True, exist_ok=True)
                self.media_dir.mkdir(exist_ok=True)
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
            metadata.starred_at = conv_model.starred_at
            metadata.pinned_at = conv_model.pinned_at
            metadata.archived_at = conv_model.archived_at

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
                         limit: Optional[int] = None,
                         offset: int = 0,
                         source: Optional[str] = None,
                         project: Optional[str] = None,
                         tag: Optional[str] = None,
                         tags: Optional[List[str]] = None,
                         model: Optional[str] = None,
                         archived: Optional[bool] = None,
                         starred: Optional[bool] = None,
                         pinned: Optional[bool] = None,
                         include_archived: bool = False) -> List[ConversationSummary]:
        """
        List conversations with optional filtering

        Args:
            limit: Maximum number of results (None = all)
            offset: Number of results to skip
            source: Filter by source
            project: Filter by project
            tag: Filter by single tag name (deprecated, use tags)
            tags: Filter by list of tags (any match)
            model: Filter by model
            archived: If True, show only archived; if False, only non-archived; if None, both
            starred: If True, show only starred; if False, only non-starred; if None, both
            pinned: If True, show only pinned; if False, only non-pinned; if None, both
            include_archived: If True, include archived conversations (default: exclude)

        Returns:
            List of ConversationSummary objects
        """
        with self.session_scope() as session:
            query = session.query(ConversationModel)

            # Apply filters
            if source:
                query = query.filter(ConversationModel.source == source)
            if project:
                query = query.filter(ConversationModel.project == project)
            if model:
                query = query.filter(ConversationModel.model == model)
            if tag:
                query = query.join(ConversationModel.tags).filter(TagModel.name == tag)
            if tags:
                # Match any of the tags
                query = query.join(ConversationModel.tags).filter(TagModel.name.in_(tags))

            # Archive filtering
            if not include_archived and archived is None:
                # Default: exclude archived
                query = query.filter(ConversationModel.archived_at.is_(None))
            elif archived is True:
                # Only archived
                query = query.filter(ConversationModel.archived_at.isnot(None))
            elif archived is False:
                # Only non-archived
                query = query.filter(ConversationModel.archived_at.is_(None))

            # Star filtering
            if starred is True:
                query = query.filter(ConversationModel.starred_at.isnot(None))
            elif starred is False:
                query = query.filter(ConversationModel.starred_at.is_(None))

            # Pin filtering
            if pinned is True:
                query = query.filter(ConversationModel.pinned_at.isnot(None))
            elif pinned is False:
                query = query.filter(ConversationModel.pinned_at.is_(None))

            # Order by: pinned first, then updated_at descending
            query = query.order_by(
                ConversationModel.pinned_at.desc().nullslast(),
                ConversationModel.updated_at.desc()
            )

            # Apply pagination
            if limit is not None:
                query = query.limit(limit)
            conversations = query.offset(offset).all()

            return [ConversationSummary.from_dict(conv.to_dict()) for conv in conversations]
    
    def search_conversations(self,
                           query_text: str = None,
                           limit: int = 100,
                           offset: int = 0,
                           title_only: bool = False,
                           content_only: bool = False,
                           date_from: datetime = None,
                           date_to: datetime = None,
                           source: str = None,
                           project: str = None,
                           model: str = None,
                           tags: List[str] = None,
                           min_messages: int = None,
                           max_messages: int = None,
                           has_branches: bool = None,
                           archived: Optional[bool] = None,
                           starred: Optional[bool] = None,
                           pinned: Optional[bool] = None,
                           include_archived: bool = False,
                           order_by: str = 'updated_at',
                           ascending: bool = False) -> List[ConversationSummary]:
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
            project: Filter by project name
            model: Filter by model used
            tags: Filter by tags (any match)
            min_messages: Minimum number of messages
            max_messages: Maximum number of messages
            has_branches: Filter by branching conversations
            archived: If True, show only archived; if False, only non-archived; if None, both
            starred: If True, show only starred; if False, only non-starred; if None, both
            pinned: If True, show only pinned; if False, only non-pinned; if None, both
            include_archived: If True, include archived conversations (default: exclude)
            order_by: Field to order by (created_at, updated_at, title, message_count)
            ascending: Sort order

        Returns:
            List of ConversationSummary objects
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

            # Source, project, and model filters
            if source:
                query = query.filter(ConversationModel.source == source)
            if project:
                query = query.filter(ConversationModel.project == project)
            if model:
                query = query.filter(ConversationModel.model.ilike(f"%{model}%"))

            # Tag filters
            if tags:
                query = query.join(ConversationModel.tags).filter(
                    TagModel.name.in_(tags)
                )

            # Archive filtering
            if not include_archived and archived is None:
                # Default: exclude archived
                query = query.filter(ConversationModel.archived_at.is_(None))
            elif archived is True:
                # Only archived
                query = query.filter(ConversationModel.archived_at.isnot(None))
            elif archived is False:
                # Only non-archived
                query = query.filter(ConversationModel.archived_at.is_(None))

            # Star filtering
            if starred is True:
                query = query.filter(ConversationModel.starred_at.isnot(None))
            elif starred is False:
                query = query.filter(ConversationModel.starred_at.is_(None))

            # Pin filtering
            if pinned is True:
                query = query.filter(ConversationModel.pinned_at.isnot(None))
            elif pinned is False:
                query = query.filter(ConversationModel.pinned_at.is_(None))

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

            # Convert to ConversationSummary objects
            output = []
            for conv, msg_count in results:
                conv_dict = conv.to_dict()
                conv_dict['message_count'] = msg_count
                output.append(ConversationSummary.from_dict(conv_dict))

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

    def archive_conversation(self, conversation_id: str, archive: bool = True) -> bool:
        """
        Archive or unarchive a conversation

        Args:
            conversation_id: ID of conversation
            archive: True to archive, False to unarchive

        Returns:
            True if successful, False if not found
        """
        with self.session_scope() as session:
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return False

            if archive:
                conv_model.archived_at = datetime.now()
                logger.info(f"Archived conversation {conversation_id}")
            else:
                conv_model.archived_at = None
                logger.info(f"Unarchived conversation {conversation_id}")

            session.commit()
            return True

    def star_conversation(self, conversation_id: str, star: bool = True) -> bool:
        """
        Star or unstar a conversation

        Args:
            conversation_id: ID of conversation
            star: True to star, False to unstar

        Returns:
            True if successful, False if not found
        """
        with self.session_scope() as session:
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return False

            if star:
                conv_model.starred_at = datetime.now()
                logger.info(f"Starred conversation {conversation_id}")
            else:
                conv_model.starred_at = None
                logger.info(f"Unstarred conversation {conversation_id}")

            session.commit()
            return True

    def pin_conversation(self, conversation_id: str, pin: bool = True) -> bool:
        """
        Pin or unpin a conversation

        Args:
            conversation_id: ID of conversation
            pin: True to pin, False to unpin

        Returns:
            True if successful, False if not found
        """
        with self.session_scope() as session:
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return False

            if pin:
                conv_model.pinned_at = datetime.now()
                logger.info(f"Pinned conversation {conversation_id}")
            else:
                conv_model.pinned_at = None
                logger.info(f"Unpinned conversation {conversation_id}")

            session.commit()
            return True

    def duplicate_conversation(self, conversation_id: str, new_title: Optional[str] = None) -> Optional[str]:
        """
        Duplicate a conversation

        Args:
            conversation_id: ID of conversation to duplicate
            new_title: Optional new title (defaults to "Copy of <original title>")

        Returns:
            ID of new conversation, or None if original not found
        """
        # Load original conversation
        original = self.load_conversation(conversation_id)
        if not original:
            return None

        # Create new conversation with new ID
        import uuid
        new_id = str(uuid.uuid4())

        # Update title
        if not new_title:
            new_title = f"Copy of {original.title}"
        original.title = new_title

        # Update ID
        original.id = new_id

        # Generate new IDs for all messages to avoid conflicts
        id_map = {}  # old_id -> new_id
        for old_id in original.message_map.keys():
            id_map[old_id] = str(uuid.uuid4())

        # Update message IDs and parent_ids
        new_message_map = {}
        for old_id, msg in original.message_map.items():
            msg.id = id_map[old_id]
            if msg.parent_id:
                msg.parent_id = id_map[msg.parent_id]
            new_message_map[msg.id] = msg

        original.message_map = new_message_map

        # Save duplicated conversation
        self.save_conversation(original)
        logger.info(f"Duplicated conversation {conversation_id} -> {new_id}")

        return new_id

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

    def add_tags(self, conversation_id: str, tag_names: List[str]) -> bool:
        """
        Add tags to a conversation (appends to existing tags)

        Args:
            conversation_id: ID of conversation
            tag_names: List of tag names to add

        Returns:
            True if successful, False otherwise
        """
        with self.session_scope() as session:
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return False

            # Get existing tag names
            existing_tags = {tag.name for tag in conv_model.tags}

            # Add new tags that don't exist
            for tag_name in tag_names:
                if tag_name not in existing_tags:
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

            conv_model.updated_at = datetime.now()
            session.commit()
            return True

    def remove_tag(self, conversation_id: str, tag_name: str) -> bool:
        """
        Remove a tag from a conversation.

        Args:
            conversation_id: ID of conversation
            tag_name: Tag name to remove

        Returns:
            True if successful, False if conversation or tag not found
        """
        with self.session_scope() as session:
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return False

            # Find the tag
            tag = session.query(TagModel).filter_by(name=tag_name).first()
            if not tag:
                return False

            # Remove tag from conversation if present
            if tag in conv_model.tags:
                conv_model.tags.remove(tag)
                conv_model.updated_at = datetime.now()
                session.commit()
                return True

            return False

    def duplicate_conversation(self, conversation_id: str) -> Optional[str]:
        """
        Deep copy a conversation with a new auto-generated UUID.

        Args:
            conversation_id: ID of conversation to duplicate

        Returns:
            New conversation ID if successful, None otherwise
        """
        with self.session_scope() as session:
            # Get original conversation
            original = session.get(ConversationModel, conversation_id)
            if not original:
                return None

            # Generate new UUID
            import uuid
            new_id = str(uuid.uuid4())

            # Create new conversation model
            new_conv = ConversationModel(
                id=new_id,
                title=f"{original.title} (copy)" if original.title else None,
                source=original.source,
                model=original.model,
                project=original.project,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                starred=False,  # Don't copy starred status
                pinned=False,   # Don't copy pinned status
                archived=False, # Don't copy archived status
                starred_at=None,
                pinned_at=None,
                archived_at=None
            )

            # Copy all messages
            for msg in original.messages:
                new_msg = MessageModel(
                    id=str(uuid.uuid4()),
                    conversation_id=new_id,
                    role=msg.role,
                    content=msg.content,
                    parent_id=msg.parent_id,
                    timestamp=msg.timestamp,
                    model=msg.model,
                    metadata_=msg.metadata_
                )
                new_conv.messages.append(new_msg)

            # Copy all tags
            for tag in original.tags:
                new_conv.tags.append(tag)

            session.add(new_conv)
            session.commit()

            return new_id

    def update_conversation_metadata(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        project: Optional[str] = None,
        source: Optional[str] = None,
        model: Optional[str] = None
    ) -> bool:
        """
        Update conversation metadata fields

        Args:
            conversation_id: ID of conversation
            title: New title (optional)
            project: New project name (optional)
            source: New source (optional)
            model: New model (optional)

        Returns:
            True if successful, False otherwise
        """
        with self.session_scope() as session:
            conv_model = session.get(ConversationModel, conversation_id)
            if not conv_model:
                return False

            if title is not None:
                conv_model.title = title
            if project is not None:
                conv_model.project = project
            if source is not None:
                conv_model.source = source
            if model is not None:
                conv_model.model = model

            conv_model.updated_at = datetime.now()
            session.commit()
            return True

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

    # ==================== Embedding Methods ====================

    def save_embedding(
        self,
        conversation_id: str,
        embedding: List[float],
        model: str,
        provider: str,
        chunking_strategy: str = 'message',
        aggregation_strategy: str = 'weighted_mean',
        aggregation_weights: Optional[Dict[str, float]] = None
    ) -> int:
        """
        Save or update embedding for a conversation.

        Args:
            conversation_id: Conversation ID
            embedding: Embedding vector
            model: Embedding model name
            provider: Provider name (e.g., 'ollama')
            chunking_strategy: How text was chunked
            aggregation_strategy: How chunks were aggregated
            aggregation_weights: Weights used for aggregation

        Returns:
            Embedding ID

        Raises:
            ValueError: If conversation not found
            SQLAlchemyError: On database errors
        """
        with self.session_scope() as session:
            # Verify conversation exists
            conv = session.get(ConversationModel, conversation_id)
            if not conv:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Check if embedding already exists
            existing = session.query(EmbeddingModel).filter(
                and_(
                    EmbeddingModel.conversation_id == conversation_id,
                    EmbeddingModel.model == model,
                    EmbeddingModel.provider == provider,
                    EmbeddingModel.chunking_strategy == chunking_strategy,
                    EmbeddingModel.aggregation_strategy == aggregation_strategy
                )
            ).first()

            if existing:
                # Update existing embedding
                existing.embedding = embedding
                existing.dimensions = len(embedding)
                existing.aggregation_weights = aggregation_weights
                session.flush()
                logger.info(f"Updated embedding for conversation {conversation_id}")
                return existing.id
            else:
                # Create new embedding
                emb = EmbeddingModel(
                    conversation_id=conversation_id,
                    model=model,
                    provider=provider,
                    chunking_strategy=chunking_strategy,
                    aggregation_strategy=aggregation_strategy,
                    aggregation_weights=aggregation_weights,
                    embedding=embedding,
                    dimensions=len(embedding)
                )
                session.add(emb)
                session.flush()
                logger.info(f"Created embedding for conversation {conversation_id}")
                return emb.id

    def get_embedding(
        self,
        conversation_id: str,
        model: str,
        provider: str,
        chunking_strategy: str = 'message',
        aggregation_strategy: str = 'weighted_mean'
    ) -> Optional[List[float]]:
        """
        Get cached embedding for a conversation.

        Args:
            conversation_id: Conversation ID
            model: Embedding model name
            provider: Provider name
            chunking_strategy: Chunking strategy used
            aggregation_strategy: Aggregation strategy used

        Returns:
            Embedding vector or None if not found
        """
        with self.session_scope() as session:
            emb = session.query(EmbeddingModel).filter(
                and_(
                    EmbeddingModel.conversation_id == conversation_id,
                    EmbeddingModel.model == model,
                    EmbeddingModel.provider == provider,
                    EmbeddingModel.chunking_strategy == chunking_strategy,
                    EmbeddingModel.aggregation_strategy == aggregation_strategy
                )
            ).first()

            return emb.embedding if emb else None

    def get_all_embeddings(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all embeddings, optionally filtered by model/provider.

        Args:
            model: Filter by model name
            provider: Filter by provider name

        Returns:
            List of embedding dictionaries with conversation_id and embedding
        """
        with self.session_scope() as session:
            query = session.query(EmbeddingModel)

            if model:
                query = query.filter(EmbeddingModel.model == model)
            if provider:
                query = query.filter(EmbeddingModel.provider == provider)

            embeddings = query.all()

            return [{
                'id': emb.id,
                'conversation_id': emb.conversation_id,
                'embedding': emb.embedding,
                'model': emb.model,
                'provider': emb.provider,
                'chunking_strategy': emb.chunking_strategy,
                'aggregation_strategy': emb.aggregation_strategy,
                'dimensions': emb.dimensions,
                'created_at': emb.created_at
            } for emb in embeddings]

    def delete_embeddings(
        self,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None
    ) -> int:
        """
        Delete embeddings matching criteria.

        Args:
            conversation_id: Delete embeddings for this conversation
            model: Delete embeddings from this model
            provider: Delete embeddings from this provider

        Returns:
            Number of embeddings deleted
        """
        with self.session_scope() as session:
            query = session.query(EmbeddingModel)

            if conversation_id:
                query = query.filter(EmbeddingModel.conversation_id == conversation_id)
            if model:
                query = query.filter(EmbeddingModel.model == model)
            if provider:
                query = query.filter(EmbeddingModel.provider == provider)

            count = query.delete()
            logger.info(f"Deleted {count} embeddings")
            return count

    # ==================== Similarity Methods ====================

    def save_similarity(
        self,
        conversation1_id: str,
        conversation2_id: str,
        similarity: float,
        metric: str,
        provider: str,
        model: Optional[str] = None
    ):
        """
        Save similarity between two conversations.

        Args:
            conversation1_id: First conversation ID
            conversation2_id: Second conversation ID
            similarity: Similarity score (0.0 to 1.0)
            metric: Similarity metric used ('cosine', 'euclidean', etc.)
            provider: Embedding provider used
            model: Optional embedding model name
        """
        # Ensure conversation1_id < conversation2_id for consistency
        if conversation1_id > conversation2_id:
            conversation1_id, conversation2_id = conversation2_id, conversation1_id

        with self.session_scope() as session:
            # Check if similarity already exists
            existing = session.query(SimilarityModel).filter(
                and_(
                    SimilarityModel.conversation1_id == conversation1_id,
                    SimilarityModel.conversation2_id == conversation2_id,
                    SimilarityModel.metric == metric,
                    SimilarityModel.provider == provider
                )
            ).first()

            if existing:
                # Update existing similarity
                existing.similarity = similarity
                existing.model = model
                logger.debug(f"Updated similarity between {conversation1_id} and {conversation2_id}")
            else:
                # Create new similarity
                sim_model = SimilarityModel(
                    conversation1_id=conversation1_id,
                    conversation2_id=conversation2_id,
                    similarity=similarity,
                    metric=metric,
                    provider=provider,
                    model=model
                )
                session.add(sim_model)
                logger.debug(f"Saved similarity between {conversation1_id} and {conversation2_id}")

    def get_similarity(
        self,
        conversation1_id: str,
        conversation2_id: str,
        metric: str,
        provider: str
    ) -> Optional[float]:
        """
        Get cached similarity between two conversations.

        Args:
            conversation1_id: First conversation ID
            conversation2_id: Second conversation ID
            metric: Similarity metric
            provider: Embedding provider

        Returns:
            Similarity score or None if not cached
        """
        # Ensure conversation1_id < conversation2_id for consistency
        if conversation1_id > conversation2_id:
            conversation1_id, conversation2_id = conversation2_id, conversation1_id

        with self.session_scope() as session:
            sim = session.query(SimilarityModel).filter(
                and_(
                    SimilarityModel.conversation1_id == conversation1_id,
                    SimilarityModel.conversation2_id == conversation2_id,
                    SimilarityModel.metric == metric,
                    SimilarityModel.provider == provider
                )
            ).first()

            return sim.similarity if sim else None

    def get_similar_conversations(
        self,
        conversation_id: str,
        metric: str = "cosine",
        provider: Optional[str] = None,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get conversations similar to a given conversation.

        Args:
            conversation_id: Query conversation ID
            metric: Similarity metric to use
            provider: Filter by provider (if None, use any)
            top_k: Return top K most similar
            threshold: Minimum similarity threshold

        Returns:
            List of dicts with keys: conversation_id, similarity, metric, provider
        """
        with self.session_scope() as session:
            # Query similarities where conversation is either conv1 or conv2
            query = session.query(SimilarityModel).filter(
                and_(
                    SimilarityModel.metric == metric,
                    or_(
                        SimilarityModel.conversation1_id == conversation_id,
                        SimilarityModel.conversation2_id == conversation_id
                    )
                )
            )

            if provider:
                query = query.filter(SimilarityModel.provider == provider)

            if threshold:
                query = query.filter(SimilarityModel.similarity >= threshold)

            # Order by similarity descending
            query = query.order_by(SimilarityModel.similarity.desc())

            if top_k:
                query = query.limit(top_k)

            results = query.all()

            # Extract the "other" conversation ID
            similar = []
            for sim in results:
                other_id = (
                    sim.conversation2_id
                    if sim.conversation1_id == conversation_id
                    else sim.conversation1_id
                )
                similar.append({
                    'conversation_id': other_id,
                    'similarity': sim.similarity,
                    'metric': sim.metric,
                    'provider': sim.provider,
                    'model': sim.model
                })

            return similar

    def delete_similarities(
        self,
        conversation_id: Optional[str] = None,
        metric: Optional[str] = None,
        provider: Optional[str] = None
    ) -> int:
        """
        Delete similarities matching criteria.

        Args:
            conversation_id: Delete similarities involving this conversation
            metric: Delete similarities computed with this metric
            provider: Delete similarities from this provider

        Returns:
            Number of similarities deleted
        """
        with self.session_scope() as session:
            query = session.query(SimilarityModel)

            if conversation_id:
                query = query.filter(
                    or_(
                        SimilarityModel.conversation1_id == conversation_id,
                        SimilarityModel.conversation2_id == conversation_id
                    )
                )
            if metric:
                query = query.filter(SimilarityModel.metric == metric)
            if provider:
                query = query.filter(SimilarityModel.provider == provider)

            count = query.delete()
            logger.info(f"Deleted {count} similarities")
            return count

    # ==================== Embedding Session Methods ====================

    def save_embedding_session(
        self,
        provider: str,
        chunking_strategy: str,
        aggregation_strategy: str,
        num_conversations: int,
        model: Optional[str] = None,
        role_weights: Optional[Dict[str, float]] = None,
        filters: Optional[Dict[str, Any]] = None,
        mark_current: bool = True
    ) -> int:
        """
        Save embedding session metadata.

        Args:
            provider: Embedding provider (e.g., 'tfidf', 'ollama')
            chunking_strategy: Chunking strategy used
            aggregation_strategy: Aggregation strategy used
            num_conversations: Number of conversations embedded
            model: Model name (if applicable)
            role_weights: Role weights used (as dict)
            filters: Filters applied (starred, tags, search, etc.)
            mark_current: Whether to mark this as current session

        Returns:
            Session ID
        """
        with self.session_scope() as session:
            # If marking as current, unmark all previous sessions
            if mark_current:
                session.query(EmbeddingSessionModel).update({'is_current': False})

            # Create new session
            session_model = EmbeddingSessionModel(
                provider=provider,
                model=model,
                chunking_strategy=chunking_strategy,
                aggregation_strategy=aggregation_strategy,
                role_weights_json=role_weights,
                filters_json=filters,
                num_conversations=num_conversations,
                is_current=mark_current
            )
            session.add(session_model)
            session.flush()

            logger.info(f"Created embedding session {session_model.id} with {num_conversations} conversations")
            return session_model.id

    def get_current_embedding_session(self) -> Optional[Dict[str, Any]]:
        """
        Get the current (most recent) embedding session.

        Returns:
            Dictionary with session metadata or None if no sessions exist
        """
        with self.session_scope() as session:
            session_model = session.query(EmbeddingSessionModel).filter(
                EmbeddingSessionModel.is_current == True
            ).first()

            if not session_model:
                # Fallback: get most recent session
                session_model = session.query(EmbeddingSessionModel).order_by(
                    EmbeddingSessionModel.created_at.desc()
                ).first()

            if not session_model:
                return None

            return {
                'id': session_model.id,
                'created_at': session_model.created_at,
                'provider': session_model.provider,
                'model': session_model.model,
                'chunking_strategy': session_model.chunking_strategy,
                'aggregation_strategy': session_model.aggregation_strategy,
                'role_weights': session_model.role_weights_json,
                'filters': session_model.filters_json,
                'num_conversations': session_model.num_conversations,
                'is_current': session_model.is_current
            }

    def get_embedding_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """
        Get specific embedding session by ID.

        Args:
            session_id: Session ID

        Returns:
            Dictionary with session metadata or None if not found
        """
        with self.session_scope() as session:
            session_model = session.query(EmbeddingSessionModel).filter(
                EmbeddingSessionModel.id == session_id
            ).first()

            if not session_model:
                return None

            return {
                'id': session_model.id,
                'created_at': session_model.created_at,
                'provider': session_model.provider,
                'model': session_model.model,
                'chunking_strategy': session_model.chunking_strategy,
                'aggregation_strategy': session_model.aggregation_strategy,
                'role_weights': session_model.role_weights_json,
                'filters': session_model.filters_json,
                'num_conversations': session_model.num_conversations,
                'is_current': session_model.is_current
            }

    def list_embedding_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List recent embedding sessions.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of session dictionaries
        """
        with self.session_scope() as session:
            sessions = session.query(EmbeddingSessionModel).order_by(
                EmbeddingSessionModel.created_at.desc()
            ).limit(limit).all()

            return [{
                'id': s.id,
                'created_at': s.created_at,
                'provider': s.provider,
                'model': s.model,
                'chunking_strategy': s.chunking_strategy,
                'aggregation_strategy': s.aggregation_strategy,
                'role_weights': s.role_weights_json,
                'filters': s.filters_json,
                'num_conversations': s.num_conversations,
                'is_current': s.is_current
            } for s in sessions]

    # ==================== Graph Management Methods ====================

    def save_current_graph(
        self,
        graph_file_path: str,
        threshold: float,
        max_links_per_node: Optional[int] = None,
        embedding_session_id: Optional[int] = None,
        num_nodes: Optional[int] = None,
        num_edges: Optional[int] = None,
        **metrics
    ) -> int:
        """
        Save current graph metadata (only one graph exists at a time).

        Args:
            graph_file_path: Path to graph JSON file
            threshold: Similarity threshold used
            max_links_per_node: Max edges per node
            embedding_session_id: Reference to embedding session
            num_nodes: Number of nodes in graph
            num_edges: Number of edges in graph
            **metrics: Additional metrics (density, diameter, clustering, etc.)

        Returns:
            Graph ID (always 1)
        """
        with self.session_scope() as session:
            # Check if graph exists (id=1)
            graph = session.query(CurrentGraphModel).filter(
                CurrentGraphModel.id == 1
            ).first()

            if graph:
                # Update existing graph
                graph.created_at = func.now()
                graph.embedding_session_id = embedding_session_id
                graph.threshold = threshold
                graph.max_links_per_node = max_links_per_node
                graph.graph_file_path = graph_file_path
                graph.num_nodes = num_nodes
                graph.num_edges = num_edges

                # Update optional metrics
                for key, value in metrics.items():
                    if hasattr(graph, key):
                        setattr(graph, key, value)

                logger.info(f"Updated current graph: {graph_file_path}")
            else:
                # Create new graph
                graph = CurrentGraphModel(
                    id=1,  # Always ID 1
                    embedding_session_id=embedding_session_id,
                    threshold=threshold,
                    max_links_per_node=max_links_per_node,
                    graph_file_path=graph_file_path,
                    num_nodes=num_nodes,
                    num_edges=num_edges,
                    **{k: v for k, v in metrics.items() if hasattr(CurrentGraphModel, k)}
                )
                session.add(graph)
                logger.info(f"Created current graph: {graph_file_path}")

            session.flush()
            return 1

    def get_current_graph(self) -> Optional[Dict[str, Any]]:
        """
        Get current graph metadata.

        Returns:
            Dictionary with graph metadata or None if no graph exists
        """
        with self.session_scope() as session:
            graph = session.query(CurrentGraphModel).filter(
                CurrentGraphModel.id == 1
            ).first()

            if not graph:
                return None

            return {
                'id': graph.id,
                'created_at': graph.created_at,
                'embedding_session_id': graph.embedding_session_id,
                'threshold': graph.threshold,
                'max_links_per_node': graph.max_links_per_node,
                'graph_file_path': graph.graph_file_path,
                'num_nodes': graph.num_nodes,
                'num_edges': graph.num_edges,
                'density': graph.density,
                'avg_degree': graph.avg_degree,
                'num_components': graph.num_components,
                'giant_component_size': graph.giant_component_size,
                'avg_path_length': graph.avg_path_length,
                'diameter': graph.diameter,
                'global_clustering': graph.global_clustering,
                'avg_local_clustering': graph.avg_local_clustering,
                'communities_algorithm': graph.communities_algorithm,
                'num_communities': graph.num_communities,
                'modularity': graph.modularity
            }

    def delete_current_graph(self) -> bool:
        """
        Delete current graph and all associated data (communities, node metrics).

        Returns:
            True if graph was deleted, False if no graph existed
        """
        with self.session_scope() as session:
            # Delete communities
            session.query(CurrentCommunityModel).delete()

            # Delete node metrics
            session.query(CurrentNodeMetricsModel).delete()

            # Delete graph
            count = session.query(CurrentGraphModel).delete()

            logger.info(f"Deleted current graph and associated data")
            return count > 0

    # ==================== Hierarchical Tag Methods ====================

    def list_tag_children(self, parent_tag: Optional[str] = None) -> List[str]:
        """
        List immediate children of a tag path.

        Args:
            parent_tag: Parent tag path (e.g., "physics" or "physics/simulator")
                       If None, lists top-level tags

        Returns:
            List of child tag names (not full paths)

        Examples:
            parent_tag=None -> ["physics", "programming", "research"]
            parent_tag="physics" -> ["simulator", "quantum", "classical"]
            parent_tag="physics/simulator" -> ["molecular", "fluid"]
        """
        with self.session_scope() as session:
            # Get all tags
            all_tags = session.query(TagModel.name).all()
            tag_names = [t[0] for t in all_tags]

            # Filter based on parent
            if parent_tag is None:
                # Top-level tags (no /)
                children = set()
                for tag in tag_names:
                    if '/' not in tag:
                        children.add(tag)
                    else:
                        # Add first component
                        children.add(tag.split('/')[0])
                return sorted(children)
            else:
                # Children of specific tag
                prefix = parent_tag.rstrip('/') + '/'
                children = set()

                for tag in tag_names:
                    if tag.startswith(prefix):
                        # Get remainder after prefix
                        remainder = tag[len(prefix):]
                        # Get first component
                        if '/' in remainder:
                            child = remainder.split('/')[0]
                        else:
                            child = remainder
                        children.add(child)

                return sorted(children)

    def list_conversations_by_tag(self, tag_path: str) -> List['ConversationSummary']:
        """
        List conversations with a specific hierarchical tag.

        Args:
            tag_path: Full tag path (e.g., "physics/simulator")

        Returns:
            List of ConversationSummary objects
        """
        with self.session_scope() as session:
            # Get tag
            tag = session.query(TagModel).filter(TagModel.name == tag_path).first()

            if not tag:
                return []

            # Get conversations with this tag
            conversations = tag.conversations

            # Convert to summaries
            from ctk.core.models import ConversationSummary
            return [ConversationSummary.from_dict(c.to_dict()) for c in conversations]

    def get_all_hierarchical_tags(self) -> List[str]:
        """
        Get all hierarchical tags.

        Returns:
            List of all tag paths (e.g., ["physics", "physics/simulator", ...])
        """
        with self.session_scope() as session:
            all_tags = session.query(TagModel.name).all()
            return sorted([t[0] for t in all_tags])

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