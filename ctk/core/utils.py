"""
Shared utility functions for CTK.

This module provides common functionality used across importers, exporters,
and other components to reduce code duplication.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


def parse_timestamp(
    value: Union[int, float, str, datetime, None], default: Optional[datetime] = None
) -> Optional[datetime]:
    """
    Parse timestamp from various formats.

    Handles multiple input formats including:
    - Unix epoch timestamps (int/float)
    - ISO 8601 format strings (with or without timezone)
    - datetime objects (passthrough)
    - None (returns default)

    Args:
        value: Timestamp as Unix epoch (int/float), ISO string, or datetime
        default: Default value if parsing fails

    Returns:
        datetime object or default value if parsing fails

    Examples:
        >>> parse_timestamp(1704067200)  # Unix timestamp
        datetime.datetime(2024, 1, 1, 0, 0)

        >>> parse_timestamp("2024-01-01T00:00:00Z")
        datetime.datetime(2024, 1, 1, 0, 0)

        >>> parse_timestamp(None, datetime.now())
        # Returns datetime.now()
    """
    if value is None:
        return default

    if isinstance(value, datetime):
        return value

    # Unix timestamp
    if isinstance(value, (int, float)):
        try:
            # Handle milliseconds (timestamps > 1e10 are usually in milliseconds)
            timestamp = value
            if timestamp > 1e10:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp)
        except (ValueError, OSError, OverflowError) as e:
            logger.debug(f"Failed to parse Unix timestamp {value}: {e}")
            return default

    # ISO string
    if isinstance(value, str):
        # Try fromisoformat first (handles most ISO 8601 variants)
        try:
            normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass

        # Try strptime for non-ISO formats
        custom_formats = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S",
            "%m/%d/%Y %H:%M:%S",
        ]

        for fmt in custom_formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        logger.debug(f"Could not parse timestamp string: {value}")
        return default

    logger.debug(f"Unsupported timestamp type: {type(value).__name__}")
    return default


def try_parse_json(data: Any) -> Optional[dict]:
    """
    Safely parse JSON data.

    Handles multiple input types:
    - dict: returned as-is
    - str: parsed as JSON
    - other: returns None

    Args:
        data: Data to parse (dict, str, or other)

    Returns:
        Parsed dict or None if parsing fails

    Examples:
        >>> try_parse_json('{"key": "value"}')
        {'key': 'value'}

        >>> try_parse_json({"key": "value"})
        {'key': 'value'}

        >>> try_parse_json("invalid json")
        None
    """
    if isinstance(data, dict):
        return data

    if isinstance(data, str):
        try:
            return json.loads(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"Failed to parse JSON: {e}")
            return None

    return None
