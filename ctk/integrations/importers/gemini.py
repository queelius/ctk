"""
Google Gemini/Bard conversation importer
"""

import json
from typing import List, Any, Dict, Optional
from datetime import datetime
import uuid

from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata
)


class GeminiImporter(ImporterPlugin):
    """Import Google Gemini/Bard conversation exports"""
    
    name = "gemini"
    description = "Import Google Gemini/Bard conversation exports"
    version = "1.0.0"
    supported_formats = ["gemini", "bard", "google"]
    
    def validate(self, data: Any) -> bool:
        """Check if data is Gemini/Bard format"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                return False

        # Check for Gemini/Bard format markers
        if isinstance(data, dict):
            # Accept conversations, messages, or turns fields (Gemini format)
            if 'conversations' in data or 'messages' in data or 'turns' in data:
                return True
            # Also accept conversation_id with turns
            if 'conversation_id' in data:
                return True

        if isinstance(data, list) and data:
            sample = data[0]
            return ('model' in str(sample) and 'gemini' in str(sample).lower()) or \
                   'bard' in str(sample).lower()

        return False
    
    def _detect_model(self, conv_data: Dict) -> str:
        """Detect the Gemini model used"""
        model = conv_data.get('model', '')
        
        model_map = {
            'gemini-pro': 'Gemini Pro',
            'gemini-pro-vision': 'Gemini Pro Vision',
            'gemini-ultra': 'Gemini Ultra',
            'gemini-1.5-pro': 'Gemini 1.5 Pro',
            'gemini-1.5-flash': 'Gemini 1.5 Flash',
            'bard': 'Bard',
            'palm': 'PaLM',
            'palm-2': 'PaLM 2',
        }
        
        for key, value in model_map.items():
            if key in model.lower():
                return value
        
        return model if model else 'Gemini'
    
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import Gemini/Bard conversation data"""
        if isinstance(data, str):
            data = json.loads(data)
        
        conversations = []
        
        # Handle different Gemini export formats
        if isinstance(data, dict):
            if 'conversations' in data:
                conv_list = data['conversations']
            else:
                conv_list = [data]
        else:
            conv_list = data if isinstance(data, list) else [data]
        
        for conv_data in conv_list:
            conv_id = conv_data.get('id', conv_data.get('conversation_id', str(uuid.uuid4())))
            title = conv_data.get('title', 'Untitled Conversation')
            model = self._detect_model(conv_data)
            
            metadata = ConversationMetadata(
                version="2.0.0",
                format="gemini",
                source="Google Gemini",
                model=model,
                created_at=self._parse_timestamp(conv_data.get('created_at')) or datetime.now(),
                updated_at=self._parse_timestamp(conv_data.get('updated_at')) or datetime.now(),
                tags=['google', 'gemini', model.lower().replace(' ', '-')],
                custom_data={
                    'language': conv_data.get('language'),
                    'safety_settings': conv_data.get('safety_settings'),
                }
            )
            
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )

            # Handle both 'messages' and 'turns' fields (Gemini uses 'turns')
            messages = conv_data.get('messages', conv_data.get('turns', []))
            parent_id = None
            
            for idx, msg_data in enumerate(messages):
                msg_id = msg_data.get('id', f"msg_{idx}")
                
                # Map Gemini roles
                role_str = msg_data.get('author', msg_data.get('role', 'user'))
                if role_str.lower() in ['model', 'gemini', 'bard']:
                    role = MessageRole.ASSISTANT
                else:
                    role = MessageRole.from_string(role_str)
                
                content = MessageContent()
                
                # Handle content
                if 'parts' in msg_data:
                    # Gemini uses parts for multimodal content
                    parts = msg_data['parts']
                    text_parts = []
                    
                    for part in parts:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict):
                            if 'text' in part:
                                text_parts.append(part['text'])
                            elif 'inline_data' in part:
                                # Image or other media
                                content.metadata['media'] = content.metadata.get('media', [])
                                content.metadata['media'].append(part)
                    
                    content.text = '\n'.join(text_parts)
                    content.parts = parts
                else:
                    content.text = msg_data.get('content', msg_data.get('text', ''))
                
                message = Message(
                    id=msg_id,
                    role=role,
                    content=content,
                    timestamp=self._parse_timestamp(msg_data.get('timestamp')),
                    parent_id=parent_id,
                    metadata={
                        'candidates_count': msg_data.get('candidates_count'),
                        'safety_ratings': msg_data.get('safety_ratings'),
                    }
                )
                
                tree.add_message(message)
                parent_id = msg_id
            
            conversations.append(tree)
        
        return conversations
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse timestamp"""
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp)
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp)
            except:
                return None
        return None