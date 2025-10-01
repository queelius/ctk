"""
Filesystem-based importer for coding agent conversations
"""

import json
import os
from pathlib import Path
from typing import List, Any, Dict, Optional
from datetime import datetime
import uuid
import sqlite3

from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata
)


class FilesystemCodingImporter(ImporterPlugin):
    """Import coding agent conversations from filesystem locations"""
    
    name = "filesystem_coding"
    description = "Import coding agent conversations from filesystem (.vscode, .cursor, etc.)"
    version = "1.0.0"
    supported_formats = ["filesystem", "vscode", "cursor_dir", "copilot_dir"]
    
    # Known coding agent storage locations
    KNOWN_PATHS = {
        'copilot': [
            '.vscode/copilot',
            '.vscode-server/data/User/workspaceStorage',
            '~/.config/Code/User/workspaceStorage',
            '~/Library/Application Support/Code/User/workspaceStorage',
            '%APPDATA%/Code/User/workspaceStorage',
        ],
        'cursor': [
            '.cursor',
            '~/.cursor',
            '~/Library/Application Support/Cursor',
            '%APPDATA%/Cursor',
        ],
        'claude_code': [
            '.claude',
            '~/.claude-code',
            '~/Library/Application Support/Claude',
        ],
        'codeium': [
            '.codeium',
            '~/.codeium/chat_history',
        ],
    }
    
    def validate(self, data: Any) -> bool:
        """Check if data is a filesystem path with coding agent data"""
        if isinstance(data, str):
            # Only check path if string is reasonable length for a path
            if len(data) < 4096:  # Max path length on most systems
                try:
                    path = Path(data).expanduser()
                    if path.exists() and path.is_dir():
                        # Check for known patterns
                        return self._detect_agent_type(path) is not None
                except (OSError, ValueError):
                    # Path is invalid or too long
                    pass
        return False
    
    def _detect_agent_type(self, path: Path) -> Optional[str]:
        """Detect which coding agent this directory belongs to"""
        path_str = str(path).lower()
        
        if '.vscode' in path_str or 'copilot' in path_str:
            return 'copilot'
        elif '.cursor' in path_str or 'cursor' in path_str:
            return 'cursor'
        elif '.claude' in path_str or 'claude' in path_str:
            return 'claude_code'
        elif '.codeium' in path_str or 'codeium' in path_str:
            return 'codeium'
        
        # Check for specific files that indicate agent type
        if (path / 'copilot.db').exists() or (path / 'copilot_conversations.json').exists():
            return 'copilot'
        if (path / 'cursor.db').exists() or (path / 'conversations.db').exists():
            return 'cursor'
        if (path / 'chat_history.json').exists() or (path / 'sessions.json').exists():
            return 'generic'
        
        return None
    
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import from filesystem path"""
        path = Path(data).expanduser()
        agent_type = self._detect_agent_type(path)
        
        if agent_type == 'copilot':
            return self._import_copilot(path)
        elif agent_type == 'cursor':
            return self._import_cursor(path)
        elif agent_type == 'claude_code':
            return self._import_claude_code(path)
        elif agent_type == 'codeium':
            return self._import_codeium(path)
        else:
            return self._import_generic(path)
    
    def _import_copilot(self, path: Path) -> List[ConversationTree]:
        """Import GitHub Copilot conversations"""
        conversations = []
        
        # Look for Copilot SQLite database
        db_paths = list(path.glob('**/copilot*.db')) + list(path.glob('**/state.vscdb'))
        
        for db_path in db_paths:
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Try to find conversation tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row['name'] for row in cursor.fetchall()]
                
                # Look for conversation-related tables
                for table in tables:
                    if 'conversation' in table.lower() or 'chat' in table.lower():
                        cursor.execute(f"SELECT * FROM {table}")
                        rows = cursor.fetchall()
                        
                        for row in rows:
                            conv = self._parse_copilot_row(dict(row))
                            if conv:
                                conversations.append(conv)
                
                conn.close()
            except Exception as e:
                print(f"Error reading {db_path}: {e}")
        
        # Also look for JSON files
        json_paths = list(path.glob('**/*conversation*.json')) + \
                    list(path.glob('**/*chat*.json'))
        
        for json_path in json_paths:
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            conv = self._parse_copilot_json(item)
                            if conv:
                                conversations.append(conv)
                    else:
                        conv = self._parse_copilot_json(data)
                        if conv:
                            conversations.append(conv)
            except Exception as e:
                print(f"Error reading {json_path}: {e}")
        
        return conversations
    
    def _parse_copilot_row(self, row: Dict) -> Optional[ConversationTree]:
        """Parse a Copilot database row into a conversation"""
        try:
            conv_id = row.get('id', str(uuid.uuid4()))
            title = row.get('title', 'Copilot Session')
            
            metadata = ConversationMetadata(
                version="2.0.0",
                format="copilot",
                source="GitHub Copilot",
                model="Copilot",
                created_at=self._parse_timestamp(row.get('created_at')) or datetime.now(),
                updated_at=self._parse_timestamp(row.get('updated_at')) or datetime.now(),
                tags=['coding', 'copilot', 'github'],
                custom={
                    'workspace': row.get('workspace'),
                    'language': row.get('language'),
                }
            )
            
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )
            
            # Parse messages if stored as JSON
            if 'messages' in row and row['messages']:
                messages = json.loads(row['messages']) if isinstance(row['messages'], str) else row['messages']
                parent_id = None
                
                for idx, msg in enumerate(messages):
                    msg_id = f"msg_{idx}"
                    role = MessageRole.from_string(msg.get('role', 'user'))
                    
                    content = MessageContent(
                        text=msg.get('content', ''),
                        metadata={'file_context': msg.get('file_context')}
                    )
                    
                    message = Message(
                        id=msg_id,
                        role=role,
                        content=content,
                        parent_id=parent_id
                    )
                    
                    tree.add_message(message, parent_id=parent_id)
                    parent_id = msg_id
            
            return tree
        except Exception:
            return None
    
    def _parse_copilot_json(self, data: Dict) -> Optional[ConversationTree]:
        """Parse Copilot JSON data"""
        try:
            conv_id = data.get('conversationId', str(uuid.uuid4()))
            title = data.get('title', 'Copilot Session')
            
            metadata = ConversationMetadata(
                version="2.0.0",
                format="copilot",
                source="GitHub Copilot",
                model="Copilot",
                created_at=datetime.now(),
                tags=['coding', 'copilot', 'github'],
                custom=data.get('metadata', {})
            )
            
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )
            
            turns = data.get('turns', data.get('messages', []))
            parent_id = None
            
            for turn in turns:
                # Handle request/response pairs
                if 'request' in turn:
                    req_id = f"{turn.get('id', uuid.uuid4())}_req"
                    req_content = MessageContent(
                        text=turn['request'].get('message', ''),
                        metadata={'context': turn['request'].get('context')}
                    )
                    req_msg = Message(
                        id=req_id,
                        role=MessageRole.USER,
                        content=req_content,
                        parent_id=parent_id
                    )
                    tree.add_message(req_msg, parent_id=parent_id)
                    parent_id = req_id
                
                if 'response' in turn:
                    resp_id = f"{turn.get('id', uuid.uuid4())}_resp"
                    resp_content = MessageContent(
                        text=turn['response'].get('message', ''),
                        metadata={'suggestions': turn['response'].get('suggestions')}
                    )
                    resp_msg = Message(
                        id=resp_id,
                        role=MessageRole.ASSISTANT,
                        content=resp_content,
                        parent_id=parent_id
                    )
                    tree.add_message(resp_msg, parent_id=parent_id)
                    parent_id = resp_id
            
            return tree if tree.message_map else None
        except Exception:
            return None
    
    def _import_cursor(self, path: Path) -> List[ConversationTree]:
        """Import Cursor conversations"""
        conversations = []
        
        # Cursor typically uses SQLite or JSON files
        db_paths = list(path.glob('**/*.db')) + list(path.glob('**/*.sqlite'))
        
        for db_path in db_paths:
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                
                # Look for conversation tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%conversation%'")
                tables = cursor.fetchall()
                
                for table in tables:
                    cursor.execute(f"SELECT * FROM {table[0]}")
                    for row in cursor.fetchall():
                        # Parse Cursor specific format
                        conv = self._parse_cursor_conversation(row)
                        if conv:
                            conversations.append(conv)
                
                conn.close()
            except Exception as e:
                print(f"Error reading Cursor database: {e}")
        
        return conversations
    
    def _parse_cursor_conversation(self, row: Any) -> Optional[ConversationTree]:
        """Parse Cursor conversation data"""
        # Implementation would depend on Cursor's actual format
        # This is a placeholder
        return None
    
    def _import_claude_code(self, path: Path) -> List[ConversationTree]:
        """Import Claude Code conversations"""
        # Would implement based on Claude Code's storage format
        return []
    
    def _import_codeium(self, path: Path) -> List[ConversationTree]:
        """Import Codeium conversations"""
        # Would implement based on Codeium's storage format
        return []
    
    def _import_generic(self, path: Path) -> List[ConversationTree]:
        """Generic import for unknown coding agents"""
        conversations = []
        
        # Look for any JSON files that might contain conversations
        for json_path in path.glob('**/*.json'):
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    
                    # Try to detect if it's conversation data
                    if self._looks_like_conversation(data):
                        conv = self._parse_generic_conversation(data)
                        if conv:
                            conversations.append(conv)
            except Exception:
                continue
        
        return conversations
    
    def _looks_like_conversation(self, data: Any) -> bool:
        """Heuristic to detect conversation data"""
        if isinstance(data, dict):
            conv_keys = ['messages', 'turns', 'interactions', 'conversation']
            return any(key in data for key in conv_keys)
        return False
    
    def _parse_generic_conversation(self, data: Dict) -> Optional[ConversationTree]:
        """Parse generic conversation format"""
        # Generic parsing logic
        return None
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse various timestamp formats"""
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp)
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp)
            except:
                return None
        return None
    
    @classmethod
    def scan_for_conversations(cls, base_path: Path = Path.home()) -> List[Path]:
        """Scan filesystem for potential conversation directories"""
        found_paths = []
        
        for agent, paths in cls.KNOWN_PATHS.items():
            for path_pattern in paths:
                path = Path(path_pattern).expanduser()
                if path.exists():
                    found_paths.append(path)
        
        return found_paths