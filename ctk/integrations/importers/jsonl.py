"""
JSONL format importer (common for local LLMs and fine-tuning)
"""

import json
from typing import List, Any, Dict, Optional
from datetime import datetime
import uuid

from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata
)


class JSONLImporter(ImporterPlugin):
    """Import JSONL conversation format (used by local LLMs and fine-tuning)"""
    
    name = "jsonl"
    description = "Import JSONL conversation format"
    version = "1.0.0"
    supported_formats = ["jsonl", "local", "llama", "mistral", "alpaca"]
    
    def validate(self, data: Any) -> bool:
        """Check if data is JSONL format"""
        if isinstance(data, str):
            # Check if it's JSONL (multiple JSON objects separated by newlines)
            lines = data.strip().split('\n')
            if len(lines) > 0:
                try:
                    first_line = json.loads(lines[0])
                    # Common JSONL conversation format
                    if 'messages' in first_line or 'conversations' in first_line:
                        return True
                    # Single message per line format
                    if 'role' in first_line and 'content' in first_line:
                        return True
                except:
                    pass
        
        # Also support list of message dicts
        if isinstance(data, list) and data:
            sample = data[0]
            if isinstance(sample, dict):
                # Standard message format
                if 'role' in sample and 'content' in sample:
                    return True
                # Conversation wrapper
                if 'messages' in sample or 'conversations' in sample:
                    return True
        
        return False
    
    def _detect_model(self, data: Any) -> str:
        """Try to detect the model from the data"""
        # Look for model hints in the data
        if isinstance(data, dict):
            model = data.get('model', '')
            if model:
                return model
        
        # Check for common model patterns
        model_hints = {
            'llama': 'LLaMA',
            'mistral': 'Mistral',
            'alpaca': 'Alpaca',
            'vicuna': 'Vicuna',
            'wizardlm': 'WizardLM',
            'openchat': 'OpenChat',
            'orca': 'Orca',
            'falcon': 'Falcon',
            'mpt': 'MPT',
            'stablelm': 'StableLM',
            'qwen': 'Qwen',
            'yi': 'Yi',
            'deepseek': 'DeepSeek',
            'gemma': 'Gemma',
            'phi': 'Phi',
        }
        
        data_str = str(data).lower()
        for hint, name in model_hints.items():
            if hint in data_str:
                return name
        
        return 'Local LLM'
    
    def _parse_jsonl_line(self, line: str) -> Optional[Dict]:
        """Parse a single JSONL line"""
        try:
            return json.loads(line)
        except:
            return None
    
    def _extract_messages(self, data: Any) -> List[List[Dict]]:
        """Extract messages from various JSONL formats"""
        conversations = []
        
        if isinstance(data, str):
            lines = data.strip().split('\n')
            current_conv = []
            
            for line in lines:
                if not line.strip():
                    if current_conv:
                        conversations.append(current_conv)
                        current_conv = []
                    continue
                
                obj = self._parse_jsonl_line(line)
                if not obj:
                    continue
                
                # Handle different formats
                if 'messages' in obj:
                    # Full conversation in one line
                    conversations.append(obj['messages'])
                elif 'conversations' in obj:
                    # Alternative naming
                    conversations.append(obj['conversations'])
                elif 'role' in obj and 'content' in obj:
                    # Single message per line
                    current_conv.append(obj)
                elif 'instruction' in obj and 'response' in obj:
                    # Instruction-following format
                    conv = []
                    if 'system' in obj:
                        conv.append({'role': 'system', 'content': obj['system']})
                    conv.append({'role': 'user', 'content': obj['instruction']})
                    conv.append({'role': 'assistant', 'content': obj['response']})
                    conversations.append(conv)
                elif 'prompt' in obj and 'completion' in obj:
                    # Completion format
                    conversations.append([
                        {'role': 'user', 'content': obj['prompt']},
                        {'role': 'assistant', 'content': obj['completion']}
                    ])
            
            if current_conv:
                conversations.append(current_conv)
        
        elif isinstance(data, list):
            # Already a list, check format
            if data and isinstance(data[0], dict):
                if 'messages' in data[0]:
                    # List of conversation objects
                    for item in data:
                        if 'messages' in item:
                            conversations.append(item['messages'])
                elif 'role' in data[0]:
                    # Single conversation as list of messages
                    conversations.append(data)
        
        return conversations
    
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import JSONL conversation data"""
        conversations_data = self._extract_messages(data)
        model = self._detect_model(data)
        
        conversations = []
        
        for idx, messages_data in enumerate(conversations_data):
            if not messages_data:
                continue
            
            # Create conversation ID and title
            conv_id = f"jsonl_{idx}_{uuid.uuid4().hex[:8]}"
            
            # Try to generate a title from the first user message
            title = "Untitled Conversation"
            for msg in messages_data:
                if msg.get('role') in ['user', 'human']:
                    content = msg.get('content', '')
                    if content:
                        # Take first 50 chars as title
                        title = content[:50] + ('...' if len(content) > 50 else '')
                        break
            
            # Create metadata
            metadata = ConversationMetadata(
                version="2.0.0",
                format="jsonl",
                source="Local",
                model=model,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                tags=['local', 'jsonl', model.lower().replace(' ', '-')],
                custom={
                    'import_index': idx,
                    'message_count': len(messages_data)
                }
            )
            
            # Create conversation tree
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )
            
            # Add messages as linear conversation
            parent_id = None
            
            for msg_idx, msg_data in enumerate(messages_data):
                # Generate message ID
                msg_id = f"msg_{msg_idx}_{uuid.uuid4().hex[:8]}"
                
                # Extract role
                role_str = msg_data.get('role', 'user')
                # Handle alternative role names
                role_map = {
                    'human': 'user',
                    'ai': 'assistant',
                    'bot': 'assistant',
                    'model': 'assistant',
                    'gpt': 'assistant',
                }
                role_str = role_map.get(role_str.lower(), role_str)
                role = MessageRole.from_string(role_str)
                
                # Extract content
                content = MessageContent()
                content_data = msg_data.get('content', '')
                
                if isinstance(content_data, str):
                    content.text = content_data
                elif isinstance(content_data, list):
                    # Multimodal content
                    text_parts = []
                    for part in content_data:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict):
                            if part.get('type') == 'text':
                                text_parts.append(part.get('text', ''))
                            else:
                                content.metadata['parts'] = content.metadata.get('parts', [])
                                content.metadata['parts'].append(part)
                    content.text = '\n'.join(text_parts)
                    content.parts = content_data
                
                # Extract timestamp if available
                timestamp = None
                if 'timestamp' in msg_data:
                    timestamp = self._parse_timestamp(msg_data['timestamp'])
                elif 'created_at' in msg_data:
                    timestamp = self._parse_timestamp(msg_data['created_at'])
                
                # Create message
                message = Message(
                    id=msg_id,
                    role=role,
                    content=content,
                    timestamp=timestamp,
                    parent_id=parent_id,
                    metadata={k: v for k, v in msg_data.items() 
                             if k not in ['role', 'content', 'timestamp', 'created_at']}
                )
                
                # Add to tree
                tree.add_message(message, parent_id=parent_id)
                parent_id = msg_id
            
            conversations.append(tree)
        
        return conversations
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        if isinstance(timestamp, (int, float)):
            try:
                return datetime.fromtimestamp(timestamp)
            except:
                return None
        
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp)
            except:
                return None
        
        return None