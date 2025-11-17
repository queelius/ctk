"""
Unit tests for command dispatcher

Tests the CommandDispatcher class for:
- Command registration
- Command execution
- Pipeline execution
- Error handling
"""

import pytest
from ctk.core.command_dispatcher import CommandDispatcher, CommandResult
from ctk.core.shell_parser import ShellParser, ParsedCommand, ParsedPipeline


# Test command handlers
def cmd_echo(args, stdin=''):
    """Echo command - outputs args"""
    output = ' '.join(args) + '\n' if args else stdin
    return CommandResult(success=True, output=output)


def cmd_cat(args, stdin=''):
    """Cat command - outputs stdin or file content"""
    if stdin:
        return CommandResult(success=True, output=stdin)
    if args:
        return CommandResult(success=True, output=f"Content of {args[0]}\n")
    return CommandResult(success=False, error="cat: no input")


def cmd_grep(args, stdin=''):
    """Grep command - filters lines"""
    if not args:
        return CommandResult(success=False, error="grep: no pattern specified")

    pattern = args[0]
    lines = stdin.split('\n') if stdin else []
    matching = [line for line in lines if pattern in line]
    output = '\n'.join(matching) + ('\n' if matching else '')
    return CommandResult(success=True, output=output)


def cmd_head(args, stdin=''):
    """Head command - returns first n lines"""
    n = int(args[0]) if args else 10
    lines = stdin.split('\n') if stdin else []
    output_lines = lines[:n]
    output = '\n'.join(output_lines) + '\n' if output_lines else ''
    return CommandResult(success=True, output=output)


def cmd_fail(args, stdin=''):
    """Command that always fails"""
    return CommandResult(success=False, output='', error="Command failed intentionally")


def cmd_exception(args, stdin=''):
    """Command that raises exception"""
    raise RuntimeError("Something went wrong")


def cmd_tuple_return(args, stdin=''):
    """Command that returns tuple instead of CommandResult"""
    return (True, "Success output\n")


def cmd_string_return(args, stdin=''):
    """Command that returns string instead of CommandResult"""
    return "String output\n"


class TestCommandDispatcher:
    """Test CommandDispatcher class"""

    @pytest.fixture
    def dispatcher(self):
        """Create dispatcher with test commands"""
        d = CommandDispatcher()
        d.register_commands({
            'echo': cmd_echo,
            'cat': cmd_cat,
            'grep': cmd_grep,
            'head': cmd_head,
            'fail': cmd_fail,
            'exception': cmd_exception,
            'tuple': cmd_tuple_return,
            'string': cmd_string_return,
        })
        return d

    # Command Registration Tests

    @pytest.mark.unit
    def test_register_command(self):
        """Test registering a single command"""
        dispatcher = CommandDispatcher()
        dispatcher.register_command('test', cmd_echo)

        assert dispatcher.has_command('test')
        assert not dispatcher.has_command('nonexistent')

    @pytest.mark.unit
    def test_register_multiple_commands(self):
        """Test registering multiple commands at once"""
        dispatcher = CommandDispatcher()
        commands = {
            'cmd1': cmd_echo,
            'cmd2': cmd_cat,
            'cmd3': cmd_grep
        }
        dispatcher.register_commands(commands)

        assert dispatcher.has_command('cmd1')
        assert dispatcher.has_command('cmd2')
        assert dispatcher.has_command('cmd3')

    @pytest.mark.unit
    def test_has_command(self, dispatcher):
        """Test checking command existence"""
        assert dispatcher.has_command('echo')
        assert dispatcher.has_command('grep')
        assert not dispatcher.has_command('nonexistent')

    # Single Command Execution Tests

    @pytest.mark.unit
    def test_execute_simple_command(self, dispatcher):
        """Test executing simple command"""
        cmd = ParsedCommand(command='echo', args=['hello'], raw_line='echo hello')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.success is True
        assert result.output == 'hello\n'
        assert result.error is None

    @pytest.mark.unit
    def test_execute_command_with_stdin(self, dispatcher):
        """Test executing command with stdin"""
        cmd = ParsedCommand(command='cat', args=[], raw_line='cat')
        result = dispatcher.execute_command(cmd, stdin='test input\n')

        assert result.success is True
        assert result.output == 'test input\n'

    @pytest.mark.unit
    def test_execute_nonexistent_command(self, dispatcher):
        """Test executing command that doesn't exist"""
        cmd = ParsedCommand(command='nonexistent', args=[], raw_line='nonexistent')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.success is False
        assert 'Command not found' in result.error
        assert result.exit_code == 127

    @pytest.mark.unit
    def test_execute_command_that_fails(self, dispatcher):
        """Test executing command that returns failure"""
        cmd = ParsedCommand(command='fail', args=[], raw_line='fail')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.success is False
        assert 'failed intentionally' in result.error

    @pytest.mark.unit
    def test_execute_command_with_exception(self, dispatcher):
        """Test executing command that raises exception"""
        cmd = ParsedCommand(command='exception', args=[], raw_line='exception')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.success is False
        assert 'Something went wrong' in result.error
        assert result.exit_code == 1

    @pytest.mark.unit
    def test_execute_command_tuple_return(self, dispatcher):
        """Test command that returns tuple is normalized"""
        cmd = ParsedCommand(command='tuple', args=[], raw_line='tuple')
        result = dispatcher.execute_command(cmd, stdin='')

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.output == 'Success output\n'

    @pytest.mark.unit
    def test_execute_command_string_return(self, dispatcher):
        """Test command that returns string is normalized"""
        cmd = ParsedCommand(command='string', args=[], raw_line='string')
        result = dispatcher.execute_command(cmd, stdin='')

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.output == 'String output\n'

    @pytest.mark.unit
    def test_execute_command_case_insensitive(self, dispatcher):
        """Test that command names are case-insensitive"""
        cmd = ParsedCommand(command='ECHO', args=['test'], raw_line='ECHO test')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.success is True
        assert result.output == 'test\n'

    # Pipeline Execution Tests

    @pytest.mark.unit
    def test_execute_single_command_pipeline(self, dispatcher):
        """Test executing pipeline with single command"""
        cmd = ParsedCommand(command='echo', args=['hello'], raw_line='echo hello')
        pipeline = ParsedPipeline(commands=[cmd], has_pipe=False)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        assert result.output == 'hello\n'

    @pytest.mark.unit
    def test_execute_two_command_pipeline(self, dispatcher):
        """Test executing pipeline with two commands"""
        cmd1 = ParsedCommand(command='echo', args=['hello\nworld\n'], raw_line='echo hello world')
        cmd2 = ParsedCommand(command='grep', args=['world'], raw_line='grep world')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        assert 'world' in result.output
        assert 'hello' not in result.output

    @pytest.mark.unit
    def test_execute_multi_stage_pipeline(self, dispatcher):
        """Test executing pipeline with multiple stages"""
        # echo "line1\nline2\nline3\n" | grep "line" | head 2
        cmd1 = ParsedCommand(command='echo', args=['line1\nline2\nline3'], raw_line='...')
        cmd2 = ParsedCommand(command='grep', args=['line'], raw_line='...')
        cmd3 = ParsedCommand(command='head', args=['2'], raw_line='...')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2, cmd3], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        lines = [l for l in result.output.split('\n') if l]
        assert len(lines) == 2

    @pytest.mark.unit
    def test_pipeline_stops_on_error(self, dispatcher):
        """Test that pipeline stops when command fails"""
        cmd1 = ParsedCommand(command='echo', args=['test'], raw_line='...')
        cmd2 = ParsedCommand(command='fail', args=[], raw_line='...')
        cmd3 = ParsedCommand(command='echo', args=['should not run'], raw_line='...')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2, cmd3], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is False
        assert 'failed intentionally' in result.error

    @pytest.mark.unit
    def test_pipeline_first_command_fails(self, dispatcher):
        """Test pipeline when first command fails"""
        cmd1 = ParsedCommand(command='fail', args=[], raw_line='...')
        cmd2 = ParsedCommand(command='echo', args=['never runs'], raw_line='...')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is False
        assert 'never runs' not in result.output

    @pytest.mark.unit
    def test_execute_empty_pipeline(self, dispatcher):
        """Test executing empty pipeline"""
        pipeline = ParsedPipeline(commands=[], has_pipe=False)
        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is False
        assert 'No command to execute' in result.error

    # Integration with ShellParser

    @pytest.mark.unit
    def test_full_pipeline_parsing_and_execution(self, dispatcher):
        """Test parsing and executing full pipeline"""
        parser = ShellParser()
        pipeline = parser.parse('echo "line1\nline2\nline3" | grep line')

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        assert 'line' in result.output

    # Execute Method Tests

    @pytest.mark.unit
    def test_execute_without_print(self, dispatcher):
        """Test execute method without printing"""
        parser = ShellParser()
        pipeline = parser.parse('echo test')

        result = dispatcher.execute(pipeline, print_output=False)

        assert result.success is True
        assert result.output == 'test\n'

    @pytest.mark.unit
    def test_execute_with_print(self, dispatcher, capsys):
        """Test execute method with printing"""
        parser = ShellParser()
        pipeline = parser.parse('echo printed')

        result = dispatcher.execute(pipeline, print_output=True)

        captured = capsys.readouterr()
        assert 'printed' in captured.out

    @pytest.mark.unit
    def test_execute_prints_error(self, dispatcher, capsys):
        """Test execute method prints errors to stderr"""
        parser = ShellParser()
        pipeline = parser.parse('fail')

        result = dispatcher.execute(pipeline, print_output=True)

        captured = capsys.readouterr()
        assert 'Error:' in captured.err
        assert 'failed intentionally' in captured.err


class TestCommandResult:
    """Test CommandResult dataclass"""

    @pytest.mark.unit
    def test_command_result_creation(self):
        """Test creating CommandResult"""
        result = CommandResult(
            success=True,
            output='test output',
            error=None,
            exit_code=0
        )

        assert result.success is True
        assert result.output == 'test output'
        assert result.error is None
        assert result.exit_code == 0

    @pytest.mark.unit
    def test_command_result_defaults(self):
        """Test CommandResult default values"""
        result = CommandResult(success=True, output='test')

        assert result.error is None
        assert result.exit_code == 0

    @pytest.mark.unit
    def test_command_result_with_error(self):
        """Test CommandResult with error"""
        result = CommandResult(
            success=False,
            output='',
            error='Something failed',
            exit_code=1
        )

        assert result.success is False
        assert result.error == 'Something failed'
        assert result.exit_code == 1


class TestPipelineDataFlow:
    """Test data flow through pipelines"""

    @pytest.fixture
    def dispatcher(self):
        """Create dispatcher with test commands"""
        d = CommandDispatcher()
        d.register_commands({
            'echo': cmd_echo,
            'cat': cmd_cat,
            'grep': cmd_grep,
            'head': cmd_head,
        })
        return d

    @pytest.mark.unit
    def test_data_flows_through_pipe(self, dispatcher):
        """Test that data flows correctly through pipe"""
        # Create commands manually to verify data flow
        cmd1 = ParsedCommand(command='echo', args=['test\ndata\n'], raw_line='...')
        cmd2 = ParsedCommand(command='cat', args=[], raw_line='...')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        # cat should receive echo's output
        assert 'test' in result.output
        assert 'data' in result.output

    @pytest.mark.unit
    def test_grep_filters_data(self, dispatcher):
        """Test grep properly filters piped data"""
        cmd1 = ParsedCommand(command='echo', args=['apple\nbanana\ncherry\n'], raw_line='...')
        cmd2 = ParsedCommand(command='grep', args=['an'], raw_line='...')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        assert 'banana' in result.output
        assert 'apple' not in result.output
        assert 'cherry' not in result.output

    @pytest.mark.unit
    def test_head_limits_output(self, dispatcher):
        """Test head properly limits lines"""
        # Generate multiple lines
        lines = '\n'.join([f'line{i}' for i in range(10)])
        cmd1 = ParsedCommand(command='echo', args=[lines], raw_line='...')
        cmd2 = ParsedCommand(command='head', args=['3'], raw_line='...')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        output_lines = [l for l in result.output.split('\n') if l]
        assert len(output_lines) == 3

    @pytest.mark.unit
    def test_three_stage_pipeline_data_flow(self, dispatcher):
        """Test data flows through three-stage pipeline"""
        # echo -> grep -> head
        cmd1 = ParsedCommand(command='echo', args=['a1\na2\nb1\nb2\nc1\nc2\n'], raw_line='...')
        cmd2 = ParsedCommand(command='grep', args=['a'], raw_line='...')
        cmd3 = ParsedCommand(command='head', args=['1'], raw_line='...')
        pipeline = ParsedPipeline(commands=[cmd1, cmd2, cmd3], has_pipe=True)

        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        assert 'a1' in result.output
        assert 'a2' not in result.output  # Should be filtered by head

    @pytest.mark.unit
    def test_empty_stdin_to_command(self, dispatcher):
        """Test command receiving empty stdin"""
        cmd = ParsedCommand(command='cat', args=[], raw_line='cat')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.success is False
        assert 'no input' in result.error


class TestEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.fixture
    def dispatcher(self):
        """Create dispatcher with test commands"""
        d = CommandDispatcher()
        d.register_commands({
            'echo': cmd_echo,
            'cat': cmd_cat,
            'grep': cmd_grep,
            'head': cmd_head,
        })
        return d

    @pytest.mark.unit
    def test_command_with_no_args_no_stdin(self, dispatcher):
        """Test command with neither args nor stdin"""
        cmd = ParsedCommand(command='echo', args=[], raw_line='echo')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.success is True
        # Echo with no args and no stdin just outputs empty line

    @pytest.mark.unit
    def test_very_long_pipeline(self, dispatcher):
        """Test pipeline with many stages"""
        commands = []
        commands.append(ParsedCommand(command='echo', args=['test'], raw_line='...'))

        for _ in range(10):
            commands.append(ParsedCommand(command='cat', args=[], raw_line='...'))

        pipeline = ParsedPipeline(commands=commands, has_pipe=True)
        result = dispatcher.execute_pipeline(pipeline)

        assert result.success is True
        assert 'test' in result.output

    @pytest.mark.unit
    def test_command_returns_none(self):
        """Test handling command that returns None"""
        def cmd_none(args, stdin=''):
            return None

        dispatcher = CommandDispatcher()
        dispatcher.register_command('none', cmd_none)

        cmd = ParsedCommand(command='none', args=[], raw_line='none')
        result = dispatcher.execute_command(cmd, stdin='')

        # Should handle None gracefully
        assert isinstance(result, CommandResult)

    @pytest.mark.unit
    def test_register_same_command_twice(self):
        """Test that re-registering command overwrites"""
        def cmd_v1(args, stdin=''):
            return CommandResult(success=True, output='v1\n')

        def cmd_v2(args, stdin=''):
            return CommandResult(success=True, output='v2\n')

        dispatcher = CommandDispatcher()
        dispatcher.register_command('test', cmd_v1)
        dispatcher.register_command('test', cmd_v2)

        cmd = ParsedCommand(command='test', args=[], raw_line='test')
        result = dispatcher.execute_command(cmd, stdin='')

        assert result.output == 'v2\n'  # Second version should be used
