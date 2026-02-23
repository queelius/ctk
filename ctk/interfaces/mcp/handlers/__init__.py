"""MCP handler modules for CTK tools."""

from ctk.interfaces.mcp.handlers import analysis, conversation, metadata, search

# Collect all tools from handler modules
ALL_TOOLS = search.TOOLS + conversation.TOOLS + metadata.TOOLS + analysis.TOOLS

# Collect all handlers from handler modules
ALL_HANDLERS = {}
ALL_HANDLERS.update(search.HANDLERS)
ALL_HANDLERS.update(conversation.HANDLERS)
ALL_HANDLERS.update(metadata.HANDLERS)
ALL_HANDLERS.update(analysis.HANDLERS)
