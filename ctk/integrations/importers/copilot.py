"""
GitHub Copilot Chat importer
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Any, Dict, Optional
from datetime import datetime
import uuid
import os

from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole, ConversationMetadata
)


class CopilotImporter(ImporterPlugin):
    """Import GitHub Copilot Chat conversations"""
    
    name = "copilot"
    description = "Import GitHub Copilot Chat conversations from VS Code"
    version = "1.0.0"
    supported_formats = ["copilot", "github_copilot"]
    
    # Copilot storage locations by platform
    STORAGE_PATHS = {
        'darwin': [
            '~/Library/Application Support/Code/User/workspaceStorage',
            '~/Library/Application Support/Code - Insiders/User/workspaceStorage',
        ],
        'linux': [
            '~/.config/Code/User/workspaceStorage',
            '~/.config/Code - Insiders/User/workspaceStorage',
            '~/.vscode-server/data/User/workspaceStorage',
        ],
        'win32': [
            '%APPDATA%/Code/User/workspaceStorage',
            '%APPDATA%/Code - Insiders/User/workspaceStorage',
        ]
    }
    
    def validate(self, data: Any) -> bool:
        """Check if data is Copilot format or path"""
        if isinstance(data, str):
            path = Path(data).expanduser()
            if path.exists():
                # Check for Copilot-specific files
                if path.is_dir():
                    return any([
                        (path / 'state.vscdb').exists(),
                        any(path.glob('**/copilot*.db')),
                        any(path.glob('**/github.copilot*/cache/*.json'))
                    ])
                elif path.suffix in ['.vscdb', '.db']:
                    return 'copilot' in path.name.lower() or 'state.vscdb' in path.name
        
        # Check JSON structure
        if isinstance(data, dict):
            return 'copilot' in str(data).lower() and 'turns' in data
        
        return False
    
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import Copilot conversations"""
        if isinstance(data, str):
            path = Path(data).expanduser()
            if path.exists():
                if path.is_dir():
                    return self._import_from_directory(path)
                else:
                    return self._import_from_file(path)
        
        # Direct JSON data
        if isinstance(data, dict):
            conv = self._parse_copilot_data(data)
            return [conv] if conv else []
        
        return []
    
    def _import_from_directory(self, path: Path) -> List[ConversationTree]:
        """Import from VS Code workspace storage directory"""
        conversations = []
        
        # Look for Copilot extension data
        copilot_paths = list(path.glob('**/github.copilot*'))
        
        for copilot_path in copilot_paths:
            # Check cache directory for conversation JSON files
            cache_dir = copilot_path / 'cache'
            if cache_dir.exists():
                for json_file in cache_dir.glob('*.json'):
                    try:
                        with open(json_file, 'r') as f:
                            data = json.load(f)
                            conv = self._parse_copilot_data(data)
                            if conv:
                                conversations.append(conv)
                    except Exception as e:
                        print(f"Error reading {json_file}: {e}")
        
        # Also check for SQLite databases
        for db_path in path.glob('**/*.vscdb'):
            convs = self._import_from_vscdb(db_path)
            conversations.extend(convs)
        
        return conversations
    
    def _import_from_file(self, path: Path) -> List[ConversationTree]:
        """Import from specific file"""
        if path.suffix == '.json':
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    conv = self._parse_copilot_data(data)
                    return [conv] if conv else []
            except Exception:
                return []
        elif path.suffix in ['.vscdb', '.db']:
            return self._import_from_vscdb(path)
        
        return []
    
    def _import_from_vscdb(self, db_path: Path) -> List[ConversationTree]:
        """Import from VS Code state database"""
        conversations = []
        
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # VS Code stores extension data in ItemTable
            cursor.execute("""
                SELECT key, value FROM ItemTable 
                WHERE key LIKE '%copilot%' OR key LIKE '%github%'
            """)
            
            for row in cursor.fetchall():
                try:
                    value = json.loads(row['value'])
                    if self._is_conversation_data(value):
                        conv = self._parse_copilot_data(value)
                        if conv:
                            conversations.append(conv)
                except Exception:
                    continue
            
            conn.close()
        except Exception as e:
            print(f"Error reading VS Code database: {e}")
        
        return conversations
    
    def _is_conversation_data(self, data: Any) -> bool:
        """Check if data contains conversation information"""
        if isinstance(data, dict):
            return any(key in data for key in ['turns', 'messages', 'conversation', 'thread'])
        return False
    
    def _parse_copilot_data(self, data: Dict) -> Optional[ConversationTree]:
        """Parse Copilot conversation data"""
        try:
            # Extract conversation ID and title
            conv_id = data.get('threadId', data.get('conversationId', str(uuid.uuid4())))
            title = data.get('title', 'Copilot Chat')
            
            # Try to extract workspace info
            workspace = data.get('workspace', {})
            if workspace.get('name'):
                title = f"{title} - {workspace['name']}"
            
            # Create metadata
            metadata = ConversationMetadata(
                version="2.0.0",
                format="copilot",
                source="GitHub Copilot",
                model="Copilot (GPT-4)",
                created_at=self._parse_timestamp(data.get('createdAt')) or datetime.now(),
                updated_at=self._parse_timestamp(data.get('updatedAt')) or datetime.now(),
                tags=['coding', 'copilot', 'github', 'vscode'],
                custom={
                    'workspace': workspace,
                    'language': data.get('language'),
                    'activeFile': data.get('activeFile'),
                    'gitRepo': data.get('gitRepo'),
                }
            )
            
            # Add language tag if present
            if data.get('language'):
                metadata.tags.append(f"lang:{data['language'].lower()}")
            
            # Create conversation tree
            tree = ConversationTree(
                id=conv_id,
                title=title,
                metadata=metadata
            )
            
            # Parse turns/messages
            turns = data.get('turns', data.get('messages', []))
            parent_id = None
            
            for idx, turn in enumerate(turns):
                # Handle Copilot's request/response structure
                if isinstance(turn, dict):
                    # User request
                    if 'request' in turn or 'query' in turn:
                        req_data = turn.get('request', turn.get('query', {}))
                        req_id = f"{conv_id}_turn{idx}_req"
                        
                        req_content = MessageContent(
                            text=req_data.get('message', req_data.get('text', '')),
                            metadata={
                                'activeSelection': req_data.get('activeSelection'),
                                'visibleRange': req_data.get('visibleRange'),
                                'activeFile': req_data.get('activeFile'),
                            }
                        )
                        
                        req_msg = Message(
                            id=req_id,
                            role=MessageRole.USER,
                            content=req_content,
                            timestamp=self._parse_timestamp(turn.get('timestamp')),
                            parent_id=parent_id
                        )
                        
                        tree.add_message(req_msg, parent_id=parent_id)
                        parent_id = req_id
                    
                    # Copilot response
                    if 'response' in turn or 'reply' in turn:
                        resp_data = turn.get('response', turn.get('reply', {}))
                        resp_id = f"{conv_id}_turn{idx}_resp"
                        
                        resp_content = MessageContent(
                            text=resp_data.get('message', resp_data.get('text', '')),
                            metadata={
                                'suggestions': resp_data.get('suggestions', []),
                                'codeBlocks': resp_data.get('codeBlocks', []),
                                'references': resp_data.get('references', []),
                            }
                        )
                        
                        # Extract code blocks
                        if 'codeBlocks' in resp_data:
                            resp_content.parts = resp_data['codeBlocks']
                        
                        resp_msg = Message(
                            id=resp_id,
                            role=MessageRole.ASSISTANT,
                            content=resp_content,
                            timestamp=self._parse_timestamp(turn.get('timestamp')),
                            parent_id=parent_id,
                            metadata={
                                'model': 'copilot',
                                'confidence': resp_data.get('confidence'),
                            }
                        )
                        
                        tree.add_message(resp_msg, parent_id=parent_id)
                        parent_id = resp_id
            
            return tree if tree.message_map else None
            
        except Exception as e:
            print(f"Error parsing Copilot data: {e}")
            return None
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        if timestamp is None:
            return None
        
        if isinstance(timestamp, (int, float)):
            # Handle milliseconds
            if timestamp > 1e10:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp)
        
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                return None
        
        return None
    
    @classmethod
    def find_copilot_data(cls) -> List[Path]:
        """Find Copilot data directories on the system"""
        import platform
        
        system = platform.system().lower()
        if system == 'windows':
            system = 'win32'
        
        paths = cls.STORAGE_PATHS.get(system, cls.STORAGE_PATHS['linux'])
        found_paths = []
        
        for path_pattern in paths:
            path = Path(path_pattern).expanduser()
            if system == 'win32':
                path = Path(os.path.expandvars(path_pattern))
            
            if path.exists():
                # Each workspace has its own storage
                for workspace_dir in path.iterdir():
                    if workspace_dir.is_dir():
                        # Check for Copilot extension
                        copilot_dirs = list(workspace_dir.glob('*github.copilot*'))
                        if copilot_dirs:
                            found_paths.extend(copilot_dirs)
        
        return found_paths