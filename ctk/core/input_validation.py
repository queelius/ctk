"""
Input validation utilities for CLI and API.

Provides functions to validate and sanitize user inputs such as file paths,
conversation IDs, and other parameters.
"""

import re
from pathlib import Path
from typing import Any, Optional


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


def validate_conversation_id(value: Optional[str], allow_partial: bool = True) -> Optional[str]:
    """
    Validate conversation ID format.

    Args:
        value: The conversation ID to validate
        allow_partial: If True, allow partial IDs (8+ hex characters).
                      If False, require full UUID format.

    Returns:
        The validated ID string

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(f"Conversation ID must be a string, got {type(value).__name__}")

    if not value:
        raise ValidationError("Conversation ID cannot be empty")

    if len(value) > 200:
        raise ValidationError(f"Conversation ID too long (max 200 chars, got {len(value)})")

    # Allow: letters, numbers, underscores, dashes, and hyphens (for UUID format)
    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        raise ValidationError(f"Invalid conversation ID format: {value}")

    # Enforce full UUID format when partial IDs are not allowed
    if not allow_partial:
        uuid_pattern = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        if not re.match(uuid_pattern, value):
            raise ValidationError(f"Full UUID required, got: {value}")

    return value


def validate_file_path(
    path_str: str,
    must_exist: bool = False,
    allow_relative: bool = True,
    allow_dir: bool = True,
    allow_file: bool = True,
) -> Path:
    """
    Validate and resolve a file path safely.

    Args:
        path_str: The path string to validate
        must_exist: If True, raise error if path doesn't exist
        allow_relative: If True, allow relative paths. If False, require absolute.
        allow_dir: If True, allow directories
        allow_file: If True, allow files

    Returns:
        Resolved Path object

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(path_str, str):
        raise ValidationError(f"Path must be a string, got {type(path_str).__name__}")

    if not path_str:
        raise ValidationError("Path cannot be empty")

    # Enforce absolute path requirement if relative paths not allowed
    if not allow_relative and not Path(path_str).is_absolute():
        raise ValidationError(f"Absolute path required, got relative: {path_str}")

    try:
        # Resolve the path (this handles .. and symlinks safely)
        path = Path(path_str).resolve()
    except (ValueError, OSError, RuntimeError) as e:
        raise ValidationError(f"Invalid path: {path_str} ({e})")

    # For file imports/exports, check existence
    if must_exist and not path.exists():
        raise ValidationError(f"Path does not exist: {path}")

    # Check type constraints
    if path.exists():
        if path.is_dir() and not allow_dir:
            raise ValidationError(f"Expected file, got directory: {path}")
        if path.is_file() and not allow_file:
            raise ValidationError(f"Expected directory, got file: {path}")

    return path


def validate_path_selection(value: Optional[str]) -> Optional[str]:
    """
    Validate path selection parameter.

    Args:
        value: The path selection value to validate

    Returns:
        The validated path selection value

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(f"Path selection must be a string, got {type(value).__name__}")

    allowed_values = {"longest", "first", "last"}
    if value not in allowed_values:
        raise ValidationError(
            f"Invalid path selection '{value}'. Must be one of: {', '.join(sorted(allowed_values))}"
        )

    return value


def validate_export_format(value: Optional[str]) -> Optional[str]:
    """
    Validate export format (basic validation - specific formats checked by registry).

    Args:
        value: The export format to validate

    Returns:
        The validated format value

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(f"Export format must be a string, got {type(value).__name__}")

    if not value:
        raise ValidationError("Export format cannot be empty")

    if len(value) > 50:
        raise ValidationError(f"Export format too long (max 50 chars, got {len(value)})")

    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        raise ValidationError(f"Invalid export format: {value}")

    return value


def validate_string(
    value: Optional[str],
    max_length: int = 10000,
    allow_empty: bool = True,
    name: str = "value"
) -> Optional[str]:
    """
    Validate a general string input.

    Args:
        value: The string to validate
        max_length: Maximum allowed length
        allow_empty: If True, allow empty strings
        name: Name of the value for error messages

    Returns:
        The validated string

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a string, got {type(value).__name__}")

    if not allow_empty and not value:
        raise ValidationError(f"{name} cannot be empty")

    if len(value) > max_length:
        raise ValidationError(
            f"{name} too long (max {max_length} chars, got {len(value)})"
        )

    return value


def validate_boolean(value: Any, name: str = "value") -> bool:
    """
    Validate and coerce a boolean input.

    Args:
        value: The value to validate/coerce
        name: Name of the value for error messages

    Returns:
        Boolean value

    Raises:
        ValidationError: If validation fails
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValidationError(
            f"Invalid boolean for {name}: {value} (use true/false/yes/no/1/0)"
        )

    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValidationError(f"Invalid boolean for {name}: {value} (use 0 or 1)")

    raise ValidationError(
        f"{name} must be boolean, got {type(value).__name__}"
    )


def validate_integer(
    value: Any,
    min_val: int = 0,
    max_val: int = 10000,
    name: str = "value"
) -> int:
    """
    Validate and coerce an integer input.

    Args:
        value: The value to validate/coerce
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        name: Name of the value for error messages

    Returns:
        Integer value

    Raises:
        ValidationError: If validation fails
    """
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be integer, not boolean")

    if isinstance(value, int):
        val = value
    elif isinstance(value, str):
        try:
            val = int(value)
        except ValueError:
            raise ValidationError(f"Invalid integer for {name}: {value}")
    else:
        raise ValidationError(f"{name} must be integer, got {type(value).__name__}")

    if val < min_val or val > max_val:
        raise ValidationError(
            f"{name} out of range [{min_val}, {max_val}]: {val}"
        )

    return val
