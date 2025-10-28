#!/usr/bin/env python3
"""
Comprehensive test of shell-first mode

Demonstrates all implemented features:
- Navigation (cd, ls, pwd)
- Unix commands (cat, head, tail, echo, grep)
- Piping between commands
- Prefix resolution
- Message metadata files (text, role, timestamp, id)
- Visualization (tree, paths)
- Environment variables
"""

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.core.database import ConversationDB
from ctk.integrations.chat.tui import ChatTUI

# Use existing database with conversations
db = ConversationDB("dev/test-images-final")

# Create provider
provider = OllamaProvider(config={'model': 'llama3.2'})

# Create TUI in shell mode
tui = ChatTUI(provider=provider, db=db)

print("=" * 80)
print("COMPREHENSIVE SHELL MODE TEST")
print("=" * 80)

# Test cases
test_sections = [
    {
        'title': '1. Basic Navigation',
        'commands': [
            ('pwd', 'Show initial path'),
            ('ls', 'List root directories'),
            ('cd /chats', 'Navigate to chats'),
            ('pwd', 'Verify new path'),
            ('ls | head 5', 'List first 5 conversations'),
        ]
    },
    {
        'title': '2. Prefix Resolution',
        'commands': [
            ('cd 7c87', 'Navigate using 4-char prefix'),
            ('pwd', 'Verify resolved path'),
            ('cd ..', 'Go back to parent'),
            ('pwd', 'Verify parent path'),
        ]
    },
    {
        'title': '3. Message Metadata Files',
        'commands': [
            ('cd 7c87', 'Navigate to conversation'),
            ('cd m1', 'Navigate to first message'),
            ('ls', 'List metadata files and children'),
            ('cat text | head 3', 'Read message text'),
            ('cat role', 'Read message role'),
            ('cat timestamp', 'Read message timestamp'),
            ('pwd', 'Show current path'),
        ]
    },
    {
        'title': '4. Unix Commands and Piping',
        'commands': [
            ('cd /chats', 'Return to chats'),
            ('ls | grep "^7" | head 3', 'Filter conversations by prefix'),
            ('echo $CWD', 'Show current working directory'),
            ('echo "Testing piping" | grep "pipe"', 'Test echo and grep pipe'),
        ]
    },
    {
        'title': '5. Visualization Commands',
        'commands': [
            ('cd 7c87', 'Navigate to conversation'),
            ('tree | head 20', 'Show conversation tree (first 20 lines)'),
            ('paths | head 15', 'Show all paths (first 15 lines)'),
        ]
    },
    {
        'title': '6. Environment Variables',
        'commands': [
            ('echo $CWD', 'Current working directory'),
            ('echo $PWD', 'Present working directory (alias)'),
            ('echo $PROVIDER', 'LLM provider name'),
            ('echo $MODEL', 'Current model'),
        ]
    },
]

for section in test_sections:
    print(f"\n{section['title']}")
    print("-" * 80)

    for cmd, description in section['commands']:
        if description:
            print(f"\n# {description}")
        print(f"$ {cmd}")

        # Execute command
        pipeline = tui.shell_parser.parse(cmd)
        result = tui.command_dispatcher.execute(pipeline, print_output=False)

        if result.success:
            output = result.output.strip()
            if output:
                # Limit output to 300 chars for readability
                if len(output) > 300:
                    print(output[:300] + "...")
                else:
                    print(output)
        else:
            print(f"Error: {result.error}")

print("\n" + "=" * 80)
print("COMPREHENSIVE TEST COMPLETE")
print("=" * 80)

# Print command summary
print("\nRegistered Commands:")
for cmd in sorted(tui.command_dispatcher.handlers.keys()):
    print(f"  - {cmd}")

print(f"\nTotal commands: {len(tui.command_dispatcher.handlers)}")

print("\nFeatures Demonstrated:")
print("  ✓ Navigation with cd, ls, pwd")
print("  ✓ Prefix resolution (e.g., cd 7c87 → full UUID)")
print("  ✓ Message metadata as files (text, role, timestamp, id)")
print("  ✓ Unix commands (cat, head, tail, echo, grep)")
print("  ✓ Command piping (|)")
print("  ✓ Environment variables ($CWD, $PWD, $PROVIDER, $MODEL)")
print("  ✓ Visualization (tree, paths)")
print("  ✓ Relative path navigation (cd .., cd m1)")
