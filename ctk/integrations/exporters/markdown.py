"""
Markdown exporter for CTK conversations
"""

from typing import List, Dict, Any, Optional, TextIO
import io
import os
import re
from datetime import datetime
from pathlib import Path

from ctk.core.plugin import ExporterPlugin
from ctk.core.models import ConversationTree, Message, MessageRole


class MarkdownExporter(ExporterPlugin):
    """Export conversations to Markdown format"""

    name = "markdown"
    description = "Export conversations to Markdown format"
    version = "1.0.0"

    def validate(self, data: Any) -> bool:
        """Validate if this exporter can handle the data"""
        # Markdown exporter can handle any conversation data
        return True

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        """Export conversations to markdown"""
        return self.export_conversations(conversations, **kwargs)

    def export_to_file(self, conversations: List[ConversationTree], file_path: str, **kwargs) -> None:
        """
        Export conversations to markdown file(s).

        If file_path is a directory (or has no extension), exports one file per conversation.
        Otherwise exports all conversations to a single file.
        """
        path = Path(file_path)

        # Determine if we should output to directory (one file per conversation)
        # Directory mode if: path is existing directory, ends with /, or has no extension
        is_directory_mode = (
            path.is_dir() or
            file_path.endswith('/') or
            file_path.endswith(os.sep) or
            (not path.suffix and not path.exists())
        )

        if is_directory_mode:
            self._export_to_directory(conversations, path, **kwargs)
        else:
            # Single file mode
            content = self.export_conversations(conversations, **kwargs)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')

    def _export_to_directory(
        self,
        conversations: List[ConversationTree],
        output_dir: Path,
        **kwargs
    ) -> None:
        """Export each conversation to its own markdown file"""
        output_dir.mkdir(parents=True, exist_ok=True)

        for conv in conversations:
            # Generate filename: YYYY-MM-DD-title-id.md
            filename = self._generate_filename(conv)
            file_path = output_dir / filename

            # Export single conversation
            content = self.export_conversations([conv], **kwargs)
            file_path.write_text(content, encoding='utf-8')

    def _generate_filename(self, conv: ConversationTree) -> str:
        """Generate a filename for a conversation"""
        # Get date prefix
        date_str = ""
        if conv.metadata and conv.metadata.created_at:
            date_str = conv.metadata.created_at.strftime("%Y-%m-%d-")

        # Sanitize title
        title = conv.title or "untitled"
        # Remove or replace problematic characters
        sanitized = re.sub(r'[^\w\s-]', '', title.lower())
        sanitized = re.sub(r'[\s_]+', '-', sanitized)
        sanitized = re.sub(r'-+', '-', sanitized).strip('-')
        # Truncate to reasonable length
        sanitized = sanitized[:50]

        # Add short ID for uniqueness
        short_id = conv.id[:8] if conv.id else "unknown"

        return f"{date_str}{sanitized}-{short_id}.md"

    def export_conversations(
        self,
        conversations: List[ConversationTree],
        output_file: Optional[str] = None,
        path_selection: str = "longest",
        include_metadata: bool = True,
        include_timestamps: bool = True,
        include_tree_structure: bool = False,
        **kwargs
    ) -> str:
        """
        Export conversations to Markdown format

        Args:
            conversations: List of ConversationTree objects to export
            output_file: Optional file path to write to
            path_selection: Path selection strategy (longest, first, last, all)
            include_metadata: Include conversation metadata
            include_timestamps: Include message timestamps
            include_tree_structure: Show tree structure for branching conversations
        """
        output = io.StringIO()

        for i, conv in enumerate(conversations):
            if i > 0:
                output.write("\n---\n\n")

            # Write conversation header
            self._write_conversation_header(output, conv, include_metadata)

            if include_tree_structure and self._has_branches(conv):
                # Show tree structure
                self._write_tree_structure(output, conv, include_timestamps)
            else:
                # Show linear conversation(s)
                if path_selection == "all":
                    paths = conv.get_all_paths()
                    for j, path in enumerate(paths):
                        if j > 0:
                            output.write("\n#### Alternative Path\n\n")
                        self._write_conversation_path(output, path, include_timestamps)
                else:
                    path = self._select_path(conv, path_selection)
                    self._write_conversation_path(output, path, include_timestamps)

        content = output.getvalue()

        # Write to file if specified
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)

        return content

    def _write_conversation_header(
        self,
        output: TextIO,
        conv: ConversationTree,
        include_metadata: bool
    ):
        """Write conversation header with metadata"""
        # Title
        title = conv.title or f"Conversation {conv.id[:8]}"
        output.write(f"# {title}\n\n")

        if include_metadata and conv.metadata:
            output.write("## Metadata\n\n")

            # Format metadata as a table
            output.write("| Field | Value |\n")
            output.write("|-------|-------|\n")

            if conv.metadata.created_at:
                output.write(f"| Created | {conv.metadata.created_at.isoformat()} |\n")
            if conv.metadata.updated_at:
                output.write(f"| Updated | {conv.metadata.updated_at.isoformat()} |\n")
            if conv.metadata.source:
                output.write(f"| Source | {conv.metadata.source} |\n")
            if conv.metadata.model:
                output.write(f"| Model | {conv.metadata.model} |\n")
            if conv.metadata.tags:
                output.write(f"| Tags | {', '.join(conv.metadata.tags)} |\n")
            if conv.metadata.project:
                output.write(f"| Project | {conv.metadata.project} |\n")

            output.write("\n")

    def _write_conversation_path(
        self,
        output: TextIO,
        path: List[Message],
        include_timestamps: bool
    ):
        """Write a single conversation path"""
        output.write("## Conversation\n\n")

        for msg in path:
            # Role header
            role_emoji = self._get_role_emoji(msg.role)
            role_name = self._get_role_display_name(msg.role)

            output.write(f"### {role_emoji} {role_name}")

            if include_timestamps and msg.timestamp:
                output.write(f" _{msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}_")

            output.write("\n\n")

            # Message content
            content_text = msg.content.get_text() if msg.content else ""
            if content_text:
                # Handle code blocks properly
                if "```" in content_text:
                    # Already has code blocks, just write as-is
                    output.write(f"{content_text}\n\n")
                else:
                    # Regular text
                    output.write(f"{content_text}\n\n")

            # Handle media content
            if msg.content and msg.content.has_media():
                if msg.content.images:
                    for img in msg.content.images:
                        caption = img.caption or "Image"
                        if img.url:
                            output.write(f"![{caption}]({img.url})\n\n")
                        else:
                            output.write(f"*[{caption} - embedded]*\n\n")

                if msg.content.documents:
                    output.write("**Attachments:**\n")
                    for doc in msg.content.documents:
                        name = doc.caption or "Document"
                        if doc.url:
                            output.write(f"- [{name}]({doc.url})\n")
                        else:
                            output.write(f"- {name}\n")
                    output.write("\n")

            # Handle tool calls
            if msg.content and msg.content.has_tools():
                output.write("**Tool Calls:**\n")
                for tool in msg.content.tool_calls:
                    output.write(f"- `{tool.name}`")
                    if tool.status == "completed" and tool.result:
                        output.write(f" → {tool.result}")
                    elif tool.status == "failed" and tool.error:
                        output.write(f" ❌ {tool.error}")
                    output.write("\n")
                output.write("\n")

    def _write_tree_structure(
        self,
        output: TextIO,
        conv: ConversationTree,
        include_timestamps: bool
    ):
        """Write conversation as a tree structure"""
        output.write("## Conversation Tree\n\n")
        output.write("```\n")

        for root_id in conv.root_message_ids:
            self._write_tree_node(output, conv, root_id, "", include_timestamps)

        output.write("```\n\n")

    def _write_tree_node(
        self,
        output: TextIO,
        conv: ConversationTree,
        message_id: str,
        prefix: str,
        include_timestamps: bool,
        is_last: bool = True
    ):
        """Recursively write tree nodes"""
        msg = conv.message_map.get(message_id)
        if not msg:
            return

        # Determine the tree characters
        if prefix:
            branch = "└── " if is_last else "├── "
        else:
            branch = ""

        # Write the node
        role_emoji = self._get_role_emoji(msg.role)
        content_preview = self._get_content_preview(msg)

        line = f"{prefix}{branch}{role_emoji} {msg.role.value}: {content_preview}"

        if include_timestamps and msg.timestamp:
            line += f" [{msg.timestamp.strftime('%H:%M:%S')}]"

        output.write(line + "\n")

        # Get children and recurse
        children = conv.get_children(message_id)
        for i, child in enumerate(children):
            is_last_child = (i == len(children) - 1)

            if prefix:
                new_prefix = prefix + ("    " if is_last else "│   ")
            else:
                new_prefix = ""

            self._write_tree_node(
                output, conv, child.id, new_prefix,
                include_timestamps, is_last_child
            )

    def _has_branches(self, conv: ConversationTree) -> bool:
        """Check if conversation has branching paths"""
        for msg_id, msg in conv.message_map.items():
            children = conv.get_children(msg_id)
            if len(children) > 1:
                return True
        return False

    def _select_path(self, conv: ConversationTree, selection: str) -> List[Message]:
        """Select a path based on strategy"""
        if selection == "longest":
            return conv.get_longest_path()
        elif selection == "first":
            paths = conv.get_all_paths()
            return paths[0] if paths else []
        elif selection == "last":
            paths = conv.get_all_paths()
            return paths[-1] if paths else []
        else:
            return conv.get_longest_path()

    def _get_role_emoji(self, role: MessageRole) -> str:
        """Get emoji for message role"""
        emoji_map = {
            MessageRole.USER: "👤",
            MessageRole.ASSISTANT: "🤖",
            MessageRole.SYSTEM: "⚙️",
            MessageRole.TOOL: "🔧",
            MessageRole.FUNCTION: "⚡",
            MessageRole.TOOL_RESULT: "📊"
        }
        return emoji_map.get(role, "💬")

    def _get_role_display_name(self, role: MessageRole) -> str:
        """Get display name for role"""
        name_map = {
            MessageRole.USER: "User",
            MessageRole.ASSISTANT: "Assistant",
            MessageRole.SYSTEM: "System",
            MessageRole.TOOL: "Tool",
            MessageRole.FUNCTION: "Function",
            MessageRole.TOOL_RESULT: "Tool Result"
        }
        return name_map.get(role, role.value.title())

    def _get_content_preview(self, msg: Message, max_length: int = 50) -> str:
        """Get a preview of message content"""
        if not msg.content:
            return "[empty]"

        text = msg.content.get_text()
        if not text:
            if msg.content.has_media():
                return "[media content]"
            elif msg.content.has_tools():
                return "[tool call]"
            else:
                return "[empty]"

        # Clean up and truncate
        text = text.replace('\n', ' ').strip()
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text


# Register the exporter
exporter = MarkdownExporter()