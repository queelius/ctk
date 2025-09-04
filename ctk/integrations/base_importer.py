"""
Base classes for conversation importers with common functionality
"""

import json
import logging
from typing import List, Any, Dict, Optional, Union
from datetime import datetime
from abc import abstractmethod

from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata,
    ToolCall, MediaContent, ContentType
)

logger = logging.getLogger(__name__)


class JSONBasedImporter(ImporterPlugin):
    """Base class for JSON-based conversation importers"""
    
    def validate(self, data: Any) -> bool:
        """Check if data can be parsed as JSON and validate format"""
        try:
            parsed_data = self._parse_json_data(data)
            return self._validate_format(parsed_data)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.debug(f"JSON validation failed in {self.name}: {e}")
            return False
    
    def _parse_json_data(self, data: Any) -> Union[Dict, List]:
        """Parse input data as JSON if needed"""
        if isinstance(data, str):
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse JSON in {self.name}: {e}")
                raise ValueError(f"Invalid JSON data: {e}")
        
        if isinstance(data, (dict, list)):
            return data
        
        raise TypeError(f"Unsupported data type: {type(data)}")
    
    def _normalize_data_to_list(self, data: Union[Dict, List]) -> List[Dict]:
        """Normalize data to a list of conversation dictionaries"""
        if isinstance(data, dict):
            return [data]
        elif isinstance(data, list):
            return data
        else:
            raise TypeError("Data must be a dict or list")
    
    def _parse_timestamp(self, timestamp: Any, formats: Optional[List[str]] = None) -> Optional[datetime]:
        """Parse timestamp from various formats with comprehensive error handling"""
        if timestamp is None:
            return None
        
        # Handle numeric timestamps
        if isinstance(timestamp, (int, float)):
            try:
                return datetime.fromtimestamp(timestamp)
            except (ValueError, OSError, OverflowError) as e:
                logger.warning(f"Invalid numeric timestamp {timestamp}: {e}")
                return None
        
        # Handle string timestamps
        if isinstance(timestamp, str):
            if formats is None:
                formats = self._get_default_timestamp_formats()
            
            for fmt in formats:
                try:
                    return datetime.strptime(timestamp, fmt)
                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to parse timestamp '{timestamp}' with format '{fmt}': {e}")
                    continue
            
            logger.warning(f"Could not parse timestamp: {timestamp}")
        
        return None
    
    def _get_default_timestamp_formats(self) -> List[str]:
        """Get default timestamp formats to try"""
        return [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S.%fZ", 
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
    
    def _create_base_metadata(self, conv_data: Dict, **overrides) -> ConversationMetadata:
        """Create base metadata with common fields"""
        metadata = ConversationMetadata(
            version="2.0.0",
            format=self.name,
            source=overrides.get('source', self.name.title()),
            model=overrides.get('model', self._detect_model(conv_data)),
            created_at=overrides.get('created_at') or self._extract_created_time(conv_data) or datetime.now(),
            updated_at=overrides.get('updated_at') or self._extract_updated_time(conv_data) or datetime.now(),
            tags=overrides.get('tags', [self.name]),
            custom_data=overrides.get('custom_data', self._extract_custom_metadata(conv_data))
        )
        return metadata
    
    def _safe_process_conversation(self, conv_data: Dict, index: int) -> Optional[ConversationTree]:
        """Safely process a single conversation with error handling"""
        try:
            return self._process_conversation(conv_data)
        except Exception as e:
            logger.error(f"Error processing conversation at index {index} in {self.name}: {e}")
            return None
    
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import conversation data with comprehensive error handling"""
        try:
            # Parse and normalize data
            parsed_data = self._parse_json_data(data)
            conversations_data = self._normalize_data_to_list(parsed_data)
            
            conversations = []
            
            for i, conv_data in enumerate(conversations_data):
                if not isinstance(conv_data, dict):
                    logger.warning(f"Skipping non-dict conversation data at index {i} in {self.name}")
                    continue
                
                conversation = self._safe_process_conversation(conv_data, i)
                if conversation:
                    conversations.append(conversation)
            
            logger.info(f"Successfully imported {len(conversations)} conversations using {self.name}")
            return conversations
            
        except Exception as e:
            logger.error(f"Failed to import data using {self.name}: {e}")
            raise
    
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    def _validate_format(self, data: Union[Dict, List]) -> bool:
        """Validate that the data matches this importer's format"""
        pass
    
    @abstractmethod
    def _detect_model(self, conv_data: Dict) -> str:
        """Detect the AI model used in the conversation"""
        pass
    
    @abstractmethod  
    def _process_conversation(self, conv_data: Dict) -> ConversationTree:
        """Process a single conversation dictionary into a ConversationTree"""
        pass
    
    # Optional methods with default implementations
    
    def _extract_created_time(self, conv_data: Dict) -> Optional[datetime]:
        """Extract creation timestamp from conversation data"""
        for field in ['create_time', 'created_at', 'createdAt', 'timestamp']:
            if field in conv_data:
                return self._parse_timestamp(conv_data[field])
        return None
    
    def _extract_updated_time(self, conv_data: Dict) -> Optional[datetime]:
        """Extract update timestamp from conversation data"""
        for field in ['update_time', 'updated_at', 'updatedAt', 'lastModified']:
            if field in conv_data:
                return self._parse_timestamp(conv_data[field])
        return None
    
    def _extract_custom_metadata(self, conv_data: Dict) -> Dict[str, Any]:
        """Extract custom metadata fields"""
        return {}
    
    def _create_message_content(self, content_data: Any) -> MessageContent:
        """Create MessageContent from various content formats"""
        if isinstance(content_data, str):
            return MessageContent(text=content_data)
        
        if isinstance(content_data, dict):
            content = MessageContent(text=content_data.get('text', ''))
            
            # Handle parts/attachments
            if 'parts' in content_data:
                content.parts = content_data['parts']
            
            # Handle tool calls
            if 'tool_calls' in content_data:
                content.tool_calls = [
                    self._create_tool_call(tool_data) 
                    for tool_data in content_data['tool_calls']
                ]
            
            return content
        
        # Fallback for unexpected content types
        return MessageContent(text=str(content_data))
    
    def _create_tool_call(self, tool_data: Dict) -> ToolCall:
        """Create ToolCall from tool call data"""
        try:
            arguments = tool_data.get('function', {}).get('arguments', '{}')
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        
        return ToolCall(
            id=tool_data.get('id', ''),
            name=tool_data.get('function', {}).get('name', ''),
            arguments=arguments
        )


class ConversationMapImporter(JSONBasedImporter):
    """Base for importers that use message mapping/tree structures"""
    
    def _process_conversation(self, conv_data: Dict) -> ConversationTree:
        """Process conversation with message mapping"""
        # Extract basic info
        conv_id = self._extract_conversation_id(conv_data)
        title = conv_data.get('title', 'Untitled Conversation')
        
        # Create metadata
        metadata = self._create_base_metadata(conv_data)
        
        # Create conversation tree
        tree = ConversationTree(id=conv_id, title=title, metadata=metadata)
        
        # Process messages
        messages_data = self._extract_messages_data(conv_data)
        for msg_data in messages_data:
            message = self._process_message(msg_data)
            if message:
                tree.add_message(message)
        
        return tree
    
    @abstractmethod
    def _extract_conversation_id(self, conv_data: Dict) -> str:
        """Extract conversation ID from conversation data"""
        pass
    
    @abstractmethod
    def _extract_messages_data(self, conv_data: Dict) -> List[Dict]:
        """Extract messages data from conversation"""
        pass
    
    @abstractmethod
    def _process_message(self, msg_data: Dict) -> Optional[Message]:
        """Process a single message from the conversation"""
        pass