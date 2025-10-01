"""
JSON exporter for CTK conversations
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from ctk.core.plugin import ExporterPlugin
from ctk.core.models import ConversationTree, Message, MessageRole


class JSONExporter(ExporterPlugin):
    """Export conversations to JSON format"""

    name = "json"
    description = "Export conversations to JSON format"
    version = "1.0.0"

    def validate(self, data: Any) -> bool:
        """Validate if this exporter can handle the data"""
        # JSON exporter can handle any conversation data
        return True

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        """Export conversations to JSON"""
        return self.export_conversations(conversations, **kwargs)

    def export_conversations(
        self,
        conversations: List[ConversationTree],
        output_file: Optional[str] = None,
        format_style: str = "ctk",
        path_selection: str = "all",
        include_metadata: bool = True,
        pretty_print: bool = True,
        **kwargs
    ) -> str:
        """
        Export conversations to JSON format

        Args:
            conversations: List of ConversationTree objects to export
            output_file: Optional file path to write to
            format_style: JSON format style (ctk, openai, anthropic, generic)
            path_selection: Path selection strategy (longest, first, last, all)
            include_metadata: Include conversation metadata
            pretty_print: Pretty-print the JSON output
        """
        if format_style == "ctk":
            data = self._export_ctk_format(conversations, include_metadata)
        elif format_style == "openai":
            data = self._export_openai_format(conversations, path_selection)
        elif format_style == "anthropic":
            data = self._export_anthropic_format(conversations, path_selection)
        else:  # generic
            data = self._export_generic_format(conversations, path_selection, include_metadata)

        # Serialize to JSON
        if pretty_print:
            json_str = json.dumps(data, indent=2, ensure_ascii=False, default=self._json_serial)
        else:
            json_str = json.dumps(data, ensure_ascii=False, default=self._json_serial)

        # Write to file if specified
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_str)

        return json_str

    def _export_ctk_format(
        self,
        conversations: List[ConversationTree],
        include_metadata: bool
    ) -> Dict[str, Any]:
        """Export in native CTK format (preserves full tree structure)"""
        data = {
            "format": "ctk",
            "version": "2.0.0",
            "exported_at": datetime.now().isoformat(),
            "conversations": []
        }

        for conv in conversations:
            conv_data = {
                "id": conv.id,
                "title": conv.title,
                "messages": {},
                "root_message_ids": conv.root_message_ids
            }

            if include_metadata:
                conv_data["metadata"] = conv.metadata.to_dict()

            # Export all messages with full tree structure
            for msg_id, msg in conv.message_map.items():
                conv_data["messages"][msg_id] = {
                    "id": msg.id,
                    "role": msg.role.value,
                    "content": msg.content.to_dict() if msg.content else {},
                    "parent_id": msg.parent_id,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                    "metadata": msg.metadata
                }

            data["conversations"].append(conv_data)

        return data

    def _export_openai_format(
        self,
        conversations: List[ConversationTree],
        path_selection: str
    ) -> List[Dict[str, Any]]:
        """Export in OpenAI format"""
        exported_conversations = []

        for conv in conversations:
            if path_selection == "all":
                # Export each path as a separate conversation
                paths = conv.get_all_paths()
                for i, path in enumerate(paths):
                    conv_data = {
                        "title": f"{conv.title or 'Conversation'} - Path {i+1}" if len(paths) > 1 else conv.title,
                        "messages": self._messages_to_openai_format(path)
                    }
                    exported_conversations.append(conv_data)
            else:
                # Export selected path
                path = self._select_path(conv, path_selection)
                conv_data = {
                    "title": conv.title,
                    "messages": self._messages_to_openai_format(path)
                }
                exported_conversations.append(conv_data)

        return exported_conversations

    def _export_anthropic_format(
        self,
        conversations: List[ConversationTree],
        path_selection: str
    ) -> Dict[str, Any]:
        """Export in Anthropic format"""
        data = {
            "conversations": []
        }

        for conv in conversations:
            if path_selection == "all":
                paths = conv.get_all_paths()
                for i, path in enumerate(paths):
                    conv_data = {
                        "uuid": f"{conv.id}-{i}" if len(paths) > 1 else conv.id,
                        "name": f"{conv.title or 'Conversation'} - Path {i+1}" if len(paths) > 1 else conv.title,
                        "messages": self._messages_to_anthropic_format(path)
                    }
                    data["conversations"].append(conv_data)
            else:
                path = self._select_path(conv, path_selection)
                conv_data = {
                    "uuid": conv.id,
                    "name": conv.title,
                    "messages": self._messages_to_anthropic_format(path)
                }
                data["conversations"].append(conv_data)

        return data

    def _export_generic_format(
        self,
        conversations: List[ConversationTree],
        path_selection: str,
        include_metadata: bool
    ) -> List[Dict[str, Any]]:
        """Export in generic format"""
        exported_conversations = []

        for conv in conversations:
            base_data = {
                "id": conv.id,
                "title": conv.title
            }

            if include_metadata:
                base_data["metadata"] = {
                    "source": conv.metadata.source,
                    "model": conv.metadata.model,
                    "created_at": conv.metadata.created_at.isoformat() if conv.metadata.created_at else None,
                    "updated_at": conv.metadata.updated_at.isoformat() if conv.metadata.updated_at else None,
                    "tags": conv.metadata.tags,
                    "project": conv.metadata.project
                }

            if path_selection == "all":
                # Include all paths
                base_data["paths"] = []
                paths = conv.get_all_paths()
                for i, path in enumerate(paths):
                    path_data = {
                        "path_id": f"path_{i}",
                        "messages": self._messages_to_generic_format(path)
                    }
                    base_data["paths"].append(path_data)
            else:
                # Single path
                path = self._select_path(conv, path_selection)
                base_data["messages"] = self._messages_to_generic_format(path)

            exported_conversations.append(base_data)

        return exported_conversations

    def _messages_to_openai_format(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to OpenAI format"""
        formatted_messages = []

        for msg in messages:
            msg_data = {
                "role": self._map_role_to_openai(msg.role),
                "content": msg.content.get_text() if msg.content else ""
            }

            # Handle multimodal content
            if msg.content and msg.content.has_media():
                content_parts = []

                # Add text
                if msg.content.text:
                    content_parts.append({
                        "type": "text",
                        "text": msg.content.text
                    })

                # Add images
                for img in msg.content.images:
                    if img.url:
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": img.url}
                        })
                    elif img.data:
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{img.mime_type};base64,{img.data}"}
                        })

                if content_parts:
                    msg_data["content"] = content_parts

            # Handle tool calls
            if msg.content and msg.content.has_tools():
                msg_data["tool_calls"] = []
                for tool in msg.content.tool_calls:
                    msg_data["tool_calls"].append({
                        "id": tool.id,
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "arguments": json.dumps(tool.arguments)
                        }
                    })

            formatted_messages.append(msg_data)

        return formatted_messages

    def _messages_to_anthropic_format(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to Anthropic format"""
        formatted_messages = []

        for msg in messages:
            msg_data = {
                "role": self._map_role_to_anthropic(msg.role),
                "content": msg.content.get_text() if msg.content else "",
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
            }
            formatted_messages.append(msg_data)

        return formatted_messages

    def _messages_to_generic_format(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to generic format"""
        formatted_messages = []

        for msg in messages:
            msg_data = {
                "id": msg.id,
                "role": msg.role.value,
                "content": msg.content.to_dict() if msg.content else {},
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "metadata": msg.metadata
            }
            formatted_messages.append(msg_data)

        return formatted_messages

    def _map_role_to_openai(self, role: MessageRole) -> str:
        """Map MessageRole to OpenAI role"""
        mapping = {
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.SYSTEM: "system",
            MessageRole.TOOL: "tool",
            MessageRole.FUNCTION: "function",
            MessageRole.TOOL_RESULT: "tool"
        }
        return mapping.get(role, "user")

    def _map_role_to_anthropic(self, role: MessageRole) -> str:
        """Map MessageRole to Anthropic role"""
        mapping = {
            MessageRole.USER: "human",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.SYSTEM: "system",
            MessageRole.TOOL: "tool",
            MessageRole.FUNCTION: "function",
            MessageRole.TOOL_RESULT: "tool_result"
        }
        return mapping.get(role, "human")

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

    def _json_serial(self, obj):
        """JSON serializer for objects not serializable by default"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")


# Register the exporter
exporter = JSONExporter()