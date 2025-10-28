#!/usr/bin/env python3
"""Test command piping in shell mode"""

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.core.database import ConversationDB
from ctk.integrations.chat.tui import ChatTUI

# Use existing database with conversations
db = ConversationDB("dev/test-images-final")

# Create provider
provider = OllamaProvider(config={'model': 'llama3.2'})

# Create TUI
tui = ChatTUI(provider=provider, db=db)

print("Testing command piping functionality")
print("=" * 60)

# Test 1: Simple pipe - ls | head
print("\nTest 1: Simple pipe (ls | head)")
print("-" * 60)
test_commands = [
    'cd /chats',
    'ls | head 5',
]

for cmd in test_commands:
    print(f"$ {cmd}")
    pipeline = tui.shell_parser.parse(cmd)
    result = tui.command_dispatcher.execute(pipeline, print_output=False)
    if result.success:
        print(result.output, end='')
    else:
        print(f"Error: {result.error}")

# Test 2: cat | head
print("\nTest 2: Reading message with pipe (cat | head)")
print("-" * 60)
test_commands = [
    'cd /chats',
    'ls | head 1',  # Get first conversation
]

for cmd in test_commands:
    pipeline = tui.shell_parser.parse(cmd)
    result = tui.command_dispatcher.execute(pipeline, print_output=False)
    if result.success and cmd.startswith('ls'):
        first_conv_id = result.output.strip().split('\n')[0].rstrip('/')

        # Navigate to conversation
        print(f"$ cd {first_conv_id[:8]}")
        pipeline = tui.shell_parser.parse(f'cd {first_conv_id[:8]}')
        cd_result = tui.command_dispatcher.execute(pipeline, print_output=False)
        if cd_result.output:
            print(cd_result.output, end='')

        # Now test cat | head
        print(f"$ cat m1 | head 3")
        pipeline = tui.shell_parser.parse('cat m1 | head 3')
        cat_result = tui.command_dispatcher.execute(pipeline, print_output=False)
        if cat_result.success:
            print(cat_result.output, end='')
        else:
            print(f"Error: {cat_result.error}")

# Test 3: Multiple pipes - cat | grep | head
print("\nTest 3: Multiple pipes (cat | grep | tail)")
print("-" * 60)
print("$ cat m1 | grep -i 'user\\|assistant' | tail 2")
pipeline = tui.shell_parser.parse("cat m1 | grep -i 'user\\|assistant' | tail 2")
result = tui.command_dispatcher.execute(pipeline, print_output=False)
if result.success:
    print(result.output, end='')
else:
    print(f"Error: {result.error}")

# Test 4: echo with pipe
print("\nTest 4: Echo with pipe (echo | grep)")
print("-" * 60)
test_commands = [
    'echo "Hello World" | grep "World"',
    'echo "Line 1\\nLine 2\\nLine 3" | head 2',
]

for cmd in test_commands:
    print(f"$ {cmd}")
    pipeline = tui.shell_parser.parse(cmd)
    result = tui.command_dispatcher.execute(pipeline, print_output=False)
    if result.success:
        print(result.output, end='')
    else:
        print(f"Error: {result.error}")

# Test 5: ls | grep (filtering conversation IDs)
print("\nTest 5: Directory listing with filter (ls | grep)")
print("-" * 60)
print("$ cd /chats")
pipeline = tui.shell_parser.parse('cd /chats')
tui.command_dispatcher.execute(pipeline, print_output=False)

print("$ ls | grep '^7' | head 3")
pipeline = tui.shell_parser.parse("ls | grep '^7' | head 3")
result = tui.command_dispatcher.execute(pipeline, print_output=False)
if result.success:
    print(result.output, end='')
else:
    print(f"Error: {result.error}")

# Test 6: Environment variable expansion in pipe
print("\nTest 6: Environment variables in pipes")
print("-" * 60)
print("$ echo $CWD | grep '/chats'")
pipeline = tui.shell_parser.parse("echo $CWD | grep '/chats'")
result = tui.command_dispatcher.execute(pipeline, print_output=False)
if result.success:
    print(result.output, end='')
else:
    print(f"Error: {result.error}")

print("\n" + "=" * 60)
print("Piping test complete!")
