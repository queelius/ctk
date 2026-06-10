"""Importer for CTK's own canonical JSON export (the inverse of the json
exporter's 'ctk' format_style). Preserves ids, tree structure, media, tool
calls, and reasoning exactly."""

import json
import logging
import uuid
from typing import Any, List

from ctk.core.models import ConversationMetadata, ConversationTree, Message
from ctk.core.plugin import ImporterPlugin

logger = logging.getLogger(__name__)


class CTKImporter(ImporterPlugin):
    """Import conversations from CTK's native JSON export."""

    name = "ctk"
    description = "Import CTK's own canonical JSON export (lossless inverse)"
    version = "1.0.0"
    supported_formats = ["ctk"]
    # Must outrank greedy validators (gemini/jsonl both claim dicts with a
    # 'conversations' key); see F5 in the round-trip-fidelity design doc.
    detection_priority = 100

    def validate(self, data: Any) -> bool:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                return False
        if not isinstance(data, dict):
            return False
        conversations = data.get("conversations")
        if not isinstance(conversations, list):
            return False
        if data.get("format") == "ctk":
            return True
        # Structural fallback: ctk conversations carry a message map plus
        # root_message_ids, which no other supported export format does.
        if conversations and isinstance(conversations[0], dict):
            first = conversations[0]
            return (
                isinstance(first.get("messages"), dict) and "root_message_ids" in first
            )
        return False

    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        if isinstance(data, str):
            data = json.loads(data)

        conversations: List[ConversationTree] = []
        for conv_data in data.get("conversations", []):
            if not isinstance(conv_data, dict):
                logger.warning(
                    "CTKImporter: skipping non-dict conversation entry (%s)",
                    type(conv_data).__name__,
                )
                continue
            try:
                metadata = (
                    ConversationMetadata.from_dict(conv_data["metadata"])
                    if isinstance(conv_data.get("metadata"), dict)
                    else ConversationMetadata()
                )
                tree = ConversationTree(
                    id=conv_data.get("id", str(uuid.uuid4())),
                    title=conv_data.get("title"),
                    metadata=metadata,
                )
                # Faithful inverse: populate the map and roots directly rather
                # than via add_message, which would overwrite metadata.updated_at
                # and re-derive roots (see CLAUDE.md gotchas).
                for msg_id, msg_dict in conv_data.get("messages", {}).items():
                    tree.message_map[msg_id] = Message.from_dict(msg_dict)
                tree.root_message_ids = list(conv_data.get("root_message_ids", []))
                conversations.append(tree)
            except (KeyError, ValueError, TypeError, AttributeError) as exc:
                logger.warning(
                    "CTKImporter: skipping malformed conversation entry: %s", exc
                )
                continue

        return conversations
