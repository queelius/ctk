"""CSV/TSV exporter for CTK conversations."""

import csv
import io
from typing import Any, List

from ctk.core.models import ConversationTree
from ctk.core.plugin import ExporterPlugin


class CSVExporter(ExporterPlugin):
    """Export conversations as CSV/TSV files for spreadsheets and data analysis."""

    name = "csv"
    description = "Export conversations as CSV files for spreadsheets and data analysis"
    version = "1.0.0"
    supported_formats = ["csv", "tsv"]

    def validate(self, data: Any) -> bool:
        """Validate that data contains ConversationTree objects."""
        if isinstance(data, list):
            return all(isinstance(c, ConversationTree) for c in data)
        return isinstance(data, ConversationTree)

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> str:
        """Export conversations to CSV format.

        Args:
            conversations: List of ConversationTree objects to export.
            mode: "conversations" (default) for summary rows, "messages" for
                  per-message rows.
            delimiter: Field delimiter character. Default "," for CSV, use
                       "\\t" for TSV.
            path_selection: Which path to follow in branching conversations.
                           "longest" (default), "first", or "last".

        Returns:
            CSV-formatted string.
        """
        mode = kwargs.get("mode", "conversations")
        delimiter = kwargs.get("delimiter", ",")
        path_selection = kwargs.get("path_selection", "longest")

        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter)

        if mode == "messages":
            self._export_messages(writer, conversations, path_selection)
        else:
            self._export_conversations(writer, conversations)

        return output.getvalue()

    def _export_conversations(self, writer, conversations):
        """Export conversation-level summary rows."""
        headers = [
            "id",
            "title",
            "source",
            "model",
            "created_at",
            "updated_at",
            "message_count",
            "tags",
            "starred",
            "pinned",
            "archived",
        ]
        writer.writerow(headers)

        for conv in conversations:
            meta = conv.metadata
            writer.writerow(
                [
                    conv.id,
                    conv.title or "",
                    meta.source or "",
                    meta.model or "",
                    meta.created_at.isoformat() if meta.created_at else "",
                    meta.updated_at.isoformat() if meta.updated_at else "",
                    len(conv.message_map),
                    ";".join(meta.tags) if meta.tags else "",
                    "true" if meta.starred_at else "false",
                    "true" if meta.pinned_at else "false",
                    "true" if meta.archived_at else "false",
                ]
            )

    def _export_messages(self, writer, conversations, path_selection):
        """Export message-level detail rows."""
        headers = [
            "conversation_id",
            "conversation_title",
            "message_id",
            "role",
            "content",
            "timestamp",
            "parent_id",
        ]
        writer.writerow(headers)

        for conv in conversations:
            path = self._select_path(conv, path_selection)

            for msg in path:
                content = (
                    msg.content.get_text()
                    if hasattr(msg.content, "get_text")
                    else str(msg.content)
                )
                writer.writerow(
                    [
                        conv.id,
                        conv.title or "",
                        msg.id,
                        msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                        content,
                        msg.timestamp.isoformat() if msg.timestamp else "",
                        msg.parent_id or "",
                    ]
                )

    def _select_path(self, conv, path_selection):
        """Select a message path based on the path_selection strategy."""
        if path_selection == "longest":
            return conv.get_longest_path()
        elif path_selection == "first":
            paths = conv.get_all_paths()
            return paths[0] if paths else []
        elif path_selection == "last":
            paths = conv.get_all_paths()
            return paths[-1] if paths else []
        else:
            return conv.get_longest_path()


# Register the exporter
exporter = CSVExporter()
