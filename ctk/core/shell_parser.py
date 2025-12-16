"""
Shell command parser for TUI shell mode

Parses shell-style command lines with support for:
- Quoted arguments (single and double quotes)
- Variable expansion ($VAR, ${VAR})
- Pipe operators (|)
- Command segmentation
"""

import re
import shlex
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ParsedCommand:
    """Represents a parsed shell command"""
    command: str
    args: List[str]
    raw_line: str


@dataclass
class ParsedPipeline:
    """Represents a parsed command pipeline"""
    commands: List[ParsedCommand]
    has_pipe: bool


class ShellParser:
    """Parse shell command lines"""

    # Variable expansion pattern: $VAR or ${VAR}
    VAR_PATTERN = re.compile(r'\$\{([^}]+)\}|\$([A-Z_][A-Z0-9_]*)', re.IGNORECASE)

    def __init__(self, environment: Optional[Dict[str, str]] = None):
        """
        Initialize parser

        Args:
            environment: Environment variables for expansion
        """
        self.environment = environment or {}

    def set_environment(self, env: Dict[str, str]):
        """Update environment variables"""
        self.environment = env

    def update_variable(self, key: str, value: str):
        """Update a single environment variable"""
        self.environment[key] = value

    def expand_variables(self, text: str) -> str:
        """
        Expand environment variables in text

        Args:
            text: Text containing $VAR or ${VAR} references

        Returns:
            Text with variables expanded

        Examples:
            >>> parser = ShellParser({'CWD': '/chats', 'MODEL': 'llama3.2'})
            >>> parser.expand_variables('echo "Path: $CWD"')
            'echo "Path: /chats"'
            >>> parser.expand_variables('Model is ${MODEL}')
            'Model is llama3.2'
        """
        def replace_var(match):
            # ${VAR} format or $VAR format
            var_name = match.group(1) or match.group(2)
            return self.environment.get(var_name, f'${var_name}')  # Keep unexpanded if not found

        return self.VAR_PATTERN.sub(replace_var, text)

    def split_pipeline(self, line: str) -> List[str]:
        """
        Split command line by pipe operators

        Args:
            line: Command line string

        Returns:
            List of command segments

        Examples:
            >>> parser = ShellParser()
            >>> parser.split_pipeline('ls | grep foo')
            ['ls', 'grep foo']
            >>> parser.split_pipeline('cat m1 | grep error | head 5')
            ['cat m1', 'grep error', 'head 5']
        """
        # Don't split pipes inside quotes
        # Use a simple state machine to track quote state
        segments = []
        current = []
        in_single_quote = False
        in_double_quote = False

        i = 0
        while i < len(line):
            char = line[i]

            # Track quote state
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                current.append(char)
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                current.append(char)
            # Split on pipe if not in quotes
            elif char == '|' and not in_single_quote and not in_double_quote:
                if current:
                    segments.append(''.join(current).strip())
                    current = []
            else:
                current.append(char)

            i += 1

        # Add final segment
        if current:
            segments.append(''.join(current).strip())

        return segments

    def parse_command(self, command_str: str) -> ParsedCommand:
        """
        Parse a single command string into command and arguments

        Args:
            command_str: Command string (e.g., "cat m1 m2" or 'echo "hello world"')

        Returns:
            ParsedCommand with command name and arguments

        Examples:
            >>> parser = ShellParser()
            >>> cmd = parser.parse_command('cat m1')
            >>> cmd.command
            'cat'
            >>> cmd.args
            ['m1']
            >>> cmd = parser.parse_command('echo "hello world"')
            >>> cmd.command
            'echo'
            >>> cmd.args
            ['hello world']
        """
        # Use shlex to handle quoted arguments properly
        try:
            tokens = shlex.split(command_str)
        except ValueError as e:
            # If shlex fails (unclosed quotes), return raw split
            tokens = command_str.split()

        if not tokens:
            return ParsedCommand(command='', args=[], raw_line=command_str)

        command = tokens[0]
        args = tokens[1:] if len(tokens) > 1 else []

        return ParsedCommand(command=command, args=args, raw_line=command_str)

    def parse(self, line: str) -> ParsedPipeline:
        """
        Parse a complete command line (with possible pipes and variables)

        Args:
            line: Full command line

        Returns:
            ParsedPipeline with all commands

        Examples:
            >>> parser = ShellParser({'CWD': '/chats'})
            >>> pipeline = parser.parse('echo $CWD')
            >>> pipeline.commands[0].command
            'echo'
            >>> pipeline.commands[0].args
            ['/chats']
            >>> pipeline.has_pipe
            False

            >>> pipeline = parser.parse('cat m1 | grep error')
            >>> pipeline.has_pipe
            True
            >>> len(pipeline.commands)
            2
        """
        # First, expand variables
        expanded = self.expand_variables(line)

        # Split by pipes
        segments = self.split_pipeline(expanded)

        # Parse each segment
        commands = [self.parse_command(seg) for seg in segments]

        return ParsedPipeline(
            commands=commands,
            has_pipe=len(commands) > 1
        )

    def is_shell_command(self, line: str) -> bool:
        """
        Determine if a line is a shell command or chat input

        A line is a shell command if it starts with a known command word.
        Otherwise, it's treated as chat input.

        Args:
            line: Input line

        Returns:
            True if shell command, False if chat input
        """
        # List of known shell commands
        # This will be expanded as we implement more commands
        shell_commands = {
            # Navigation
            'cd', 'ls', 'pwd', 'goto-longest', 'goto-latest', 'where',
            # Unix commands
            'cat', 'head', 'tail', 'echo', 'grep',
            # File operations
            'ln', 'cp', 'mv', 'rm', 'mkdir',
            # Database operations
            'star', 'unstar', 'pin', 'unpin', 'archive', 'unarchive', 'title',
            'search', 'find', 'ask', 'show', 'tree', 'paths', 'export',
            # LLM commands
            'chat', 'model', 'say', 'models', 'temp',
            # MCP commands
            'mcp',
            # Network/similarity commands
            'net',
            # System commands
            'config', 'help', 'exit', 'clear', 'quit', 'history',
            # Session management
            'new-chat', 'save', 'load', 'delete', 'list',
            # Additional
            'browse', 'fork', 'fork-id', 'regenerate', 'edit', 'tag', 'untag',
            'alternatives', 'context',
        }

        # Parse to get first word
        pipeline = self.parse(line)
        if not pipeline.commands:
            return False

        first_command = pipeline.commands[0].command.lower()
        return first_command in shell_commands


if __name__ == '__main__':
    # Simple tests
    parser = ShellParser({'CWD': '/chats', 'MODEL': 'llama3.2', 'MSG_COUNT': '5'})

    # Test variable expansion
    print("Variable expansion:")
    print(f"  Input:  echo 'Current: $CWD'")
    print(f"  Output: {parser.expand_variables('echo Current: $CWD')}")
    print(f"  Input:  Model: ${{MODEL}}, Count: $MSG_COUNT")
    print(f"  Output: {parser.expand_variables('Model: ${MODEL}, Count: $MSG_COUNT')}")
    print()

    # Test command parsing
    print("Command parsing:")
    cmd = parser.parse_command('cat m1 m2 m3')
    print(f"  Input:  cat m1 m2 m3")
    print(f"  Command: {cmd.command}, Args: {cmd.args}")

    cmd = parser.parse_command('echo "hello world"')
    print(f"  Input:  echo \"hello world\"")
    print(f"  Command: {cmd.command}, Args: {cmd.args}")
    print()

    # Test pipeline parsing
    print("Pipeline parsing:")
    pipeline = parser.parse('cat m1 | grep error | head 5')
    print(f"  Input: cat m1 | grep error | head 5")
    print(f"  Has pipe: {pipeline.has_pipe}")
    print(f"  Commands: {len(pipeline.commands)}")
    for i, cmd in enumerate(pipeline.commands):
        print(f"    [{i}] {cmd.command} {cmd.args}")
    print()

    # Test shell command detection
    print("Shell command detection:")
    for line in ['cd /chats', 'cat m1', 'Hello, how are you?', 'help', 'What is quantum mechanics?']:
        is_cmd = parser.is_shell_command(line)
        print(f"  '{line}' -> {'COMMAND' if is_cmd else 'CHAT'}")
