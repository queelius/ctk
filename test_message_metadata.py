#!/usr/bin/env python3
"""Test message metadata as VFS files"""

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.core.database import ConversationDB
from ctk.integrations.chat.tui import ChatTUI

# Use existing database with conversations
db = ConversationDB("dev/test-images-final")

# Create provider
provider = OllamaProvider(config={'model': 'llama3.2'})

# Create TUI
tui = ChatTUI(provider=provider, db=db)

print("Testing Message Metadata as VFS Files")
print("=" * 70)

# Navigate to a message and explore metadata
test_cmds = [
    ('cd /chats', 'Navigate to chats directory'),
    ('ls | head 1', 'Get first conversation'),
    ('cd 7c87', 'Navigate using prefix'),
    ('pwd', 'Show current path'),
    ('ls', 'List message nodes'),
    ('cd m1', 'Navigate to first message'),
    ('pwd', 'Show current path (inside message)'),
    ('ls', 'List metadata files and children'),
    ('', ''),  # Blank line
    ('cat text | head 3', 'Read message text (first 3 lines)'),
    ('cat role', 'Read message role'),
    ('cat timestamp', 'Read message timestamp'),
    ('cat id | grep "^" | head -c 20', 'Read message ID (truncated)'),
    ('', ''),  # Blank line
    ('echo "Metadata files allow Unix-like inspection!"', 'Demo echo'),
    ('ls | grep -v "^m"', 'List only metadata files (filter out message dirs)'),
]

for cmd, description in test_cmds:
    if not cmd:
        print()
        continue

    if description:
        print(f"\n# {description}")

    print(f"$ {cmd}")

    pipeline = tui.shell_parser.parse(cmd)
    result = tui.command_dispatcher.execute(pipeline, print_output=False)

    if result.success:
        output = result.output.strip()
        if output:
            # Limit output length
            if len(output) > 500:
                print(output[:500] + "...")
            else:
                print(output)
    else:
        print(f"Error: {result.error}")

print("\n" + "=" * 70)
print("Message metadata test complete!")
print("\nKey features demonstrated:")
print("  - Message nodes expose metadata as files (text, role, timestamp, id)")
print("  - 'ls' shows both metadata files and child messages")
print("  - 'cat' can read individual metadata files")
print("  - Pipes work with metadata files (e.g., cat text | head)")
print("  - Grep can filter metadata (e.g., ls | grep -v '^m')")
