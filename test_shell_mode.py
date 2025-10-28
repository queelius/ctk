#!/usr/bin/env python3
"""Quick test of shell mode integration"""

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.core.database import ConversationDB
from ctk.integrations.chat.tui import ChatTUI

# Create test database
db = ConversationDB("test-shell-mode-db")

# Create provider
provider = OllamaProvider(config={'model': 'llama3.2'})

# Create TUI in shell mode
tui = ChatTUI(provider=provider, db=db)

# Check mode
print(f"Initial mode: {tui.mode}")
print(f"Shell parser initialized: {tui.shell_parser is not None}")
print(f"Command dispatcher initialized: {tui.command_dispatcher is not None}")

# Test environment variables
tui._update_environment()
print(f"\nEnvironment variables:")
for key, value in tui.shell_parser.environment.items():
    print(f"  {key}: {value}")

# Test shell parser
print(f"\nTesting shell parser:")
test_commands = [
    'echo Hello World',
    'cat m1',
    'ls',
    'cd /chats',
    'What is quantum mechanics?'  # Non-command
]

for cmd in test_commands:
    is_cmd = tui.shell_parser.is_shell_command(cmd)
    print(f"  '{cmd}' -> {'COMMAND' if is_cmd else 'CHAT'}")

print("\nShell mode integration test complete!")
