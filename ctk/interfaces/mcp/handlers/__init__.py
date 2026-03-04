"""MCP handler modules for CTK tools."""

from ctk.interfaces.mcp.handlers import (analysis, conversation, metadata,
                                         search, sql)

# Collect all tools from handler modules
ALL_TOOLS = (
    search.TOOLS + conversation.TOOLS + metadata.TOOLS
    + analysis.TOOLS + sql.TOOLS
)

# Collect all handlers from handler modules
ALL_HANDLERS = {}
ALL_HANDLERS.update(search.HANDLERS)
ALL_HANDLERS.update(conversation.HANDLERS)
ALL_HANDLERS.update(metadata.HANDLERS)
ALL_HANDLERS.update(analysis.HANDLERS)
ALL_HANDLERS.update(sql.HANDLERS)
