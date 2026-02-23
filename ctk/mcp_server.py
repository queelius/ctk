#!/usr/bin/env python3
"""CTK MCP Server — entry point. See ctk/interfaces/mcp/ for implementation."""

import asyncio

from ctk.interfaces.mcp.server import (
    get_db,
    handle_call_tool,
    handle_list_tools,
    main,
    server,
)
from ctk.interfaces.mcp.handlers.conversation import (
    format_conversation_for_output,
    resolve_conversation_id,
)

# Re-export validation for backward compatibility
from ctk.interfaces.mcp.validation import (
    MAX_LIMIT,
    ValidationError,
    validate_boolean,
    validate_conversation_id,
    validate_integer,
    validate_string,
)

# Re-export constants that were previously available at module level
from ctk.core.constants import (
    MAX_ID_LENGTH,
    MAX_QUERY_LENGTH,
    MAX_TITLE_LENGTH,
)

__all__ = [
    "server",
    "get_db",
    "handle_list_tools",
    "handle_call_tool",
    "main",
    "resolve_conversation_id",
    "format_conversation_for_output",
    "ValidationError",
    "validate_string",
    "validate_boolean",
    "validate_integer",
    "validate_conversation_id",
    "MAX_LIMIT",
    "MAX_ID_LENGTH",
    "MAX_QUERY_LENGTH",
    "MAX_TITLE_LENGTH",
]

if __name__ == "__main__":
    asyncio.run(main())
