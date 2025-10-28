"""
Command dispatcher for shell mode

Routes parsed commands to appropriate handlers and manages command execution,
including support for piping between commands.
"""

import sys
from io import StringIO
from typing import Dict, Callable, Optional, List, Any
from dataclasses import dataclass

from ctk.core.shell_parser import ParsedCommand, ParsedPipeline


@dataclass
class CommandResult:
    """Result from command execution"""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0


class CommandDispatcher:
    """Dispatch and execute shell commands"""

    def __init__(self):
        """Initialize dispatcher with command handlers"""
        self.handlers: Dict[str, Callable] = {}
        self._register_builtin_commands()

    def _register_builtin_commands(self):
        """Register built-in command handlers"""
        # These will be implemented as we go
        # For now, register placeholders
        pass

    def register_command(self, name: str, handler: Callable):
        """
        Register a command handler

        Args:
            name: Command name (e.g., 'cat', 'ls')
            handler: Callable that handles the command
                     Signature: handler(args: List[str], stdin: str = '') -> CommandResult
        """
        self.handlers[name] = handler

    def register_commands(self, handlers: Dict[str, Callable]):
        """
        Register multiple command handlers at once

        Args:
            handlers: Dictionary mapping command names to handlers
        """
        self.handlers.update(handlers)

    def has_command(self, name: str) -> bool:
        """Check if a command is registered"""
        return name in self.handlers

    def execute_command(self, command: ParsedCommand, stdin: str = '') -> CommandResult:
        """
        Execute a single parsed command

        Args:
            command: Parsed command to execute
            stdin: Standard input to pass to command

        Returns:
            CommandResult with output and status
        """
        cmd_name = command.command.lower()

        # Check if command exists
        if not self.has_command(cmd_name):
            return CommandResult(
                success=False,
                output='',
                error=f"Command not found: {cmd_name}",
                exit_code=127
            )

        # Get handler and execute
        handler = self.handlers[cmd_name]

        try:
            result = handler(command.args, stdin=stdin)

            # Normalize result to CommandResult if handler returns something else
            if isinstance(result, CommandResult):
                return result
            elif isinstance(result, tuple):
                # Assume (success, output) or (success, output, error)
                success, output = result[0], result[1]
                error = result[2] if len(result) > 2 else None
                return CommandResult(success=success, output=output, error=error)
            elif isinstance(result, str):
                # Just output
                return CommandResult(success=True, output=result)
            else:
                return CommandResult(success=True, output=str(result))

        except Exception as e:
            return CommandResult(
                success=False,
                output='',
                error=f"Error executing {cmd_name}: {str(e)}",
                exit_code=1
            )

    def execute_pipeline(self, pipeline: ParsedPipeline) -> CommandResult:
        """
        Execute a command pipeline (with pipes)

        Args:
            pipeline: Parsed pipeline to execute

        Returns:
            CommandResult with final output and status

        Examples:
            # Single command (no pipe)
            cat m1
            -> Execute cat, return output

            # Two-stage pipe
            cat m1 | grep error
            -> Execute cat, pipe output to grep, return grep output

            # Multi-stage pipe
            cat m1 | grep error | head 5
            -> Execute cat, pipe to grep, pipe to head, return head output
        """
        if not pipeline.commands:
            return CommandResult(success=False, output='', error='No command to execute')

        # Execute first command with no stdin
        result = self.execute_command(pipeline.commands[0], stdin='')

        # If single command or first command failed, return immediately
        if not pipeline.has_pipe or not result.success:
            return result

        # Execute remaining commands in pipeline
        for i in range(1, len(pipeline.commands)):
            # Pipe previous output as stdin to next command
            result = self.execute_command(pipeline.commands[i], stdin=result.output)

            # Stop on error
            if not result.success:
                return result

        return result

    def execute(self, pipeline: ParsedPipeline, print_output: bool = True) -> CommandResult:
        """
        Execute a pipeline and optionally print output

        Args:
            pipeline: Parsed pipeline to execute
            print_output: Whether to print output to stdout

        Returns:
            CommandResult
        """
        result = self.execute_pipeline(pipeline)

        if print_output:
            if result.output:
                print(result.output, end='')
            if result.error:
                print(f"Error: {result.error}", file=sys.stderr)

        return result


# Example usage and testing
if __name__ == '__main__':
    from ctk.core.shell_parser import ShellParser

    # Create dispatcher
    dispatcher = CommandDispatcher()

    # Register some test commands
    def cmd_echo(args: List[str], stdin: str = '') -> CommandResult:
        """Echo command"""
        output = ' '.join(args) + '\n'
        return CommandResult(success=True, output=output)

    def cmd_cat(args: List[str], stdin: str = '') -> CommandResult:
        """Cat command (simulated)"""
        if stdin:
            return CommandResult(success=True, output=stdin)
        output = f"Content of {args[0] if args else 'stdin'}\n"
        return CommandResult(success=True, output=output)

    def cmd_grep(args: List[str], stdin: str = '') -> CommandResult:
        """Grep command (simulated)"""
        if not args:
            return CommandResult(success=False, error="grep: no pattern specified")

        pattern = args[0]
        lines = stdin.split('\n') if stdin else []
        matching = [line for line in lines if pattern in line]
        output = '\n'.join(matching) + ('\n' if matching else '')
        return CommandResult(success=True, output=output)

    def cmd_head(args: List[str], stdin: str = '') -> CommandResult:
        """Head command (simulated)"""
        n = int(args[0]) if args else 10
        lines = stdin.split('\n') if stdin else []
        output = '\n'.join(lines[:n]) + '\n' if lines[:n] else ''
        return CommandResult(success=True, output=output)

    dispatcher.register_commands({
        'echo': cmd_echo,
        'cat': cmd_cat,
        'grep': cmd_grep,
        'head': cmd_head,
    })

    # Test single command
    parser = ShellParser()
    print("=== Test 1: Single command ===")
    pipeline = parser.parse('echo Hello World')
    result = dispatcher.execute(pipeline, print_output=False)
    print(f"Output: {result.output!r}")
    print()

    # Test simple pipe
    print("=== Test 2: Simple pipe ===")
    pipeline = parser.parse('cat test | grep error')
    result = dispatcher.execute(pipeline, print_output=False)
    print(f"Output: {result.output!r}")
    print()

    # Test multi-stage pipe (would need actual data)
    print("=== Test 3: Command not found ===")
    pipeline = parser.parse('nonexistent command')
    result = dispatcher.execute(pipeline, print_output=False)
    print(f"Success: {result.success}")
    print(f"Error: {result.error}")
