"""
GitHub Copilot Chat importer
Based on copikit approach for finding and parsing chat sessions
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
    version = "2.0.0"
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
            # Only check path if string is reasonable length for a path
            if len(data) < 4096:  # Max path length on most systems
                try:
                    path = Path(data).expanduser()
                    if path.exists():
                        # Check for Copilot-specific directories
                        if path.is_dir():
                            # Check for chatSessions directory (the actual chat data)
                            if (path / 'chatSessions').exists():
                                return True
                            # Check if it's a workspace storage root with chat sessions
                            for subdir in path.iterdir():
                                if subdir.is_dir() and (subdir / 'chatSessions').exists():
                                    return True
                        elif path.suffix == '.json':
                            # Check if it looks like a chat session file
                            try:
                                with open(path) as f:
                                    data = json.load(f)
                                    return 'requests' in data or 'creationDate' in data
                            except:
                                return False
                except (OSError, ValueError):
                    # Path is invalid or too long
                    pass

        # Check JSON structure for chat session
        if isinstance(data, dict):
            return 'requests' in data or 'sessionId' in data

        return False

    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import Copilot conversation data"""
        if isinstance(data, str):
            # Check if it's a file/directory path
            path = Path(data).expanduser()
            if path.exists():
                if path.is_dir():
                    return self._import_from_directory(path)
                else:
                    return self._import_from_file(path)

        # Direct JSON data
        if isinstance(data, dict):
            conv = self._parse_chat_session(data)
            return [conv] if conv else []

        return []

    def _import_from_directory(self, path: Path) -> List[ConversationTree]:
        """Import from VS Code workspace storage directory"""
        conversations = []

        # Check if this is a workspace directory or the workspaceStorage root
        ws_dirs = []
        if (path / "chatSessions").is_dir() or (path / "workspace.json").exists():
            # This is a workspace directory
            ws_dirs = [path]
        else:
            # This is the workspaceStorage root, iterate through workspace directories
            ws_dirs = [d for d in path.iterdir() if d.is_dir()]

        for ws_dir in ws_dirs:
            # Get project info from workspace.json if available
            project_path = None
            ws_json = ws_dir / "workspace.json"
            if ws_json.exists():
                try:
                    ws_data = json.loads(ws_json.read_text())
                    project_path = ws_data.get("folder")
                except Exception:
                    pass

            # Look for chat sessions
            chat_dir = ws_dir / "chatSessions"
            if chat_dir.is_dir():
                for session_file in chat_dir.glob("*.json"):
                    try:
                        with open(session_file, 'r') as f:
                            session_data = json.load(f)
                            conv = self._parse_chat_session(session_data,
                                                           session_id=session_file.stem,
                                                           project_path=project_path)
                            if conv:
                                conversations.append(conv)
                    except Exception as e:
                        print(f"Error reading {session_file}: {e}")

            # Also look for editing sessions if needed (future enhancement)
            edit_dir = ws_dir / "chatEditingSessions"
            if edit_dir.is_dir():
                # We could parse editing sessions here if desired
                pass

        return conversations

    def _import_from_file(self, path: Path) -> List[ConversationTree]:
        """Import from specific file"""
        if path.suffix == '.json':
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    conv = self._parse_chat_session(data)
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
                        conv = self._parse_chat_session(value)
                        if conv:
                            conversations.append(conv)
                except Exception:
                    continue

            conn.close()
        except Exception as e:
            print(f"Error reading database {db_path}: {e}")

        return conversations

    def _is_conversation_data(self, data: Any) -> bool:
        """Check if data looks like conversation data"""
        if not isinstance(data, dict):
            return False
        return 'requests' in data or 'messages' in data or 'sessionId' in data

    def _parse_chat_session(self, data: Dict[str, Any], session_id: str = None,
                            project_path: str = None) -> Optional[ConversationTree]:
        """Parse Copilot chat session data (based on copikit approach)"""
        # Extract session info
        conv_id = session_id or data.get('sessionId') or str(uuid.uuid4())

        # Extract timestamps
        created_at = None
        updated_at = None
        if 'creationDate' in data:
            created_at = datetime.fromtimestamp(data['creationDate'] / 1000)
        if 'lastMessageDate' in data:
            updated_at = datetime.fromtimestamp(data['lastMessageDate'] / 1000)

        # Build title from first user message or use default
        title = 'Copilot Chat'
        requests = data.get('requests', [])
        if requests and 'message' in requests[0]:
            first_prompt = requests[0]['message'].get('text', '')
            if first_prompt:
                # Use first line or first 50 chars as title
                title = first_prompt.split('\n')[0][:50]
                if len(title) == 50:
                    title += '...'

        # Extract project name from path
        project_name = None
        if project_path:
            project_name = Path(project_path.replace('file://', '')).name

        # Create metadata
        metadata = ConversationMetadata(
            version="2.0.0",
            format="copilot",
            source="GitHub Copilot",
            model="Copilot",
            created_at=created_at or datetime.now(),
            updated_at=updated_at or datetime.now(),
            tags=['copilot', 'vscode', 'coding'],
            custom_data={
                'project_path': project_path,
                'project_name': project_name,
                'session_id': conv_id,
            }
        )

        # Add project tag if known
        if project_name:
            metadata.tags.append(f'project:{project_name}')

        tree = ConversationTree(
            id=conv_id,
            title=title,
            metadata=metadata
        )

        # Parse conversation turns (requests)
        parent_id = None

        for idx, turn in enumerate(requests):
            # Extract user message
            user_msg = turn.get('message', {}).get('text', '')
            if user_msg:
                user_msg_id = f"{conv_id}_user_{idx}"
                user_content = MessageContent(text=user_msg)

                # Check for file context
                variables = turn.get('variableData', {}).get('variables', [])
                for var in variables:
                    if var.get('kind') == 'file':
                        file_uri = var.get('value', {}).get('uri', {}).get('path')
                        if file_uri:
                            user_content.metadata['referenced_files'] = user_content.metadata.get('referenced_files', [])
                            user_content.metadata['referenced_files'].append(file_uri)

                user_message = Message(
                    id=user_msg_id,
                    role=MessageRole.USER,
                    content=user_content,
                    parent_id=parent_id
                )
                tree.add_message(user_message)
                parent_id = user_msg_id

            # Extract assistant response
            response_text = None

            # Try different response formats
            result_meta = turn.get('result', {}).get('metadata', {})
            if 'response' in result_meta:
                response_text = result_meta['response']
            elif 'response' in turn:
                # Concatenate response parts
                parts = []
                for part in turn['response']:
                    if isinstance(part, dict) and 'value' in part:
                        parts.append(part['value'])
                    elif isinstance(part, str):
                        parts.append(part)
                response_text = ''.join(parts)

            if response_text:
                assistant_msg_id = f"{conv_id}_assistant_{idx}"
                assistant_content = MessageContent(text=response_text)

                assistant_message = Message(
                    id=assistant_msg_id,
                    role=MessageRole.ASSISTANT,
                    content=assistant_content,
                    parent_id=parent_id
                )
                tree.add_message(assistant_message)
                parent_id = assistant_msg_id

        return tree if tree.message_map else None

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
                        # Check for chatSessions directory (the actual chat data)
                        chat_sessions = workspace_dir / 'chatSessions'
                        if chat_sessions.exists() and chat_sessions.is_dir():
                            # Check if there are actual session files
                            if list(chat_sessions.glob('*.json')):
                                found_paths.append(workspace_dir)

        return found_paths