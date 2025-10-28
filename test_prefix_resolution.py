#!/usr/bin/env python3
"""Test prefix resolution in navigation commands"""

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
print(f"Initial path: {tui.vfs_cwd}")
print()

# Test prefix resolution
test_commands = [
    'cd /chats',
    'pwd',
    'ls | head 5',  # Get first 5 conversation IDs
]

print("Getting conversation IDs to test prefix resolution:")
for cmd in test_commands:
    print(f"\n$ {cmd}")
    pipeline = tui.shell_parser.parse(cmd)
    result = tui.command_dispatcher.execute(pipeline, print_output=False)
    if result.success and result.output:
        print(result.output, end='')

# Get first conversation ID and test prefix
print("\nNow testing prefix resolution:")
pipeline = tui.shell_parser.parse('ls')
result = tui.command_dispatcher.execute(pipeline, print_output=False)
if result.success and result.output:
    lines = result.output.strip().split('\n')
    if lines:
        # Get first conversation ID
        first_conv_id = lines[0].rstrip('/')

        # Test with different prefix lengths
        for prefix_len in [3, 4, 6, 8]:
            # Return to /chats before each test
            pipeline = tui.shell_parser.parse('cd /chats')
            tui.command_dispatcher.execute(pipeline, print_output=False)

            prefix = first_conv_id[:prefix_len]
            print(f"\n$ cd {prefix}")
            pipeline = tui.shell_parser.parse(f'cd {prefix}')
            result = tui.command_dispatcher.execute(pipeline, print_output=False)
            if result.success:
                if result.output:
                    print(result.output, end='')
                # Show new path
                print(f"$ pwd")
                pipeline = tui.shell_parser.parse('pwd')
                pwd_result = tui.command_dispatcher.execute(pipeline, print_output=False)
                if pwd_result.success:
                    print(pwd_result.output, end='')
            else:
                print(f"Error: {result.error}")

# Test prefix resolution in subdirectory navigation
print("\n\nTesting relative prefix resolution:")
print("$ cd /chats")
pipeline = tui.shell_parser.parse('cd /chats')
tui.command_dispatcher.execute(pipeline, print_output=False)

# Get a conversation ID and navigate into it
pipeline = tui.shell_parser.parse('ls')
result = tui.command_dispatcher.execute(pipeline, print_output=False)
if result.success and result.output:
    lines = result.output.strip().split('\n')
    if len(lines) > 1:
        second_conv_id = lines[1].rstrip('/')

        print(f"\n$ cd {second_conv_id}")
        pipeline = tui.shell_parser.parse(f'cd {second_conv_id}')
        result = tui.command_dispatcher.execute(pipeline, print_output=False)
        if result.success:
            print("$ pwd")
            pipeline = tui.shell_parser.parse('pwd')
            pwd_result = tui.command_dispatcher.execute(pipeline, print_output=False)
            if pwd_result.success:
                print(pwd_result.output, end='')

            # Now test navigating to messages with prefix
            print("\n$ ls")
            pipeline = tui.shell_parser.parse('ls')
            ls_result = tui.command_dispatcher.execute(pipeline, print_output=False)
            if ls_result.success:
                print(ls_result.output, end='')

                # Try to cd to a message with prefix
                msg_lines = ls_result.output.strip().split('\n')
                if msg_lines:
                    first_msg = msg_lines[0].rstrip('/')
                    if first_msg.startswith('m'):
                        msg_prefix = first_msg[:3]  # e.g., "m1" from "m1/"
                        print(f"\n$ cd {msg_prefix}")
                        pipeline = tui.shell_parser.parse(f'cd {msg_prefix}')
                        cd_result = tui.command_dispatcher.execute(pipeline, print_output=False)
                        if cd_result.success:
                            if cd_result.output:
                                print(cd_result.output, end='')
                            print("$ pwd")
                            pipeline = tui.shell_parser.parse('pwd')
                            pwd_result = tui.command_dispatcher.execute(pipeline, print_output=False)
                            if pwd_result.success:
                                print(pwd_result.output, end='')

print("\n\nPrefix resolution test complete!")
