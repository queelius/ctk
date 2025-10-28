#!/usr/bin/env python3
"""Test navigation commands in shell mode"""

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.core.database import ConversationDB
from ctk.integrations.chat.tui import ChatTUI

# Use existing database with conversations
db = ConversationDB("dev/test-images-final")

# Create provider
provider = OllamaProvider(config={'model': 'llama3.2'})

# Create TUI
tui = ChatTUI(provider=provider, db=db)

print(f"Mode: {tui.mode}")
print(f"VFS Navigator: {tui.vfs_navigator is not None}")
print(f"Initial path: {tui.vfs_cwd}")
print()

# Test registered commands
print("Registered commands in dispatcher:")
for cmd in sorted(tui.command_dispatcher.handlers.keys()):
    print(f"  - {cmd}")
print()

# Test command parsing and execution
test_commands = [
    'pwd',
    'ls',
    'cd /chats',
    'pwd',
    'ls',
    'echo $CWD',
]

print("Testing commands:")
for cmd in test_commands:
    print(f"\n$ {cmd}")
    pipeline = tui.shell_parser.parse(cmd)
    result = tui.command_dispatcher.execute(pipeline, print_output=False)
    if result.success:
        if result.output:
            print(result.output, end='')
    else:
        print(f"Error: {result.error}")

print("\nNavigation test complete!")
