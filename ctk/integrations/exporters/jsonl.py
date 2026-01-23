"""
JSONL format exporter (for local LLMs and fine-tuning)
"""

import json
from typing import Any, Dict, List, Optional

from ctk.core.models import ConversationTree, Message
from ctk.core.plugin import ExporterPlugin
from ctk.core.sanitizer import Sanitizer


class JSONLExporter(ExporterPlugin):
    """Export to JSONL format for local LLMs"""

    name = "jsonl"
    description = "Export to JSONL format for local LLMs and fine-tuning"
    version = "1.0.0"
    supported_formats = ["jsonl", "local", "training"]

    def validate(self, data: Any) -> bool:
        """Validate data can be exported"""
        return isinstance(data, (list, ConversationTree))

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> str:
        """Export conversations to JSONL format"""
        output_lines = []

        # Get options
        format_type = kwargs.get("format", "messages")  # messages, chat, instruction
        include_system = kwargs.get("include_system", True)
        path_selection = kwargs.get("path_selection", "longest")
        include_metadata = kwargs.get("include_metadata", False)

        # Initialize sanitizer if requested
        sanitizer = None
        if kwargs.get("sanitize", False):
            sanitizer = Sanitizer(enabled=True)

        for conv in conversations:
            # Get the linear path based on selection
            if path_selection == "longest":
                messages = conv.get_longest_path()
            elif path_selection == "first":
                paths = conv.get_all_paths()
                messages = paths[0] if paths else []
            elif path_selection == "last":
                paths = conv.get_all_paths()
                messages = paths[-1] if paths else []
            else:
                messages = conv.get_longest_path()

            if format_type == "messages":
                # Standard messages format
                conv_data = {
                    "messages": self._format_messages(
                        messages, include_system, sanitizer
                    )
                }

                if include_metadata:
                    conv_data["metadata"] = {
                        "id": conv.id,
                        "title": conv.title,
                        "model": conv.metadata.model,
                        "source": conv.metadata.source,
                    }

                output_lines.append(json.dumps(conv_data, ensure_ascii=False))

            elif format_type == "chat":
                # Chat completion format (each turn is a separate line)
                formatted_messages = self._format_messages(
                    messages, include_system, sanitizer
                )
                for i in range(0, len(formatted_messages) - 1, 2):
                    if i + 1 < len(formatted_messages):
                        chat_pair = {
                            "messages": (
                                formatted_messages[max(0, i - 1) : i + 2]
                                if include_system and i > 0
                                else formatted_messages[i : i + 2]
                            )
                        }
                        output_lines.append(json.dumps(chat_pair, ensure_ascii=False))

            elif format_type == "instruction":
                # Instruction-following format
                system_msg = None
                user_msgs = []
                assistant_msgs = []

                for msg in messages:
                    if msg.role.value == "system":
                        system_msg = msg.content.get_text()
                    elif msg.role.value == "user":
                        user_msgs.append(msg.content.get_text())
                    elif msg.role.value == "assistant":
                        assistant_msgs.append(msg.content.get_text())

                # Create instruction-response pairs
                for user_msg, assistant_msg in zip(user_msgs, assistant_msgs):
                    inst_data = {
                        "instruction": self._sanitize_text(user_msg, sanitizer),
                        "response": self._sanitize_text(assistant_msg, sanitizer),
                    }
                    if system_msg and include_system:
                        inst_data["system"] = self._sanitize_text(system_msg, sanitizer)

                    output_lines.append(json.dumps(inst_data, ensure_ascii=False))

        return "\n".join(output_lines)

    def _format_messages(
        self,
        messages: List[Message],
        include_system: bool,
        sanitizer: Optional[Sanitizer],
    ) -> List[Dict]:
        """Format messages for export, preserving tool calls and multimodal content"""
        formatted = []

        for msg in messages:
            if not include_system and msg.role.value == "system":
                continue

            msg_data = {"role": msg.role.value}

            # Check if message has structured content (images, tools, etc.)
            has_media = msg.content and msg.content.has_media()
            has_tools = msg.content and msg.content.has_tools()

            if has_media or has_tools:
                # Build content parts array for structured content
                content_parts = []

                # Add text content if present
                text = msg.content.get_text() if msg.content else ""
                if text:
                    content_parts.append({
                        "type": "text",
                        "text": self._sanitize_text(text, sanitizer),
                    })

                # Add images
                if msg.content and msg.content.images:
                    for img in msg.content.images:
                        img_data = {"type": "image"}
                        if img.url:
                            img_data["url"] = img.url
                        if img.data:
                            img_data["data"] = img.data
                        if img.mime_type:
                            img_data["mime_type"] = img.mime_type
                        if img.caption:
                            img_data["caption"] = self._sanitize_text(img.caption, sanitizer)
                        content_parts.append(img_data)

                # Add audio
                if msg.content and msg.content.audio:
                    for audio in msg.content.audio:
                        audio_data = {"type": "audio"}
                        if audio.url:
                            audio_data["url"] = audio.url
                        if audio.data:
                            audio_data["data"] = audio.data
                        if audio.mime_type:
                            audio_data["mime_type"] = audio.mime_type
                        content_parts.append(audio_data)

                # Add tool calls
                if msg.content and msg.content.tool_calls:
                    for tool in msg.content.tool_calls:
                        tool_data = {
                            "type": "tool_call",
                            "id": tool.id,
                            "name": tool.name,
                            "arguments": tool.arguments,
                            "status": tool.status,
                        }
                        if tool.result is not None:
                            tool_data["result"] = tool.result
                        if tool.error:
                            tool_data["error"] = tool.error
                        content_parts.append(tool_data)

                msg_data["content"] = content_parts
            else:
                # Simple text content
                content = msg.content.get_text() if msg.content else ""
                msg_data["content"] = self._sanitize_text(content, sanitizer)

            # Also check for legacy parts structure
            if msg.content and msg.content.parts and len(msg.content.parts) > 1:
                # If we have parts but didn't process them above, preserve them
                if not has_media and not has_tools:
                    content_parts = []
                    for part in msg.content.parts:
                        if isinstance(part, str):
                            content_parts.append({
                                "type": "text",
                                "text": self._sanitize_text(part, sanitizer),
                            })
                        elif isinstance(part, dict):
                            # Preserve structured content
                            if sanitizer and sanitizer.enabled:
                                part = sanitizer.sanitize_dict(part)
                            content_parts.append(part)
                    msg_data["content"] = content_parts

            formatted.append(msg_data)

        return formatted

    def _sanitize_text(self, text: str, sanitizer: Optional[Sanitizer]) -> str:
        """Sanitize text if sanitizer is provided"""
        if sanitizer and sanitizer.enabled:
            return sanitizer.sanitize_text(text)
        return text


# Register the exporter
exporter = JSONLExporter()
