"""
OpenAI/ChatGPT conversation importer
"""

import json
import logging
from typing import List, Any, Dict, Optional
from datetime import datetime
import re
import os
import glob
import base64

from ctk.core.plugin import ImporterPlugin

logger = logging.getLogger(__name__)
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata,
    ToolCall, MediaContent, ContentType
)


class OpenAIImporter(ImporterPlugin):
    """Import OpenAI/ChatGPT conversation exports"""
    
    name = "openai"
    description = "Import ChatGPT conversation exports"
    version = "1.0.0"
    supported_formats = ["chatgpt", "openai", "gpt"]
    
    def validate(self, data: Any) -> bool:
        """Check if data is OpenAI format"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                return False
        
        if isinstance(data, list) and data:
            sample = data[0]
        elif isinstance(data, dict):
            sample = data
        else:
            return False
        
        # Check for OpenAI format markers
        return 'mapping' in sample and ('conversation_id' in sample or 'id' in sample)
    
    def _detect_model(self, conv_data: Dict) -> str:
        """Detect the model used in the conversation"""
        model = conv_data.get('default_model_slug', '')
        
        # Map common model slugs to readable names
        model_map = {
            'gpt-4': 'GPT-4',
            'gpt-4-turbo': 'GPT-4 Turbo',
            'gpt-4-1106-preview': 'GPT-4 Turbo Preview',
            'gpt-4-0125-preview': 'GPT-4 Turbo (Jan 2024)',
            'gpt-4o': 'GPT-4o',
            'gpt-4o-mini': 'GPT-4o Mini',
            'gpt-3.5-turbo': 'GPT-3.5 Turbo',
            'text-davinci-003': 'GPT-3.5 (Davinci)',
            'text-davinci-002': 'GPT-3 (Davinci)',
        }
        
        if model:
            model_lower = model.lower()
            for key, value in model_map.items():
                if key in model_lower:
                    return value
            return model
        
        return 'ChatGPT'
    
    def _extract_metadata(self, conv_data: Dict) -> Dict[str, Any]:
        """Extract additional metadata from conversation"""
        metadata = {
            'gizmo_id': conv_data.get('gizmo_id'),
            'is_archived': conv_data.get('is_archived', False),
            'conversation_template_id': conv_data.get('conversation_template_id'),
            'plugin_ids': conv_data.get('plugin_ids', []),
            'safe_urls': conv_data.get('safe_urls', []),
        }
        
        # Remove None values
        return {k: v for k, v in metadata.items() if v is not None}
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        if timestamp is None:
            return None
        
        if isinstance(timestamp, (int, float)):
            try:
                return datetime.fromtimestamp(timestamp)
            except:
                return None
        
        if isinstance(timestamp, str):
            formats = [
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(timestamp, fmt)
                except:
                    continue

        return None

    def _resolve_and_copy_image(self, file_service_url: str) -> Optional[str]:
        """
        Resolve file-service:// or sediment:// URL to local file and copy to media directory

        Args:
            file_service_url: URL like "file-service://file-ABC123", "sediment://file_123", etc.

        Returns:
            Relative path like "media/uuid.png" or None if not found
        """
        if not self.source_dir or not self.media_dir:
            logger.debug(f"source_dir or media_dir not provided, skipping image: {file_service_url}")
            return None

        # Skip sediment:// URLs as files don't exist in exports
        if file_service_url.startswith('sediment://'):
            logger.debug(f"Skipping sediment:// URL (files not in export): {file_service_url}")
            return None

        import uuid
        import shutil
        from pathlib import Path

        # Extract file ID from URL
        file_id = file_service_url.replace('file-service://', '')

        # Search patterns:
        # 1. Main directory: {uuid}-{filename}.{ext}
        # 2. Main directory with file- prefix: file-{id}-{filename}.{ext}
        # 3. dalle-generations: file-{id}-{uuid}.{ext}

        source_path = None

        # Try main directory patterns
        for pattern in [f"{file_id}-*", f"file-{file_id}-*"]:
            matches = glob.glob(str(Path(self.source_dir) / pattern))
            if matches:
                source_path = Path(matches[0])
                break

        # Try dalle-generations directory
        if not source_path:
            dalle_dir = Path(self.source_dir) / 'dalle-generations'
            if dalle_dir.exists():
                for pattern in [f"file-{file_id}-*", f"{file_id}-*"]:
                    matches = glob.glob(str(dalle_dir / pattern))
                    if matches:
                        source_path = Path(matches[0])
                        break

        if not source_path or not source_path.exists():
            logger.warning(f"Could not find image file for {file_service_url}")
            return None

        # Generate new UUID for media file
        new_uuid = str(uuid.uuid4())
        ext = source_path.suffix
        dest_filename = f"{new_uuid}{ext}"
        dest_path = Path(self.media_dir) / dest_filename

        # Copy file
        try:
            shutil.copy2(source_path, dest_path)
            logger.debug(f"Copied {source_path.name} -> {dest_filename}")
            return f"media/{dest_filename}"
        except Exception as e:
            logger.error(f"Failed to copy image {source_path}: {e}")
            return None

    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import OpenAI conversation data

        Args:
            data: Conversation data (JSON string or dict/list)
            **kwargs: Additional arguments
                - source_dir: Directory containing the export (for resolving image paths)
                - media_dir: Target directory for copying images (from ConversationDB)
        """
        if isinstance(data, str):
            data = json.loads(data)

        if not isinstance(data, list):
            data = [data]

        # Get source directory for images
        self.source_dir = kwargs.get('source_dir')
        self.media_dir = kwargs.get('media_dir')

        conversations = []

        for conv_data in data:
            # Skip invalid entries
            if not conv_data or not isinstance(conv_data, dict):
                logger.warning(f"Skipping invalid conversation data: {type(conv_data)}")
                continue

            # Extract basic info
            conv_id = conv_data.get('conversation_id') or conv_data.get('id', '')
            title = conv_data.get('title', 'Untitled Conversation')
            
            # Detect model
            model = self._detect_model(conv_data)
            
            # Create metadata
            metadata = ConversationMetadata(
                version="2.0.0",
                format="openai",
                source="ChatGPT",
                model=model,
                created_at=self._parse_timestamp(conv_data.get('create_time')) or datetime.now(),
                updated_at=self._parse_timestamp(conv_data.get('update_time')) or datetime.now(),
                tags=['openai', model.lower().replace(' ', '-')] if model else ['openai'],
                custom_data=self._extract_metadata(conv_data)
            )
            
            # Create conversation tree
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )
            
            # Process mapping
            mapping = conv_data.get('mapping', {})

            # First pass: identify structural nodes (no message content)
            # These are conversation root placeholders like "client-created-root"
            # They're part of OpenAI's tree structure but aren't actual messages
            structural_nodes = set()
            for node_id, node_data in mapping.items():
                if not node_data or not node_data.get('message'):
                    structural_nodes.add(node_id)

            # Second pass: process actual messages
            for msg_id, msg_data in mapping.items():
                if not msg_data or 'message' not in msg_data:
                    continue

                msg_info = msg_data['message']
                if not msg_info:
                    continue
                
                # Extract role
                author = msg_info.get('author', {})
                if isinstance(author, dict):
                    role_str = author.get('role', 'user')
                else:
                    role_str = str(author) if author else 'user'
                
                role = MessageRole.from_string(role_str)
                
                # Extract content
                content_data = msg_info.get('content', {})
                content = MessageContent()
                
                if isinstance(content_data, dict):
                    content.type = content_data.get('content_type', 'text')
                    parts = content_data.get('parts', [])
                    
                    # Handle different part types
                    text_parts = []
                    for part in parts:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict):
                            # Handle multimodal content
                            if 'asset_pointer' in part:
                                # This is an image or other media asset
                                asset_url = part.get('asset_pointer')
                                if asset_url:
                                    # Resolve and copy image to media directory
                                    media_path = self._resolve_and_copy_image(asset_url)
                                    if media_path:
                                        # Safely get nested metadata
                                        metadata = part.get('metadata') or {}
                                        dalle_data = metadata.get('dalle') if isinstance(metadata, dict) else {}
                                        prompt = dalle_data.get('prompt') if isinstance(dalle_data, dict) else None
                                        content.add_image(
                                            url=media_path,
                                            caption=prompt
                                        )
                            elif 'image_url' in part:
                                # Direct image URL
                                img_data = part['image_url']
                                if isinstance(img_data, str):
                                    # Try to resolve if it's a file-service URL
                                    if img_data.startswith('file-service://'):
                                        media_path = self._resolve_and_copy_image(img_data)
                                        if media_path:
                                            content.add_image(url=media_path)
                                    else:
                                        content.add_image(url=img_data)
                                elif isinstance(img_data, dict):
                                    url = img_data.get('url')
                                    if url and url.startswith('file-service://'):
                                        media_path = self._resolve_and_copy_image(url)
                                        if media_path:
                                            content.add_image(
                                                url=media_path,
                                                caption=img_data.get('detail')
                                            )
                                    else:
                                        content.add_image(
                                            url=url,
                                            caption=img_data.get('detail')
                                        )
                            elif 'text' in part:
                                text_parts.append(part['text'])
                            elif 'content' in part:
                                text_parts.append(str(part['content']))
                            
                            # Store original part in metadata
                            if 'content_type' in part:
                                content.metadata['part_types'] = content.metadata.get('part_types', [])
                                content.metadata['part_types'].append(part['content_type'])
                    
                    content.text = '\n'.join(text_parts) if text_parts else ''
                    content.parts = parts
                    
                    # Handle tool/function calls
                    if 'tool_calls' in content_data:
                        for tool_data in content_data['tool_calls']:
                            tool_call = ToolCall(
                                id=tool_data.get('id', ''),
                                name=tool_data.get('function', {}).get('name', ''),
                                arguments=json.loads(tool_data.get('function', {}).get('arguments', '{}'))
                                    if tool_data.get('function', {}).get('arguments') else {}
                            )
                            content.tool_calls.append(tool_call)
                    
                    # Handle function calls (older format)
                    if 'function_call' in content_data:
                        func_call = content_data['function_call']
                        tool_call = ToolCall(
                            name=func_call.get('name', ''),
                            arguments=json.loads(func_call.get('arguments', '{}'))
                                if func_call.get('arguments') else {}
                        )
                        content.tool_calls.append(tool_call)
                    
                elif isinstance(content_data, str):
                    content.text = content_data
                
                # Determine parent_id
                # If parent is a structural node (conversation root), set parent_id to None
                # This correctly translates OpenAI's tree structure to our unified model
                parent = msg_data.get('parent')
                parent_id = None if (parent is None or parent in structural_nodes) else parent

                # Create message
                message = Message(
                    id=msg_id,
                    role=role,
                    content=content,
                    timestamp=self._parse_timestamp(msg_info.get('create_time')),
                    parent_id=parent_id,
                    metadata={
                        'status': msg_info.get('status'),
                        'end_turn': msg_info.get('end_turn'),
                        'weight': msg_info.get('weight'),
                        'recipient': msg_info.get('recipient'),
                    }
                )
                
                # Add to tree
                tree.add_message(message)
            
            conversations.append(tree)
        
        return conversations