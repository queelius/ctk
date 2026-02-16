"""
Cursor-based pagination utilities for CTK.

Cursors encode the position in a result set as an opaque base64 string
containing the sort key (updated_at) and conversation ID for deterministic
keyset pagination.
"""

import base64
import json
from datetime import datetime
from typing import Tuple


def encode_cursor(updated_at: datetime, conversation_id: str) -> str:
    """Encode pagination cursor as URL-safe base64 JSON.

    Args:
        updated_at: Timestamp of the last item on current page
        conversation_id: ID of the last item on current page

    Returns:
        URL-safe base64-encoded cursor string
    """
    data = {
        "u": updated_at.isoformat(),
        "id": conversation_id,
    }
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_cursor(cursor: str) -> Tuple[datetime, str]:
    """Decode pagination cursor.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        Tuple of (updated_at, conversation_id)

    Raises:
        ValueError: If cursor is not valid base64 or JSON
        KeyError: If cursor JSON is missing required fields
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
    except Exception as e:
        raise ValueError(f"Invalid cursor encoding: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid cursor JSON: {e}") from e

    return datetime.fromisoformat(data["u"]), data["id"]
