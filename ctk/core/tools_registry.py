"""
Tool definitions registry for LLM tool calling.

This module contains the data definitions for all tools available to LLMs
via the /ask command and chat mode. The tools are used by both CLI and TUI.

Each tool definition includes:
- name: Tool name for LLM to call
- pass_through: If True, output goes directly to user (not back to LLM)
- description: Detailed description with usage guidelines
- input_schema: JSON Schema for tool parameters
"""

from typing import Any, Dict, List

# Tool definitions for CTK operations
TOOLS_REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "search_conversations",
        "pass_through": True,
        "description": """Search and filter conversations in the database.

DO NOT USE THIS TOOL FOR: greetings (hi, hello), chitchat, general questions.

USE THIS TOOL WHEN user explicitly asks to find/search/list conversations.

IMPORTANT: After showing results, suggest shell commands like `show <id>` or `cd <id>` - NEVER mention this tool's name to users.

EXAMPLES:
- "find conversations about python" → {"query": "python"}
- "show me starred conversations" → {"starred": true}
- "list recent conversations" → {"limit": 10}

RULE: Only include starred/pinned/archived if user explicitly mentions them.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional search query text (searches titles and message content). Omit for listing without search.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                },
                "source": {
                    "type": "string",
                    "description": "Filter by source (e.g., 'openai', 'anthropic')",
                },
                "project": {
                    "type": "string",
                    "description": "Filter by project name",
                },
                "model": {"type": "string", "description": "Filter by model name"},
                "starred": {
                    "type": "boolean",
                    "description": "Set to true to show ONLY starred conversations. Omit this parameter completely unless user explicitly mentions 'starred'.",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Set to true to show ONLY pinned conversations. Omit this parameter completely unless user explicitly mentions 'pinned'.",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Set to true to show ONLY archived conversations. Omit this parameter completely unless user explicitly mentions 'archived'.",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags to filter by",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_conversation",
        "pass_through": True,
        "description": """Get details of a specific conversation by its ID.

DO NOT USE THIS TOOL FOR: greetings, chitchat, or questions that don't mention a specific conversation ID.

USE THIS TOOL WHEN: user provides a conversation ID and wants details about it.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "show_messages": {
                    "type": "boolean",
                    "description": "Include message content (default: false)",
                },
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "get_statistics",
        "pass_through": True,
        "description": """Get database statistics (counts, sources, models).

DO NOT USE THIS TOOL FOR: greetings, chitchat, or general questions.

USE THIS TOOL WHEN: user asks "how many conversations", "what are the stats", "show statistics".""",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "execute_shell_command",
        "pass_through": True,
        "description": """Execute a CTK shell command (cd, ls, find, cat, tree, star, etc.).

DO NOT USE THIS TOOL FOR: greetings, chitchat, or general questions.

USE THIS TOOL WHEN: user wants to navigate (cd, ls), view content (cat, tree), or organize (star, pin, archive).

Commands: cd, ls, pwd, find, cat, tree, paths, star, unstar, pin, unpin, archive, unarchive, title, show""",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (e.g., 'ls /starred', 'find -name python')",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "star_conversation",
        "description": """Star a conversation to mark it as important.

USE THIS TOOL WHEN: user says "star this", "mark as important", "favorite this conversation".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to star",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "unstar_conversation",
        "description": """Remove star from a conversation.

USE THIS TOOL WHEN: user says "unstar this", "remove from favorites".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to unstar",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "pin_conversation",
        "description": """Pin a conversation to keep it at the top.

USE THIS TOOL WHEN: user says "pin this", "keep at top".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to pin",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "unpin_conversation",
        "description": """Remove pin from a conversation.

USE THIS TOOL WHEN: user says "unpin this".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to unpin",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "archive_conversation",
        "description": """Archive a conversation to hide it from default listings.

USE THIS TOOL WHEN: user says "archive this", "hide this conversation".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to archive",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "unarchive_conversation",
        "description": """Unarchive a conversation to make it visible again.

USE THIS TOOL WHEN: user says "unarchive this", "restore this conversation".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to unarchive",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "rename_conversation",
        "description": """Rename a conversation by setting its title.

USE THIS TOOL WHEN: user says "rename this to...", "change title to...", "call this...".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to rename",
                },
                "title": {
                    "type": "string",
                    "description": "New title for the conversation",
                },
            },
            "required": ["conversation_id", "title"],
        },
    },
    {
        "name": "show_conversation_content",
        "description": """Show the full content of a conversation.

USE THIS TOOL WHEN: user says "show me the conversation", "display the chat", "what was said in...".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to show",
                },
                "path_selection": {
                    "type": "string",
                    "description": "Which path to show: 'longest' (default), 'latest', or a path number like '0', '1'",
                },
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "show_conversation_tree",
        "description": """Show the tree structure of a conversation (useful for branching conversations).

USE THIS TOOL WHEN: user says "show the tree", "show branches", "conversation structure".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "delete_conversation",
        "description": """Delete a conversation from the database. This is IRREVERSIBLE.

USE THIS TOOL WHEN: user explicitly says "delete this conversation", "remove this chat".

IMPORTANT: Ask for confirmation before deleting.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to delete",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "tag_conversation",
        "description": """Add tags to a conversation for categorization.

USE THIS TOOL WHEN: user says "tag this as...", "add tag...", "categorize as...".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to add to the conversation",
                },
            },
            "required": ["conversation_id", "tags"],
        },
    },
    {
        "name": "list_tags",
        "description": """List all tags in the database with counts.

USE THIS TOOL WHEN: user says "show all tags", "what tags exist", "list tags".""",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "remove_tag",
        "description": """Remove a tag from a conversation.

USE THIS TOOL WHEN: user says "remove tag", "untag", "delete tag from...".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "tag": {"type": "string", "description": "Tag to remove"},
            },
            "required": ["conversation_id", "tag"],
        },
    },
    {
        "name": "list_sources",
        "description": """List all conversation sources (openai, anthropic, etc.) with counts.

USE THIS TOOL WHEN: user says "what sources", "show sources", "where are conversations from".""",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_models",
        "description": """List all models used in conversations with counts.

USE THIS TOOL WHEN: user says "what models", "show models", "which models were used".""",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "export_conversation",
        "description": """Export a conversation to a specific format.

USE THIS TOOL WHEN: user says "export to markdown", "save as json", "export conversation".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json", "jsonl"],
                    "description": "Export format (default: markdown)",
                },
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "duplicate_conversation",
        "description": """Create a copy of a conversation with a new ID.

USE THIS TOOL WHEN: user says "duplicate", "copy conversation", "clone this".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to duplicate",
                },
                "new_title": {
                    "type": "string",
                    "description": "Optional title for the copy",
                },
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "get_recent_conversations",
        "description": """Get the N most recently updated conversations.

USE THIS TOOL WHEN: user says "recent conversations", "latest chats", "what did I work on recently".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of conversations to return (default: 10)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "list_conversations",
        "description": """List conversations with optional filters.

USE THIS TOOL WHEN: user asks to "list conversations", "show all chats", "list starred", "show pinned", "what's archived".

Returns a formatted table of conversations matching the criteria.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "starred": {
                    "type": "boolean",
                    "description": "Filter to starred conversations only",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Filter to pinned conversations only",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Filter to archived conversations only",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 20)",
                },
                "source": {
                    "type": "string",
                    "description": "Filter by source (e.g., 'anthropic', 'openai')",
                },
                "model": {"type": "string", "description": "Filter by model name"},
            },
            "required": [],
        },
    },
    {
        "name": "list_conversation_paths",
        "description": """List all paths in a branching conversation tree.

USE THIS TOOL WHEN: user asks "show paths", "list branches", "how many paths", "conversation branches".

Returns all distinct paths from root to leaf in the conversation tree.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or prefix of conversation ID",
                }
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "list_plugins",
        "description": """List available importer and exporter plugins.

USE THIS TOOL WHEN: user asks "what plugins", "list importers", "list exporters", "supported formats".""",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "auto_tag_conversation",
        "description": """Automatically tag a conversation using LLM analysis.

USE THIS TOOL WHEN: user says "auto-tag", "suggest tags", "analyze and tag".

Uses LLM to analyze conversation content and suggest relevant tags.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or prefix of conversation ID",
                }
            },
            "required": ["conversation_id"],
        },
    },
]

# Set of pass-through tool names (output goes directly to user)
PASS_THROUGH_TOOLS = {
    "search_conversations",
    "list_conversations",
    "get_conversation",
    "get_statistics",
    "execute_shell_command",
}
