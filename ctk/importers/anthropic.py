"""
Anthropic/Claude conversation importer
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ctk.core.models import (ContentType, ConversationMetadata,
                             ConversationTree, MediaContent, Message,
                             MessageContent, MessageRole, ReasoningBlock,
                             ToolCall)
from ctk.core.plugin import ImporterPlugin
from ctk.core.utils import parse_timestamp


class AnthropicImporter(ImporterPlugin):
    """Import Anthropic/Claude conversation exports"""

    name = "anthropic"
    description = "Import Claude conversation exports"
    version = "1.0.0"
    supported_formats = ["claude", "anthropic"]

    def validate(self, data: Any) -> bool:
        """Check if data is Anthropic format"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError, ValueError):
                return False

        if isinstance(data, list) and data:
            sample = data[0]
        elif isinstance(data, dict):
            sample = data
        else:
            return False

        # Check for Anthropic format markers
        # Look for chat_messages field (required) and optionally uuid or name
        has_chat_messages = "chat_messages" in sample
        has_messages = "messages" in sample
        has_uuid = "uuid" in sample
        has_name = "name" in sample

        # Valid if has chat_messages (primary Anthropic export format)
        # Or has messages/uuid with sender pattern
        if has_chat_messages:
            return True

        if has_messages and (has_uuid or has_name):
            return True

        # Also check in the content of messages if available
        has_sender = False
        if "messages" in sample and sample["messages"]:
            has_sender = any("sender" in msg for msg in sample["messages"])
        else:
            has_sender = "sender" in str(sample)

        return has_uuid and has_sender

    def _detect_model(self, conv_data: Dict) -> str:
        """Detect the Claude model used"""
        model = conv_data.get("model", "")

        # Map model identifiers to readable names
        model_map = {
            "claude-3-opus": "Claude 3 Opus",
            "claude-3-sonnet": "Claude 3 Sonnet",
            "claude-3-haiku": "Claude 3 Haiku",
            "claude-3.5-sonnet": "Claude 3.5 Sonnet",
            "claude-2.1": "Claude 2.1",
            "claude-2": "Claude 2",
            "claude-instant-1.2": "Claude Instant 1.2",
            "claude-instant": "Claude Instant",
        }

        # Sort by key length DESC so specific prefixes (claude-3-opus) match
        # before generic ones (claude-3). See CLAUDE.md for the gotcha.
        sorted_map = sorted(model_map.items(), key=lambda kv: len(kv[0]), reverse=True)

        for key, value in sorted_map:
            if key in model.lower():
                return value

        # Check in messages for model info
        messages = conv_data.get("messages", [])
        for msg in messages:
            if "model" in msg:
                for key, value in sorted_map:
                    if key in msg["model"].lower():
                        return value

        return model if model else "Claude"

    def _process_content_blocks(self, blocks: list, content: MessageContent) -> List[str]:
        """Extract structured data from Anthropic content blocks.

        Returns the text fragments found (used as fallback message text when
        no top-level text exists). Always runs, even when top-level text is
        present, so tool calls and reasoning are never dropped (F2).
        """
        text_parts: List[str] = []
        for part in blocks:
            if isinstance(part, str):
                text_parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            part_type = part.get("type", "")
            if part_type == "text":
                text_parts.append(part.get("text", ""))
            elif part_type == "image":
                source = part.get("source", {})
                if isinstance(source, dict):
                    if source.get("type") == "base64":
                        content.add_image(
                            data=source.get("data"),
                            mime_type=source.get("media_type", "image/png"),
                        )
                    elif "url" in source:
                        content.add_image(url=source["url"])
            elif part_type == "tool_use":
                content.tool_calls.append(
                    ToolCall(
                        id=part.get("id", ""),
                        name=part.get("name", ""),
                        arguments=part.get("input", {}),
                    )
                )
            elif part_type == "tool_result":
                tool_id = part.get("tool_use_id", "")
                for tc in content.tool_calls:
                    if tc.id == tool_id:
                        tc.result = part.get("content", "")
                        tc.status = "completed"
                        if part.get("is_error"):
                            tc.status = "failed"
                            tc.error = str(part.get("content", ""))
                        break
            elif part_type in ("thinking", "redacted_thinking"):
                content.reasoning.append(
                    ReasoningBlock(
                        text=part.get("thinking", part.get("data", "")),
                        extra={k: v for k, v in part.items()
                               if k not in ("type", "thinking")},
                    )
                )
            elif part_type == "token_budget":
                content.metadata["token_budget"] = part
            else:
                content.metadata["attachments"] = content.metadata.get("attachments", [])
                content.metadata["attachments"].append(part)
        return text_parts

    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import Anthropic conversation data"""
        if isinstance(data, str):
            data = json.loads(data)

        if not isinstance(data, list):
            data = [data]

        conversations = []

        for conv_data in data:
            # Extract basic info
            conv_id = conv_data.get("uuid") or conv_data.get("id", str(uuid.uuid4()))
            title = conv_data.get("name") or conv_data.get(
                "title", "Untitled Conversation"
            )

            # Detect model
            model = self._detect_model(conv_data)

            # Create metadata
            metadata = ConversationMetadata(
                version="2.0.0",
                format="anthropic",
                source="Claude",
                model=model,
                created_at=parse_timestamp(conv_data.get("created_at"))
                or datetime.now(),
                updated_at=parse_timestamp(conv_data.get("updated_at"))
                or datetime.now(),
                tags=["anthropic", "claude"]
                + (
                    [model.lower().replace(" ", "-")]
                    if model.lower() != "claude"
                    else []
                ),
                custom_data={
                    "project_uuid": conv_data.get("project_uuid"),
                    "account_uuid": (
                        conv_data.get("account", {}).get("uuid")
                        if isinstance(conv_data.get("account"), dict)
                        else conv_data.get("account_uuid")
                    ),
                    "summary": conv_data.get("summary"),
                },
            )

            # Create conversation tree
            tree = ConversationTree(id=conv_id, title=title, metadata=metadata)

            # Process messages - handle both 'messages' and 'chat_messages' fields
            messages = conv_data.get("messages", conv_data.get("chat_messages", []))
            parent_id = None

            for idx, msg_data in enumerate(messages):
                # Generate message ID
                msg_id = msg_data.get("uuid") or msg_data.get("id", f"msg_{idx}")

                # Extract role
                sender = msg_data.get("sender", msg_data.get("role", "user"))
                role = MessageRole.from_string(sender)

                # Extract content
                content = MessageContent()

                # Structured pass over content blocks first (never skipped: F2).
                block_text_parts: List[str] = []
                raw_blocks = msg_data.get("content")
                if isinstance(raw_blocks, list):
                    block_text_parts = self._process_content_blocks(raw_blocks, content)
                    content.parts = raw_blocks
                elif isinstance(raw_blocks, str):
                    block_text_parts = [raw_blocks]

                # Top-level text is the export's own rendering and wins when present.
                top_text = msg_data.get("text")
                if top_text:
                    content.text = top_text
                elif block_text_parts:
                    content.text = "\n".join(block_text_parts)

                # Attachments (independent of which text source won).
                if "attachments" in msg_data:
                    for attachment in msg_data["attachments"]:
                        if isinstance(attachment, dict):
                            file_name = attachment.get("file_name", "")
                            file_type = attachment.get("file_type", "")
                            if any(
                                ext in file_name.lower()
                                for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]
                            ):
                                content.add_image(path=file_name, mime_type=file_type)
                            elif file_name:
                                content.documents.append(
                                    MediaContent(
                                        type=ContentType.DOCUMENT,
                                        path=file_name,
                                        mime_type=file_type,
                                    )
                                )
                    if msg_data["attachments"]:
                        attachment_text = "\n\nAttachments: " + ", ".join(
                            a.get("file_name", "Unknown")
                            for a in msg_data["attachments"]
                        )
                        content.text = (content.text or "") + attachment_text

                # Create message
                message = Message(
                    id=msg_id,
                    role=role,
                    content=content,
                    timestamp=parse_timestamp(msg_data.get("created_at")),
                    parent_id=parent_id,
                    metadata={
                        "files": msg_data.get("files", []),
                        "feedback": msg_data.get("feedback"),
                    },
                )

                # Add to tree (linear for now, as Anthropic exports are typically linear)
                tree.add_message(message)
                parent_id = msg_id

            conversations.append(tree)

        return conversations
