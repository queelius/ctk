#!/usr/bin/env python3
"""
Test script for MCP integration in CTK chat.

This demonstrates how to use MCP tools with the chat interface.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.integrations.chat.tui import ChatTUI
from ctk.core.database import ConversationDB


def main():
    """Run chat with MCP integration"""

    # Parse command line arguments
    if len(sys.argv) > 1:
        model = sys.argv[1]
    else:
        model = 'llama3.2'

    # Check for remote Ollama
    if len(sys.argv) > 2:
        base_url = sys.argv[2]
    else:
        base_url = 'http://localhost:11434'

    # Check for database path
    if len(sys.argv) > 3:
        db_path = sys.argv[3]
    else:
        db_path = 'db'  # Default database

    # Create provider
    config = {
        'model': model,
        'base_url': base_url
    }

    print(f"Initializing Ollama provider...")
    print(f"  Model: {model}")
    print(f"  URL: {base_url}")
    print(f"  Database: {db_path}")
    print()

    provider = OllamaProvider(config)

    # Test connection
    if not provider.is_available():
        print(f"Error: Cannot connect to Ollama at {base_url}")
        print("Make sure Ollama is running")
        sys.exit(1)

    # Create database connection
    try:
        db = ConversationDB(db_path)
        print(f"✓ Connected to database")
    except Exception as e:
        print(f"Warning: Could not connect to database: {e}")
        print("Continuing without database support...")
        db = None

    # Print MCP instructions
    print("\n" + "=" * 60)
    print("MCP Integration Demo")
    print("=" * 60)
    print("\nTo use MCP tools, first add and connect to a server:")
    print()
    print("  1. Add the example server:")
    example_path = os.path.join(os.path.dirname(__file__), "mcp_example_server.py")
    print(f"     /mcp add example python {example_path}")
    print()
    print("  2. Connect to it:")
    print("     /mcp connect example")
    print()
    print("  3. List available tools:")
    print("     /mcp tools")
    print()
    print("  4. Call a tool:")
    print('     /mcp call echo {"text": "Hello from MCP!"}')
    print('     /mcp call list_files {"path": "."}')
    print()
    print("=" * 60)
    print()

    # Create and run chat
    chat = ChatTUI(provider, db=db)
    chat.run()


if __name__ == '__main__':
    main()
