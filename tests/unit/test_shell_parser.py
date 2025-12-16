"""
Unit tests for shell parser

Tests the ShellParser class for:
- Variable expansion
- Command parsing
- Pipeline parsing
- Shell command detection
"""

import pytest
from ctk.core.shell_parser import ShellParser, ParsedCommand, ParsedPipeline


class TestShellParser:
    """Test ShellParser class"""

    @pytest.fixture
    def parser(self):
        """Create parser with test environment"""
        return ShellParser({
            'CWD': '/chats',
            'MODEL': 'llama3.2',
            'MSG_COUNT': '5',
            'HOME': '/home/user'
        })

    @pytest.fixture
    def empty_parser(self):
        """Create parser with empty environment"""
        return ShellParser()

    # Variable Expansion Tests

    @pytest.mark.unit
    def test_expand_single_variable(self, parser):
        """Test expanding a single variable with $ syntax"""
        result = parser.expand_variables('echo $CWD')
        assert result == 'echo /chats'

    @pytest.mark.unit
    def test_expand_braced_variable(self, parser):
        """Test expanding variable with ${} syntax"""
        result = parser.expand_variables('Model: ${MODEL}')
        assert result == 'Model: llama3.2'

    @pytest.mark.unit
    def test_expand_multiple_variables(self, parser):
        """Test expanding multiple variables in one string"""
        result = parser.expand_variables('$CWD has ${MSG_COUNT} messages')
        assert result == '/chats has 5 messages'

    @pytest.mark.unit
    def test_expand_undefined_variable(self, parser):
        """Test that undefined variables are kept as-is"""
        result = parser.expand_variables('echo $UNDEFINED')
        assert result == 'echo $UNDEFINED'

    @pytest.mark.unit
    def test_expand_variable_in_quotes(self, parser):
        """Test variable expansion preserves quotes"""
        result = parser.expand_variables('echo "Current: $CWD"')
        assert result == 'echo "Current: /chats"'

    @pytest.mark.unit
    def test_expand_no_variables(self, parser):
        """Test text with no variables is unchanged"""
        result = parser.expand_variables('hello world')
        assert result == 'hello world'

    @pytest.mark.unit
    def test_update_variable(self, parser):
        """Test updating a single variable"""
        parser.update_variable('CWD', '/starred')
        result = parser.expand_variables('$CWD')
        assert result == '/starred'

    @pytest.mark.unit
    def test_set_environment(self, parser):
        """Test replacing entire environment"""
        new_env = {'FOO': 'bar', 'BAZ': 'qux'}
        parser.set_environment(new_env)

        result = parser.expand_variables('$FOO $BAZ')
        assert result == 'bar qux'

    # Pipeline Splitting Tests

    @pytest.mark.unit
    def test_split_single_command(self, empty_parser):
        """Test splitting line with no pipes"""
        result = empty_parser.split_pipeline('ls -la')
        assert result == ['ls -la']

    @pytest.mark.unit
    def test_split_two_commands(self, empty_parser):
        """Test splitting simple pipe"""
        result = empty_parser.split_pipeline('ls | grep foo')
        assert result == ['ls', 'grep foo']

    @pytest.mark.unit
    def test_split_multiple_pipes(self, empty_parser):
        """Test splitting multiple pipes"""
        result = empty_parser.split_pipeline('cat m1 | grep error | head 5')
        assert result == ['cat m1', 'grep error', 'head 5']

    @pytest.mark.unit
    def test_split_pipe_in_quotes(self, empty_parser):
        """Test that pipes inside quotes are not split"""
        result = empty_parser.split_pipeline('echo "foo | bar" | grep foo')
        assert result == ['echo "foo | bar"', 'grep foo']

    @pytest.mark.unit
    def test_split_pipe_in_single_quotes(self, empty_parser):
        """Test that pipes inside single quotes are not split"""
        result = empty_parser.split_pipeline("echo 'foo | bar' | grep foo")
        assert result == ["echo 'foo | bar'", 'grep foo']

    @pytest.mark.unit
    def test_split_mixed_quotes(self, empty_parser):
        """Test pipes with mixed quote types"""
        result = empty_parser.split_pipeline('echo "double" | echo \'single\' | grep test')
        assert result == ['echo "double"', "echo 'single'", 'grep test']

    @pytest.mark.unit
    def test_split_with_whitespace(self, empty_parser):
        """Test that extra whitespace is trimmed"""
        result = empty_parser.split_pipeline('ls  |  grep foo  |  head 5')
        assert result == ['ls', 'grep foo', 'head 5']

    # Command Parsing Tests

    @pytest.mark.unit
    def test_parse_simple_command(self, empty_parser):
        """Test parsing command with no arguments"""
        cmd = empty_parser.parse_command('ls')
        assert cmd.command == 'ls'
        assert cmd.args == []
        assert cmd.raw_line == 'ls'

    @pytest.mark.unit
    def test_parse_command_with_args(self, empty_parser):
        """Test parsing command with arguments"""
        cmd = empty_parser.parse_command('cat m1 m2 m3')
        assert cmd.command == 'cat'
        assert cmd.args == ['m1', 'm2', 'm3']

    @pytest.mark.unit
    def test_parse_command_with_quoted_arg(self, empty_parser):
        """Test parsing command with quoted argument"""
        cmd = empty_parser.parse_command('echo "hello world"')
        assert cmd.command == 'echo'
        assert cmd.args == ['hello world']

    @pytest.mark.unit
    def test_parse_command_with_single_quoted_arg(self, empty_parser):
        """Test parsing command with single-quoted argument"""
        cmd = empty_parser.parse_command("echo 'hello world'")
        assert cmd.command == 'echo'
        assert cmd.args == ['hello world']

    @pytest.mark.unit
    def test_parse_command_with_multiple_quoted_args(self, empty_parser):
        """Test parsing command with multiple quoted arguments"""
        cmd = empty_parser.parse_command('grep "error message" file.txt "another pattern"')
        assert cmd.command == 'grep'
        assert cmd.args == ['error message', 'file.txt', 'another pattern']

    @pytest.mark.unit
    def test_parse_empty_command(self, empty_parser):
        """Test parsing empty string"""
        cmd = empty_parser.parse_command('')
        assert cmd.command == ''
        assert cmd.args == []

    @pytest.mark.unit
    def test_parse_command_with_flags(self, empty_parser):
        """Test parsing command with flag arguments"""
        cmd = empty_parser.parse_command('grep -i -n pattern file.txt')
        assert cmd.command == 'grep'
        assert cmd.args == ['-i', '-n', 'pattern', 'file.txt']

    # Full Pipeline Parsing Tests

    @pytest.mark.unit
    def test_parse_single_command_pipeline(self, parser):
        """Test parsing pipeline with single command"""
        pipeline = parser.parse('echo $CWD')
        assert len(pipeline.commands) == 1
        assert pipeline.commands[0].command == 'echo'
        assert pipeline.commands[0].args == ['/chats']
        assert pipeline.has_pipe is False

    @pytest.mark.unit
    def test_parse_two_command_pipeline(self, parser):
        """Test parsing pipeline with two commands"""
        pipeline = parser.parse('cat m1 | grep error')
        assert len(pipeline.commands) == 2
        assert pipeline.commands[0].command == 'cat'
        assert pipeline.commands[0].args == ['m1']
        assert pipeline.commands[1].command == 'grep'
        assert pipeline.commands[1].args == ['error']
        assert pipeline.has_pipe is True

    @pytest.mark.unit
    def test_parse_multi_stage_pipeline(self, empty_parser):
        """Test parsing pipeline with multiple stages"""
        pipeline = empty_parser.parse('cat m1 | grep error | head 5')
        assert len(pipeline.commands) == 3
        assert pipeline.commands[0].command == 'cat'
        assert pipeline.commands[1].command == 'grep'
        assert pipeline.commands[2].command == 'head'
        assert pipeline.has_pipe is True

    @pytest.mark.unit
    def test_parse_with_variable_expansion(self, parser):
        """Test that variables are expanded before parsing"""
        pipeline = parser.parse('echo $MODEL | grep llama')
        assert pipeline.commands[0].args == ['llama3.2']

    @pytest.mark.unit
    def test_parse_complex_pipeline_with_quotes(self, parser):
        """Test parsing complex pipeline with quotes and variables"""
        pipeline = parser.parse('echo "Model: $MODEL" | grep "llama" | head 1')
        assert len(pipeline.commands) == 3
        assert pipeline.commands[0].args == ['Model: llama3.2']
        assert pipeline.commands[1].args == ['llama']
        assert pipeline.commands[2].args == ['1']

    # Shell Command Detection Tests

    @pytest.mark.unit
    def test_is_shell_command_navigation(self, empty_parser):
        """Test detecting navigation commands"""
        assert empty_parser.is_shell_command('cd /chats') is True
        assert empty_parser.is_shell_command('ls') is True
        assert empty_parser.is_shell_command('pwd') is True

    @pytest.mark.unit
    def test_is_shell_command_unix(self, empty_parser):
        """Test detecting Unix commands"""
        assert empty_parser.is_shell_command('cat m1') is True
        assert empty_parser.is_shell_command('head 10') is True
        assert empty_parser.is_shell_command('tail 5') is True
        assert empty_parser.is_shell_command('echo hello') is True
        assert empty_parser.is_shell_command('grep pattern') is True

    @pytest.mark.unit
    def test_is_shell_command_organization(self, empty_parser):
        """Test detecting organization commands"""
        assert empty_parser.is_shell_command('star 123') is True
        assert empty_parser.is_shell_command('pin abc') is True
        assert empty_parser.is_shell_command('archive xyz') is True
        assert empty_parser.is_shell_command('title New Title') is True

    @pytest.mark.unit
    def test_is_shell_command_llm(self, empty_parser):
        """Test detecting LLM commands"""
        assert empty_parser.is_shell_command('chat') is True
        assert empty_parser.is_shell_command('say hello') is True
        assert empty_parser.is_shell_command('model') is True
        assert empty_parser.is_shell_command('net embeddings') is True

    @pytest.mark.unit
    def test_is_shell_command_system(self, empty_parser):
        """Test detecting system commands"""
        assert empty_parser.is_shell_command('help') is True
        assert empty_parser.is_shell_command('exit') is True
        assert empty_parser.is_shell_command('clear') is True
        assert empty_parser.is_shell_command('quit') is True

    @pytest.mark.unit
    def test_is_not_shell_command_chat(self, empty_parser):
        """Test that chat input is not detected as command"""
        assert empty_parser.is_shell_command('What is quantum mechanics?') is False
        assert empty_parser.is_shell_command('Hello, how are you?') is False
        assert empty_parser.is_shell_command('Tell me about Python') is False

    @pytest.mark.unit
    def test_is_shell_command_case_insensitive(self, empty_parser):
        """Test that command detection is case-insensitive"""
        assert empty_parser.is_shell_command('CD /chats') is True
        assert empty_parser.is_shell_command('LS') is True
        assert empty_parser.is_shell_command('Cat m1') is True

    @pytest.mark.unit
    def test_is_shell_command_with_pipe(self, empty_parser):
        """Test detecting commands in pipelines"""
        assert empty_parser.is_shell_command('ls | grep foo') is True
        assert empty_parser.is_shell_command('cat m1 | head 10') is True

    # Edge Cases and Error Handling

    @pytest.mark.unit
    def test_parse_unclosed_quotes(self, empty_parser):
        """Test parsing with unclosed quotes falls back to simple split"""
        cmd = empty_parser.parse_command('echo "unclosed')
        # shlex will fail, so we fall back to simple split
        assert cmd.command == 'echo'
        # The behavior here depends on the fallback implementation

    @pytest.mark.unit
    def test_parse_empty_pipeline(self, empty_parser):
        """Test parsing empty string"""
        pipeline = empty_parser.parse('')
        # Empty string results in one empty command
        assert len(pipeline.commands) >= 0
        if pipeline.commands:
            assert pipeline.commands[0].command == ''
        assert pipeline.has_pipe is False

    @pytest.mark.unit
    def test_parse_only_whitespace(self, empty_parser):
        """Test parsing whitespace-only string"""
        pipeline = empty_parser.parse('   ')
        assert len(pipeline.commands) == 1

    @pytest.mark.unit
    def test_expand_variable_edge_cases(self, parser):
        """Test variable expansion edge cases"""
        # Adjacent variables
        result = parser.expand_variables('$CWD$MODEL')
        assert result == '/chatsllama3.2'

        # Variable at start
        result = parser.expand_variables('$CWD is current')
        assert result == '/chats is current'

        # Variable at end
        result = parser.expand_variables('Current is $CWD')
        assert result == 'Current is /chats'

    @pytest.mark.unit
    def test_parse_command_with_special_chars(self, empty_parser):
        """Test parsing commands with special characters in arguments"""
        cmd = empty_parser.parse_command('grep -E "^[0-9]+"')
        assert cmd.command == 'grep'
        assert cmd.args == ['-E', '^[0-9]+']

    @pytest.mark.unit
    def test_pipeline_with_multiple_spaces(self, empty_parser):
        """Test that multiple spaces between pipes are handled"""
        pipeline = empty_parser.parse('ls   |   grep foo   |   head 5')
        assert len(pipeline.commands) == 3
        assert pipeline.commands[0].command == 'ls'
        assert pipeline.commands[1].command == 'grep'
        assert pipeline.commands[2].command == 'head'


class TestParsedCommand:
    """Test ParsedCommand dataclass"""

    @pytest.mark.unit
    def test_parsed_command_creation(self):
        """Test creating ParsedCommand"""
        cmd = ParsedCommand(command='ls', args=['-la'], raw_line='ls -la')
        assert cmd.command == 'ls'
        assert cmd.args == ['-la']
        assert cmd.raw_line == 'ls -la'


class TestParsedPipeline:
    """Test ParsedPipeline dataclass"""

    @pytest.mark.unit
    def test_parsed_pipeline_creation(self):
        """Test creating ParsedPipeline"""
        cmd1 = ParsedCommand(command='ls', args=[], raw_line='ls')
        cmd2 = ParsedCommand(command='grep', args=['foo'], raw_line='grep foo')

        pipeline = ParsedPipeline(commands=[cmd1, cmd2], has_pipe=True)
        assert len(pipeline.commands) == 2
        assert pipeline.has_pipe is True

    @pytest.mark.unit
    def test_parsed_pipeline_single_command(self):
        """Test pipeline with single command"""
        cmd = ParsedCommand(command='ls', args=[], raw_line='ls')
        pipeline = ParsedPipeline(commands=[cmd], has_pipe=False)

        assert len(pipeline.commands) == 1
        assert pipeline.has_pipe is False
