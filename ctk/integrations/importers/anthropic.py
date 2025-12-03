"""
Anthropic/Claude conversation importer
"""

import json
from typing import List, Any, Dict, Optional
from datetime import datetime
import uuid

from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata,
    ToolCall, MediaContent, ContentType
)


class AnthropicImporter(ImporterPlugin):
    """Import Anthropic/Claude conversation exports"""
    
    name = "anthropic"
    description = "Import Claude conversation exports"
    version = "1.0.0"
    supported_formats = ["claude", "anthropic"]
    
    def validate(self, data: Any) -> bool:
        """Check if data is Anthropic format"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError, ValueError):
                return False

        if isinstance(data, list) and data:
            sample = data[0]
        elif isinstance(data, dict):
            sample = data
        else:
            return False

        # Check for Anthropic format markers
        # Look for chat_messages field (required) and optionally uuid or name
        has_chat_messages = 'chat_messages' in sample
        has_messages = 'messages' in sample
        has_uuid = 'uuid' in sample
        has_name = 'name' in sample

        # Valid if has chat_messages (primary Anthropic export format)
        # Or has messages/uuid with sender pattern
        if has_chat_messages:
            return True

        if has_messages and (has_uuid or has_name):
            return True

        # Also check in the content of messages if available
        has_sender = False
        if 'messages' in sample and sample['messages']:
            has_sender = any('sender' in msg for msg in sample['messages'])
        else:
            has_sender = 'sender' in str(sample)

        return has_uuid and has_sender
    
    def _detect_model(self, conv_data: Dict) -> str:
        """Detect the Claude model used"""
        model = conv_data.get('model', '')
        
        # Map model identifiers to readable names
        model_map = {
            'claude-3-opus': 'Claude 3 Opus',
            'claude-3-sonnet': 'Claude 3 Sonnet',
            'claude-3-haiku': 'Claude 3 Haiku',
            'claude-3.5-sonnet': 'Claude 3.5 Sonnet',
            'claude-2.1': 'Claude 2.1',
            'claude-2': 'Claude 2',
            'claude-instant-1.2': 'Claude Instant 1.2',
            'claude-instant': 'Claude Instant',
        }
        
        for key, value in model_map.items():
            if key in model.lower():
                return value
        
        # Check in messages for model info
        messages = conv_data.get('messages', [])
        for msg in messages:
            if 'model' in msg:
                for key, value in model_map.items():
                    if key in msg['model'].lower():
                        return value
        
        return model if model else 'Claude'
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        if timestamp is None:
            return None
        
        if isinstance(timestamp, datetime):
            return timestamp
        
        if isinstance(timestamp, (int, float)):
            try:
                # Handle milliseconds
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
                return datetime.fromtimestamp(timestamp)
            except (ValueError, OSError, OverflowError):
                return None
        
        if isinstance(timestamp, str):
            formats = [
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(timestamp, fmt)
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import Anthropic conversation data"""
        if isinstance(data, str):
            data = json.loads(data)
        
        if not isinstance(data, list):
            data = [data]
        
        conversations = []
        
        for conv_data in data:
            # Extract basic info
            conv_id = conv_data.get('uuid') or conv_data.get('id', str(uuid.uuid4()))
            title = conv_data.get('name') or conv_data.get('title', 'Untitled Conversation')
            
            # Detect model
            model = self._detect_model(conv_data)
            
            # Create metadata
            metadata = ConversationMetadata(
                version="2.0.0",
                format="anthropic",
                source="Claude",
                model=model,
                created_at=self._parse_timestamp(conv_data.get('created_at')) or datetime.now(),
                updated_at=self._parse_timestamp(conv_data.get('updated_at')) or datetime.now(),
                tags=['anthropic', 'claude'] + ([model.lower().replace(' ', '-')] if model.lower() != 'claude' else []),
                custom_data={
                    'project_uuid': conv_data.get('project_uuid'),
                    'account_uuid': conv_data.get('account', {}).get('uuid') if isinstance(conv_data.get('account'), dict) else conv_data.get('account_uuid'),
                    'summary': conv_data.get('summary'),
                }
            )
            
            # Create conversation tree
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )
            
            # Process messages - handle both 'messages' and 'chat_messages' fields
            messages = conv_data.get('messages', conv_data.get('chat_messages', []))
            parent_id = None
            
            for idx, msg_data in enumerate(messages):
                # Generate message ID
                msg_id = msg_data.get('uuid') or msg_data.get('id', f"msg_{idx}")
                
                # Extract role
                sender = msg_data.get('sender', msg_data.get('role', 'user'))
                role = MessageRole.from_string(sender)
                
                # Extract content
                content = MessageContent()
                
                # Handle different content formats
                if 'text' in msg_data:
                    content.text = msg_data['text']
                    
                    # Check for attachments
                    if 'attachments' in msg_data:
                        for attachment in msg_data['attachments']:
                            if isinstance(attachment, dict):
                                file_name = attachment.get('file_name', '')
                                file_type = attachment.get('file_type', '')
                                
                                # Add as image if it looks like an image
                                if any(ext in file_name.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                                    content.add_image(
                                        path=file_name,
                                        mime_type=file_type
                                    )
                                # Add as document otherwise
                                elif file_name:
                                    doc = MediaContent(
                                        type=ContentType.DOCUMENT,
                                        path=file_name,
                                        mime_type=file_type
                                    )
                                    content.documents.append(doc)
                    
                    # Add attachment info to text if present
                    if 'attachments' in msg_data and msg_data['attachments']:
                        attachment_text = '\n\nAttachments: ' + ', '.join(
                            a.get('file_name', 'Unknown') for a in msg_data['attachments']
                        )
                        content.text = (content.text or '') + attachment_text
                        
                elif 'content' in msg_data:
                    if isinstance(msg_data['content'], str):
                        content.text = msg_data['content']
                    elif isinstance(msg_data['content'], list):
                        # Handle multipart content
                        text_parts = []
                        for part in msg_data['content']:
                            if isinstance(part, str):
                                text_parts.append(part)
                            elif isinstance(part, dict):
                                part_type = part.get('type', '')
                                
                                if part_type == 'text':
                                    text_parts.append(part.get('text', ''))
                                elif part_type == 'image':
                                    # Handle image content
                                    source = part.get('source', {})
                                    if isinstance(source, dict):
                                        if source.get('type') == 'base64':
                                            content.add_image(
                                                data=source.get('data'),
                                                mime_type=source.get('media_type', 'image/png')
                                            )
                                        elif 'url' in source:
                                            content.add_image(url=source['url'])
                                elif part_type == 'tool_use':
                                    # Handle tool use
                                    tool_call = ToolCall(
                                        id=part.get('id', ''),
                                        name=part.get('name', ''),
                                        arguments=part.get('input', {})
                                    )
                                    content.tool_calls.append(tool_call)
                                elif part_type == 'tool_result':
                                    # Handle tool result
                                    tool_id = part.get('tool_use_id', '')
                                    # Find the corresponding tool call and update it
                                    for tc in content.tool_calls:
                                        if tc.id == tool_id:
                                            tc.result = part.get('content', '')
                                            tc.status = 'completed'
                                            if part.get('is_error'):
                                                tc.status = 'failed'
                                                tc.error = str(part.get('content', ''))
                                            break
                                else:
                                    # Store unknown parts in metadata
                                    content.metadata['attachments'] = content.metadata.get('attachments', [])
                                    content.metadata['attachments'].append(part)
                        
                        content.text = '\n'.join(text_parts) if text_parts else ''
                        content.parts = msg_data['content']
                
                # Create message
                message = Message(
                    id=msg_id,
                    role=role,
                    content=content,
                    timestamp=self._parse_timestamp(msg_data.get('created_at')),
                    parent_id=parent_id,
                    metadata={
                        'files': msg_data.get('files', []),
                        'feedback': msg_data.get('feedback'),
                    }
                )
                
                # Add to tree (linear for now, as Anthropic exports are typically linear)
                tree.add_message(message)
                parent_id = msg_id
            
            conversations.append(tree)
        
        return conversations