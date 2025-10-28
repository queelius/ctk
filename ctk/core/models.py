"""
Core data models for conversation representation
"""

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import json
import uuid


class MessageRole(Enum):
    """Standard message roles across platforms"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"
    TOOL_RESULT = "tool_result"  # For tool execution results
    
    @classmethod
    def from_string(cls, role: str) -> 'MessageRole':
        """Convert string to MessageRole, handling platform variations"""
        if not role:
            return cls.USER
        
        if not isinstance(role, str):
            return cls.USER
            
        role = role.lower().strip()
        role_map = {
            'human': cls.USER,
            'ai': cls.ASSISTANT,
            'claude': cls.ASSISTANT,
            'gpt': cls.ASSISTANT,
            'chatgpt': cls.ASSISTANT,
            'bot': cls.ASSISTANT,
            'model': cls.ASSISTANT,
            'tool_use': cls.TOOL,
            'function_call': cls.FUNCTION,
        }
        
        if role in role_map:
            return role_map[role]
        
        try:
            return cls(role)
        except ValueError:
            return cls.USER


class ContentType(Enum):
    """Types of content that can be in a message"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    CODE = "code"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class MediaContent:
    """Represents media content (image, audio, video, document)"""
    type: ContentType
    url: Optional[str] = None  # URL to the media
    path: Optional[str] = None  # Local file path
    data: Optional[str] = None  # Base64 encoded data
    mime_type: Optional[str] = None  # MIME type (image/png, audio/mp3, etc.)
    caption: Optional[str] = None  # Optional caption/description
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_remote(self) -> bool:
        """Check if media is from a remote URL"""
        return self.url is not None and self.url.startswith(('http://', 'https://'))
    
    def is_local(self) -> bool:
        """Check if media is a local file"""
        return self.path is not None
    
    def is_embedded(self) -> bool:
        """Check if media is embedded as base64"""
        return self.data is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = {}
        if self.type:
            # Convert ContentType enum to string
            data['type'] = self.type.value if isinstance(self.type, ContentType) else self.type
        if self.url is not None:
            data['url'] = self.url
        if self.path is not None:
            data['path'] = self.path
        if self.data is not None:
            data['data'] = self.data
        if self.mime_type is not None:
            data['mime_type'] = self.mime_type
        if self.caption is not None:
            data['caption'] = self.caption
        if self.metadata:
            data['metadata'] = self.metadata
        return data


@dataclass
class ToolCall:
    """Represents a tool/function call"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""  # Tool/function name
    arguments: Dict[str, Any] = field(default_factory=dict)  # Arguments passed
    result: Optional[Any] = None  # Result from tool execution
    status: str = "pending"  # pending, completed, failed
    error: Optional[str] = None  # Error message if failed
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'name': self.name,
            'arguments': self.arguments,
            'status': self.status
        }
        if self.result is not None:
            data['result'] = self.result
        if self.error:
            data['error'] = self.error
        if self.metadata:
            data['metadata'] = self.metadata
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolCall':
        """Create from dictionary"""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', ''),
            arguments=data.get('arguments', {}),
            result=data.get('result'),
            status=data.get('status', 'pending'),
            error=data.get('error'),
            metadata=data.get('metadata', {})
        )


@dataclass
class MessageContent:
    """Content of a message, supporting text and multimodal content"""
    text: Optional[str] = None
    images: List[MediaContent] = field(default_factory=list)
    audio: List[MediaContent] = field(default_factory=list)
    video: List[MediaContent] = field(default_factory=list)
    documents: List[MediaContent] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    
    # Legacy fields for compatibility
    type: str = "text"
    parts: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_text(self) -> str:
        """Extract text content from various formats"""
        if self.text:
            return self.text
        
        # Fallback to parts for legacy compatibility
        if self.parts:
            text_parts = []
            for part in self.parts:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    if 'text' in part:
                        text_parts.append(part['text'])
                    elif 'content' in part:
                        text_parts.append(str(part['content']))
            return '\n'.join(text_parts)
        
        return ""
    
    def add_image(self, url: str = None, path: str = None, data: str = None, 
                  caption: str = None, mime_type: str = None):
        """Add an image to the content"""
        img = MediaContent(
            type=ContentType.IMAGE,
            url=url,
            path=path,
            data=data,
            caption=caption,
            mime_type=mime_type or "image/png"
        )
        self.images.append(img)
        return img
    
    def add_tool_call(self, name: str, arguments: Dict[str, Any] = None, 
                      tool_id: str = None) -> ToolCall:
        """Add a tool call to the content"""
        tool_call = ToolCall(
            id=tool_id or str(uuid.uuid4()),
            name=name,
            arguments=arguments or {}
        )
        self.tool_calls.append(tool_call)
        return tool_call
    
    def has_media(self) -> bool:
        """Check if content has any media attachments"""
        return bool(self.images or self.audio or self.video or self.documents)
    
    def has_tools(self) -> bool:
        """Check if content has tool calls"""
        return bool(self.tool_calls)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = {}
        # Always include text field, using get_text() to extract from parts if needed
        text_content = self.get_text()
        data['text'] = text_content  # Always include, even if empty
        if self.images:
            data['images'] = [img.to_dict() for img in self.images]
        if self.audio:
            data['audio'] = [a.to_dict() for a in self.audio]
        if self.video:
            data['video'] = [v.to_dict() for v in self.video]
        if self.documents:
            data['documents'] = [d.to_dict() for d in self.documents]
        if self.tool_calls:
            data['tool_calls'] = [t.to_dict() for t in self.tool_calls]
        if self.parts:  # Legacy
            data['parts'] = self.parts
        if self.metadata:
            data['metadata'] = self.metadata
        # Don't include type field if it's the default ContentType enum
        if self.type and not isinstance(self.type, ContentType):
            data['type'] = self.type
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageContent':
        """Create from dictionary"""
        content = cls(
            text=data.get('text'),
            type=data.get('type', 'text'),
            parts=data.get('parts', []),
            metadata=data.get('metadata', {})
        )
        
        # Load media
        if 'images' in data:
            for img_data in data['images']:
                content.images.append(MediaContent(
                    type=ContentType.IMAGE,
                    **{k: v for k, v in img_data.items() if k != 'type'}
                ))
        
        # Load tool calls
        if 'tool_calls' in data:
            for tool_data in data['tool_calls']:
                content.tool_calls.append(ToolCall.from_dict(tool_data))
        
        return content


@dataclass
class Message:
    """A single message in a conversation"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: MessageRole = MessageRole.USER
    content: MessageContent = field(default_factory=MessageContent)
    timestamp: Optional[datetime] = field(default_factory=datetime.now)
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'role': self.role.value,
            'content': self.content.to_dict(),
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'parent_id': self.parent_id,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create from dictionary"""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            role=MessageRole.from_string(data.get('role', 'user')),
            content=MessageContent.from_dict(data.get('content', {})),
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else None,
            parent_id=data.get('parent_id'),
            metadata=data.get('metadata', {})
        )


@dataclass
class ConversationMetadata:
    """Metadata about a conversation"""
    version: str = "2.0.0"
    format: str = "ctk"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None  # Platform/source (openai, anthropic, etc.)
    model: Optional[str] = None  # Model used
    tags: List[str] = field(default_factory=list)
    project: Optional[str] = None  # Project name for organization
    custom_data: Dict[str, Any] = field(default_factory=dict)  # Renamed from custom
    # Organization fields
    starred_at: Optional[datetime] = None
    pinned_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'version': self.version,
            'format': self.format,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'source': self.source,
            'model': self.model,
            'tags': self.tags,
            'project': self.project,
            'custom_data': self.custom_data,
            'starred_at': self.starred_at.isoformat() if self.starred_at else None,
            'pinned_at': self.pinned_at.isoformat() if self.pinned_at else None,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationMetadata':
        """Create from dictionary"""
        return cls(
            version=data.get('version', '2.0.0'),
            format=data.get('format', 'ctk'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else datetime.now(),
            source=data.get('source'),
            model=data.get('model'),
            tags=data.get('tags', []),
            project=data.get('project'),
            custom_data=data.get('custom_data', data.get('custom', {})),  # Handle both names
            starred_at=datetime.fromisoformat(data['starred_at']) if data.get('starred_at') else None,
            pinned_at=datetime.fromisoformat(data['pinned_at']) if data.get('pinned_at') else None,
            archived_at=datetime.fromisoformat(data['archived_at']) if data.get('archived_at') else None
        )


@dataclass
class ConversationSummary:
    """Lightweight conversation metadata (no messages loaded)"""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    source: Optional[str] = None
    model: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    project: Optional[str] = None
    starred_at: Optional[datetime] = None
    pinned_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_count': self.message_count,
            'source': self.source,
            'model': self.model,
            'tags': self.tags,
            'project': self.project,
            'starred_at': self.starred_at.isoformat() if self.starred_at else None,
            'pinned_at': self.pinned_at.isoformat() if self.pinned_at else None,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationSummary':
        """Create from dictionary"""
        return cls(
            id=data['id'],
            title=data.get('title', 'Untitled'),
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data.get('created_at'), str) else data.get('created_at', datetime.now()),
            updated_at=datetime.fromisoformat(data['updated_at']) if isinstance(data.get('updated_at'), str) else data.get('updated_at', datetime.now()),
            message_count=data.get('message_count', 0),
            source=data.get('source'),
            model=data.get('model'),
            tags=data.get('tags', []),
            project=data.get('project'),
            starred_at=datetime.fromisoformat(data['starred_at']) if isinstance(data.get('starred_at'), str) else data.get('starred_at'),
            pinned_at=datetime.fromisoformat(data['pinned_at']) if isinstance(data.get('pinned_at'), str) else data.get('pinned_at'),
            archived_at=datetime.fromisoformat(data['archived_at']) if isinstance(data.get('archived_at'), str) else data.get('archived_at'),
        )


@dataclass
class ConversationTree:
    """Tree-structured conversation representation"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: Optional[str] = None
    metadata: ConversationMetadata = field(default_factory=ConversationMetadata)
    message_map: Dict[str, Message] = field(default_factory=dict)
    root_message_ids: List[str] = field(default_factory=list)
    
    def add_message(self, message: Message) -> None:
        """Add a message to the conversation tree"""
        self.message_map[message.id] = message
        
        # If no parent, it's a root message
        if not message.parent_id:
            if message.id not in self.root_message_ids:
                self.root_message_ids.append(message.id)
        
        # Update metadata
        self.metadata.updated_at = datetime.now()
    
    def get_children(self, message_id: str) -> List[Message]:
        """Get all direct children of a message"""
        children = []
        for msg in self.message_map.values():
            if msg.parent_id == message_id:
                children.append(msg)
        return sorted(children, key=lambda m: m.timestamp or datetime.min)
    
    def get_all_paths(self) -> List[List[Message]]:
        """Get all possible conversation paths from root to leaf"""
        all_paths = []
        
        for root_id in self.root_message_ids:
            paths_from_root = self._get_paths_from_message(root_id)
            all_paths.extend(paths_from_root)
        
        return all_paths
    
    def _get_paths_from_message(self, message_id: str) -> List[List[Message]]:
        """Get all paths starting from a specific message"""
        message = self.message_map.get(message_id)
        if not message:
            return []
        
        children = self.get_children(message_id)
        
        if not children:
            # Leaf node - return single path with just this message
            return [[message]]
        
        # Get paths from all children and prepend this message
        all_paths = []
        for child in children:
            child_paths = self._get_paths_from_message(child.id)
            for child_path in child_paths:
                complete_path = [message] + child_path
                all_paths.append(complete_path)
        
        return all_paths
    
    def get_longest_path(self) -> List[Message]:
        """Get the longest conversation path (most messages)"""
        paths = self.get_all_paths()
        if not paths:
            return []
        return max(paths, key=len)
    
    def get_linear_history(self, leaf_message_id: str = None) -> List[Message]:
        """Get linear history from root to a specific message or longest path"""
        if not leaf_message_id:
            return self.get_longest_path()
        
        history = []
        current_id = leaf_message_id
        
        while current_id:
            message = self.message_map.get(current_id)
            if not message:
                break
            history.append(message)
            current_id = message.parent_id
        
        return list(reversed(history))
    
    def count_branches(self) -> int:
        """Count the number of branch points in the conversation"""
        branch_count = 0
        for msg_id in self.message_map:
            children = self.get_children(msg_id)
            if len(children) > 1:
                branch_count += 1
        return branch_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'metadata': self.metadata.to_dict(),
            'messages': [msg.to_dict() for msg in self.message_map.values()],
            'root_message_ids': self.root_message_ids
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationTree':
        """Create from dictionary"""
        conv = cls(
            id=data.get('id', str(uuid.uuid4())),
            title=data.get('title'),
            metadata=ConversationMetadata.from_dict(data.get('metadata', {}))
        )
        
        # Add messages
        for msg_data in data.get('messages', []):
            message = Message.from_dict(msg_data)
            conv.add_message(message)
        
        # Set root message IDs if provided
        if 'root_message_ids' in data:
            conv.root_message_ids = data['root_message_ids']
        
        return conv