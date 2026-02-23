"""Shared validation utilities for MCP tool handlers."""

import re
from typing import Any, Optional

from ctk.core.constants import MAX_ID_LENGTH, MAX_RESULT_LIMIT

MAX_LIMIT = MAX_RESULT_LIMIT


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def validate_string(
    value: Any, name: str, max_length: int, required: bool = False
) -> Optional[str]:
    """
    Validate a string parameter.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        max_length: Maximum allowed length
        required: Whether the parameter is required

    Returns:
        Validated string or None

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        if required:
            raise ValidationError(f"'{name}' is required")
        return None

    if not isinstance(value, str):
        raise ValidationError(f"'{name}' must be a string, got {type(value).__name__}")

    if len(value) > max_length:
        raise ValidationError(
            f"'{name}' exceeds maximum length ({len(value)} > {max_length})"
        )

    return value


def validate_boolean(value: Any, name: str) -> Optional[bool]:
    """
    Validate a boolean parameter.

    Args:
        value: Value to validate
        name: Parameter name for error messages

    Returns:
        Validated boolean or None

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False

    raise ValidationError(f"'{name}' must be a boolean, got {type(value).__name__}")


def validate_integer(
    value: Any, name: str, min_val: int = 0, max_val: int = MAX_LIMIT
) -> Optional[int]:
    """
    Validate an integer parameter.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Validated integer or None

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValidationError(f"'{name}' must be an integer, got boolean")

    if isinstance(value, int):
        if value < min_val:
            raise ValidationError(f"'{name}' must be >= {min_val}, got {value}")
        if value > max_val:
            raise ValidationError(f"'{name}' must be <= {max_val}, got {value}")
        return value

    if isinstance(value, str):
        try:
            int_val = int(value)
            if int_val < min_val or int_val > max_val:
                raise ValidationError(
                    f"'{name}' must be between {min_val} and {max_val}"
                )
            return int_val
        except ValueError:
            pass

    raise ValidationError(f"'{name}' must be an integer, got {type(value).__name__}")


def validate_conversation_id(value: Any, name: str = "id") -> str:
    """
    Validate a conversation ID.

    Args:
        value: Value to validate
        name: Parameter name for error messages

    Returns:
        Validated ID string

    Raises:
        ValidationError: If validation fails
    """
    validated = validate_string(value, name, MAX_ID_LENGTH, required=True)
    if not validated:
        raise ValidationError(f"'{name}' is required")

    # IDs should only contain alphanumeric, dashes, and underscores
    if not re.match(r"^[a-zA-Z0-9_-]+$", validated):
        raise ValidationError(f"'{name}' contains invalid characters")

    return validated
