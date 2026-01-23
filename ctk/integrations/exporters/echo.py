"""
ECHO format exporter for CTK conversations.

Exports conversations in an ECHO-compliant directory structure with:
- README.md explaining the archive
- conversations/ directory with per-conversation exports
- index.json listing all conversations
- Optional: SQLite database copy
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ctk.core.models import ConversationTree, Message
from ctk.core.plugin import ExporterPlugin


class ECHOExporter(ExporterPlugin):
    """Export conversations to ECHO-compliant directory structure."""

    name = "echo"
    description = "Export to ECHO-compliant archive format"
    version = "1.0.0"
    supported_formats = ["echo", "longecho", "archive"]

    def validate(self, data: Any) -> bool:
        """Validate data can be exported."""
        return isinstance(data, (list, ConversationTree))

    def export_data(
        self, conversations: List[ConversationTree], **kwargs
    ) -> Dict[str, Any]:
        """Export conversations - returns summary dict."""
        output_dir = kwargs.pop("output_dir", None)
        if not output_dir:
            raise ValueError("output_dir is required for ECHO export")

        return self.export_to_directory(conversations, output_dir, **kwargs)

    def export_to_file(
        self, conversations: List[ConversationTree], file_path: str, **kwargs
    ) -> None:
        """
        Export to ECHO directory structure.

        For ECHO export, file_path is treated as the output directory.
        """
        self.export_to_directory(conversations, file_path, **kwargs)

    def export_to_directory(
        self,
        conversations: List[ConversationTree],
        output_dir: str,
        db_path: Optional[str] = None,
        include_db: bool = False,
        owner_name: str = "Unknown",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Export conversations to ECHO-compliant directory structure.

        Args:
            conversations: List of conversations to export
            output_dir: Output directory path
            db_path: Path to source SQLite database (for optional copy)
            include_db: Whether to include SQLite database copy
            owner_name: Name of archive owner for README

        Returns:
            Summary dict with export statistics
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Create conversations directory
        conv_dir = output_path / "conversations"
        conv_dir.mkdir(exist_ok=True)

        # Build index
        index_data = {
            "format": "ctk-echo",
            "version": "1.0.0",
            "exported_at": datetime.now().isoformat(),
            "total_conversations": len(conversations),
            "conversations": [],
        }

        # Export each conversation
        for conv in conversations:
            conv_export_dir = conv_dir / conv.id
            conv_export_dir.mkdir(exist_ok=True)

            # Export conversation JSON (tree structure)
            conv_json = self._export_conversation_json(conv)
            (conv_export_dir / "conversation.json").write_text(
                json.dumps(conv_json, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Export conversation markdown (human-readable)
            conv_md = self._export_conversation_markdown(conv)
            (conv_export_dir / "conversation.md").write_text(conv_md, encoding="utf-8")

            # Export metadata
            metadata = self._export_conversation_metadata(conv)
            (conv_export_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Add to index
            index_data["conversations"].append(
                {
                    "id": conv.id,
                    "title": conv.title,
                    "created": (
                        conv.metadata.created_at.isoformat()
                        if conv.metadata.created_at
                        else None
                    ),
                    "source": conv.metadata.source,
                    "model": conv.metadata.model,
                    "message_count": len(conv.message_map),
                    "path": f"conversations/{conv.id}/",
                }
            )

        # Write index
        (output_path / "index.json").write_text(
            json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Optionally copy database
        if include_db and db_path:
            db_source = Path(db_path)
            if db_source.exists():
                shutil.copy2(db_source, output_path / "conversations.db")

        # Generate README
        readme_content = self._generate_readme(
            owner_name=owner_name,
            total_conversations=len(conversations),
            include_db=include_db and db_path is not None,
        )
        (output_path / "README.md").write_text(readme_content, encoding="utf-8")

        # Generate manifest.json for longecho integration
        include_site = kwargs.get("include_site", False)
        manifest = {
            "version": "1.0",
            "name": (
                f"{owner_name}'s Conversation Archive"
                if owner_name != "Unknown"
                else "Conversation Archive"
            ),
            "description": "AI conversation history",
            "type": "database",
            "browsable": True,
            "icon": "chat",
        }
        if include_site:
            manifest["site"] = "site/"

        (output_path / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Generate HTML site if requested
        if include_site:
            from ctk.integrations.exporters.html import HTMLExporter

            site_dir = output_path / "site"
            site_dir.mkdir(exist_ok=True)

            html_exporter = HTMLExporter()
            html_exporter.export_to_file(
                conversations,
                str(site_dir / "index.html"),
                embed=True,
                db_dir=kwargs.get("db_dir"),
            )

        return {
            "total_exported": len(conversations),
            "output_dir": str(output_path),
            "db_included": include_db and db_path is not None,
        }

    def _export_conversation_json(self, conv: ConversationTree) -> Dict[str, Any]:
        """Export conversation to tree-based JSON structure."""

        def message_to_dict(msg: Message) -> Dict[str, Any]:
            """Convert message to dict with children array."""
            result = {
                "id": msg.id,
                "role": msg.role.value,
                "content": msg.content.get_text() if msg.content else "",
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            }

            # Add children
            children = conv.get_children(msg.id)
            if children:
                result["children"] = [message_to_dict(child) for child in children]

            return result

        # Start from root messages
        root_messages = []
        for root_id in conv.root_message_ids:
            if root_id in conv.message_map:
                root_messages.append(message_to_dict(conv.message_map[root_id]))

        return {"id": conv.id, "title": conv.title, "messages": root_messages}

    def _export_conversation_markdown(self, conv: ConversationTree) -> str:
        """Export conversation to human-readable markdown."""
        lines = [f"# {conv.title or 'Untitled Conversation'}", ""]

        # Add metadata header
        if conv.metadata.created_at:
            lines.append(
                f"**Date:** {conv.metadata.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
        if conv.metadata.model:
            lines.append(f"**Model:** {conv.metadata.model}")
        if conv.metadata.source:
            lines.append(f"**Source:** {conv.metadata.source}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Get longest path for linear representation
        messages = conv.get_longest_path()

        for msg in messages:
            role = msg.role.value.upper()
            content = msg.content.get_text() if msg.content else ""

            lines.append(f"## {role}")
            lines.append("")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    def _export_conversation_metadata(self, conv: ConversationTree) -> Dict[str, Any]:
        """Export conversation metadata."""
        return {
            "id": conv.id,
            "title": conv.title,
            "source": conv.metadata.source,
            "model": conv.metadata.model,
            "created": (
                conv.metadata.created_at.isoformat() if conv.metadata.created_at else None
            ),
            "updated": (
                conv.metadata.updated_at.isoformat() if conv.metadata.updated_at else None
            ),
            "message_count": len(conv.message_map),
            "has_branches": len(conv.root_message_ids) > 1
            or any(len(conv.get_children(msg_id)) > 1 for msg_id in conv.message_map),
        }

    def _generate_readme(
        self, owner_name: str, total_conversations: int, include_db: bool
    ) -> str:
        """Generate ECHO-compliant README."""
        db_section = ""
        if include_db:
            db_section = """
### SQLite Database

The `conversations.db` file is a copy of the source database.

Key tables:
- `conversations`: id, title, created_at, source, model
- `messages`: id, conversation_id, parent_id, role, content, timestamp

Query example:
```sql
sqlite3 conversations.db "SELECT title FROM conversations ORDER BY created_at DESC LIMIT 10"
```
"""

        return f"""# Conversation Archive

{owner_name}'s AI conversation history.

Exported: {datetime.now().strftime('%Y-%m-%d')}
Total conversations: {total_conversations}

## Format

This is an ECHO-compliant archive. All data is in durable, open formats.

### Directory Structure

```
├── README.md                    # This file
├── index.json                   # List of all conversations
├── conversations/
│   ├── {{uuid}}/
│   │   ├── conversation.json    # Full tree structure
│   │   ├── conversation.md      # Human-readable (linear path)
│   │   └── metadata.json        # Conversation metadata
│   └── ...
{"├── conversations.db            # SQLite database (optional)" if include_db else ""}
```

### conversation.json

Each conversation is stored as a tree structure with nested children:

```json
{{
  "id": "uuid",
  "title": "Conversation Title",
  "messages": [
    {{
      "id": "msg-uuid",
      "role": "user",
      "content": "Message text",
      "timestamp": "2024-01-15T10:30:00",
      "children": [...]
    }}
  ]
}}
```

### conversation.md

Human-readable markdown with the longest conversation path.
{db_section}
## Exploring

1. **Browse**: Open `index.json` to see all conversations
2. **Read**: Open any `conversation.md` in a text editor
3. **Parse**: Use `conversation.json` for programmatic access
4. **Query**: Use SQLite browser on `conversations.db` (if included)

## About ECHO

ECHO is a philosophy for durable personal data archives.
Learn more: https://github.com/queelius/longecho

---

*Generated by ctk (Conversation Toolkit)*
"""


# Register the exporter
exporter = ECHOExporter()
