"""
Importer for coding agent conversations (Claude Code, GitHub Copilot Chat, Cursor, etc.)
"""

import json
from typing import List, Any, Dict, Optional
from datetime import datetime
import uuid
import re

from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata
)


class CodingAgentImporter(ImporterPlugin):
    """Import coding agent conversation exports"""
    
    name = "coding_agent"
    description = "Import coding agent conversations (Claude Code, Copilot, Cursor, etc.)"
    version = "1.0.0"
    supported_formats = ["claude_code", "copilot", "cursor", "codeium", "coding"]
    
    def validate(self, data: Any) -> bool:
        """Check if data is from a coding agent"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                return False
        
        # Look for coding-specific markers
        data_str = str(data).lower()
        coding_markers = [
            'workspace', 'file_path', 'code_block', 'language',
            'repository', 'commit', 'diff', 'terminal',
            'claude_code', 'copilot', 'cursor', 'codeium',
            'vscode', 'editor', 'diagnostics'
        ]
        
        return any(marker in data_str for marker in coding_markers)
    
    def _detect_agent(self, data: Any) -> tuple[str, str]:
        """Detect which coding agent this is from"""
        data_str = str(data).lower()
        
        agents = {
            'claude_code': ('Claude Code', 'Anthropic'),
            'copilot': ('GitHub Copilot', 'Microsoft/OpenAI'),
            'cursor': ('Cursor', 'Cursor AI'),
            'codeium': ('Codeium', 'Codeium'),
            'cody': ('Cody', 'Sourcegraph'),
            'tabnine': ('Tabnine', 'Tabnine'),
            'amazon_codewhisperer': ('CodeWhisperer', 'Amazon'),
        }
        
        for key, (name, provider) in agents.items():
            if key in data_str:
                return name, provider
        
        return 'Coding Agent', 'Unknown'
    
    def _extract_code_blocks(self, text: str) -> List[Dict[str, str]]:
        """Extract code blocks from text"""
        code_blocks = []
        
        # Match fenced code blocks
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for lang, code in matches:
            code_blocks.append({
                'type': 'code',
                'language': lang or 'plaintext',
                'content': code.strip()
            })
        
        return code_blocks
    
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import coding agent conversation data"""
        if isinstance(data, str):
            data = json.loads(data)
        
        if not isinstance(data, list):
            data = [data]
        
        conversations = []
        
        for conv_data in data:
            # Detect agent type
            agent_name, provider = self._detect_agent(conv_data)
            
            # Extract basic info
            conv_id = conv_data.get('id', str(uuid.uuid4()))
            title = conv_data.get('title', 'Coding Session')
            
            # Look for workspace/project info
            workspace = conv_data.get('workspace', {})
            project_name = workspace.get('name', conv_data.get('project_name'))
            if project_name:
                title = f"{title} - {project_name}"
            
            # Create metadata
            metadata = ConversationMetadata(
                version="2.0.0",
                format="coding_agent",
                source=agent_name,
                model=conv_data.get('model', agent_name),
                created_at=self._parse_timestamp(conv_data.get('created_at')) or datetime.now(),
                updated_at=self._parse_timestamp(conv_data.get('updated_at')) or datetime.now(),
                tags=['coding', agent_name.lower().replace(' ', '-'), provider.lower()],
                custom={
                    'workspace': workspace,
                    'repository': conv_data.get('repository'),
                    'branch': conv_data.get('branch'),
                    'files_modified': conv_data.get('files_modified', []),
                    'language': conv_data.get('language'),
                    'framework': conv_data.get('framework'),
                }
            )
            
            # Add language/framework tags
            if 'language' in conv_data:
                metadata.tags.append(f"lang:{conv_data['language'].lower()}")
            if 'framework' in conv_data:
                metadata.tags.append(f"framework:{conv_data['framework'].lower()}")
            
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )
            
            # Process messages
            messages = conv_data.get('messages', conv_data.get('interactions', []))
            parent_id = None
            
            for idx, msg_data in enumerate(messages):
                msg_id = msg_data.get('id', f"msg_{idx}")
                
                # Determine role
                role_str = msg_data.get('role', msg_data.get('author', 'user'))
                if role_str.lower() in ['agent', 'assistant', 'ai', 'model']:
                    role = MessageRole.ASSISTANT
                elif role_str.lower() in ['tool', 'function', 'command', 'terminal']:
                    role = MessageRole.TOOL
                else:
                    role = MessageRole.from_string(role_str)
                
                # Extract content
                content = MessageContent()
                
                # Handle different content formats
                if 'content' in msg_data:
                    if isinstance(msg_data['content'], str):
                        content.text = msg_data['content']
                        # Extract code blocks
                        code_blocks = self._extract_code_blocks(content.text)
                        if code_blocks:
                            content.metadata['code_blocks'] = code_blocks
                    elif isinstance(msg_data['content'], dict):
                        content.text = msg_data['content'].get('text', '')
                        if 'code' in msg_data['content']:
                            content.metadata['code'] = msg_data['content']['code']
                        if 'file_path' in msg_data['content']:
                            content.metadata['file_path'] = msg_data['content']['file_path']
                
                # Handle tool calls (file edits, terminal commands, etc.)
                if 'tool_calls' in msg_data:
                    content.metadata['tool_calls'] = msg_data['tool_calls']
                    content.type = 'tool_use'
                
                if 'command' in msg_data:
                    content.metadata['command'] = msg_data['command']
                    content.type = 'command'
                
                # File context
                if 'file_context' in msg_data:
                    content.metadata['file_context'] = msg_data['file_context']
                
                # Diagnostics/errors
                if 'diagnostics' in msg_data:
                    content.metadata['diagnostics'] = msg_data['diagnostics']
                
                message = Message(
                    id=msg_id,
                    role=role,
                    content=content,
                    timestamp=self._parse_timestamp(msg_data.get('timestamp')),
                    parent_id=parent_id,
                    metadata={
                        'file_path': msg_data.get('file_path'),
                        'line_number': msg_data.get('line_number'),
                        'commit_sha': msg_data.get('commit_sha'),
                        'diff': msg_data.get('diff'),
                    }
                )
                
                tree.add_message(message, parent_id=parent_id)
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