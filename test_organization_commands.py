#!/usr/bin/env python3
"""Test organization commands in shell mode"""

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.core.database import ConversationDB
from ctk.integrations.chat.tui import ChatTUI

# Use existing database with conversations
db = ConversationDB("dev/test-images-final")

# Create provider
provider = OllamaProvider(config={'model': 'llama3.2'})

# Create TUI
tui = ChatTUI(provider=provider, db=db)

print("Testing Organization Commands")
print("=" * 70)

# Test organization commands
test_sections = [
    {
        'title': 'Star/Unstar Conversation',
        'commands': [
            ('cd /chats', 'Navigate to chats'),
            ('cd 68e1', 'Navigate to conversation (with prefix)'),
            ('pwd', 'Show current path'),
            ('star', 'Star current conversation'),
            ('cd /starred', 'Navigate to starred directory'),
            ('ls | grep 68e1', 'Verify conversation is starred'),
            ('cd /chats/68e1', 'Return to conversation'),
            ('unstar', 'Unstar conversation'),
            ('cd /starred', 'Check starred directory'),
            ('ls | grep 68e1', 'Should not find conversation'),
        ]
    },
    {
        'title': 'Pin/Unpin Conversation',
        'commands': [
            ('cd /chats/68e1', 'Navigate to conversation'),
            ('pin', 'Pin conversation'),
            ('cd /pinned', 'Navigate to pinned directory'),
            ('ls | grep 68e1', 'Verify conversation is pinned'),
            ('cd /chats/68e1', 'Return to conversation'),
            ('unpin', 'Unpin conversation'),
        ]
    },
    {
        'title': 'Archive/Unarchive Conversation',
        'commands': [
            ('cd /chats/68e1', 'Navigate to conversation'),
            ('archive', 'Archive conversation'),
            ('cd /archived', 'Navigate to archived directory'),
            ('ls | grep 68e1', 'Verify conversation is archived'),
            ('cd /chats/68e1', 'Return to conversation'),
            ('unarchive', 'Unarchive conversation'),
        ]
    },
    {
        'title': 'Set Conversation Title',
        'commands': [
            ('cd /chats/68e1', 'Navigate to conversation'),
            ('title Shell Mode Test Conversation', 'Set new title'),
            ('tree | head 5', 'Show tree with updated title'),
        ]
    },
    {
        'title': 'Organization with Explicit IDs',
        'commands': [
            ('cd /chats', 'Navigate to chats'),
            ('star 7c87', 'Star using prefix (from any location)'),
            ('cd /starred', 'Check starred directory'),
            ('ls | grep 7c87', 'Verify conversation is starred'),
            ('unstar 7c87af4c-5e10-4eb4-8aaa-41070f710e0f', 'Unstar using full ID'),
        ]
    }
]

for section in test_sections:
    print(f"\n{section['title']}")
    print("-" * 70)

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
                # Limit output to 200 chars for readability
                if len(output) > 200:
                    print(output[:200] + "...")
                else:
                    print(output)
        else:
            print(f"Error: {result.error}")

print("\n" + "=" * 70)
print("Organization Commands Test Complete!")
print("\nAvailable organization commands:")
print("  - star [conv_id]      - Star a conversation")
print("  - unstar [conv_id]    - Unstar a conversation")
print("  - pin [conv_id]       - Pin a conversation")
print("  - unpin [conv_id]     - Unpin a conversation")
print("  - archive [conv_id]   - Archive a conversation")
print("  - unarchive [conv_id] - Unarchive a conversation")
print("  - title <new_title>   - Set conversation title")
print("\nNote: If conv_id is omitted, operates on current conversation")
