"""
Comprehensive edge case tests for the JSONL importer.

Tests cover: validation, model detection, message extraction,
import_data behavior, and various edge cases.
"""

import json
from datetime import datetime

import pytest

from ctk.core.models import MessageRole
from ctk.integrations.importers.jsonl import JSONLImporter


# ---------------------------------------------------------------------------
# TestJSONLValidation
# ---------------------------------------------------------------------------
class TestJSONLValidation:
    """Tests for JSONLImporter.validate()"""

    def setup_method(self):
        self.importer = JSONLImporter()

    # -- String inputs that should validate --

    @pytest.mark.unit
    def test_valid_jsonl_string_role_content(self):
        """JSONL string with role+content on the first line validates True."""
        data = '{"role": "user", "content": "hello"}\n{"role": "assistant", "content": "hi"}'
        assert self.importer.validate(data) is True

    @pytest.mark.unit
    def test_valid_jsonl_string_messages_key(self):
        """JSONL string whose first line has a messages key validates True."""
        data = json.dumps({"messages": [{"role": "user", "content": "hi"}]})
        assert self.importer.validate(data) is True

    @pytest.mark.unit
    def test_valid_jsonl_string_conversations_key(self):
        """JSONL string whose first line has a conversations key validates True."""
        data = json.dumps({"conversations": [{"role": "user", "content": "hi"}]})
        assert self.importer.validate(data) is True

    @pytest.mark.unit
    def test_valid_jsonl_string_single_line(self):
        """A single-line JSONL string with role+content validates True."""
        data = '{"role": "system", "content": "You are helpful."}'
        assert self.importer.validate(data) is True

    # -- Dict inputs that should validate --

    @pytest.mark.unit
    def test_valid_dict_with_messages(self):
        """Dict with a 'messages' key validates True."""
        data = {"messages": [{"role": "user", "content": "hello"}]}
        assert self.importer.validate(data) is True

    @pytest.mark.unit
    def test_valid_dict_with_conversations(self):
        """Dict with a 'conversations' key validates True."""
        data = {"conversations": [{"role": "user", "content": "hello"}]}
        assert self.importer.validate(data) is True

    # -- List inputs that should validate --

    @pytest.mark.unit
    def test_valid_list_role_content(self):
        """List of dicts with role+content validates True."""
        data = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        assert self.importer.validate(data) is True

    @pytest.mark.unit
    def test_valid_list_with_messages_objects(self):
        """List of conversation objects containing 'messages' validates True."""
        data = [{"messages": [{"role": "user", "content": "hi"}]}]
        assert self.importer.validate(data) is True

    @pytest.mark.unit
    def test_valid_list_with_conversations_objects(self):
        """List of objects containing 'conversations' key validates True."""
        data = [{"conversations": [{"role": "user", "content": "hi"}]}]
        assert self.importer.validate(data) is True

    # -- Inputs that should NOT validate --

    @pytest.mark.unit
    def test_invalid_empty_dict(self):
        """Empty dict has no 'messages' or 'conversations' key -> False."""
        assert self.importer.validate({}) is False

    @pytest.mark.unit
    def test_invalid_empty_list(self):
        """Empty list has no first element to inspect -> False."""
        assert self.importer.validate([]) is False

    @pytest.mark.unit
    def test_invalid_integer(self):
        """An integer is not str/dict/list -> False."""
        assert self.importer.validate(42) is False

    @pytest.mark.unit
    def test_invalid_none(self):
        """None is not str/dict/list -> False."""
        assert self.importer.validate(None) is False

    @pytest.mark.unit
    def test_invalid_empty_string(self):
        """Empty string has no parseable JSON -> False."""
        assert self.importer.validate("") is False

    @pytest.mark.unit
    def test_invalid_malformed_json_string(self):
        """A string that is not valid JSON -> False."""
        assert self.importer.validate("this is not json at all") is False

    @pytest.mark.unit
    def test_invalid_json_string_missing_required_keys(self):
        """JSON string without role/content/messages/conversations -> False."""
        data = '{"foo": "bar"}'
        assert self.importer.validate(data) is False

    @pytest.mark.unit
    def test_invalid_dict_unrelated_keys(self):
        """Dict with unrelated keys -> False."""
        data = {"title": "hi", "author": "someone"}
        assert self.importer.validate(data) is False

    @pytest.mark.unit
    def test_invalid_list_of_non_dicts(self):
        """List of non-dict items (strings) -> False."""
        data = ["hello", "world"]
        assert self.importer.validate(data) is False

    @pytest.mark.unit
    def test_invalid_list_missing_keys(self):
        """List of dicts that lack role/content/messages/conversations -> False."""
        data = [{"foo": "bar"}]
        assert self.importer.validate(data) is False


# ---------------------------------------------------------------------------
# TestJSONLModelDetection
# ---------------------------------------------------------------------------
class TestJSONLModelDetection:
    """Tests for JSONLImporter._detect_model()"""

    def setup_method(self):
        self.importer = JSONLImporter()

    @pytest.mark.unit
    def test_dict_with_model_field(self):
        """Dict with explicit model field returns that model name."""
        data = {"model": "my-custom-model", "messages": []}
        assert self.importer._detect_model(data) == "my-custom-model"

    @pytest.mark.unit
    def test_dict_model_field_takes_priority_over_hints(self):
        """Explicit model field in dict takes priority over text hints."""
        data = {"model": "custom-llama-variant", "content": "something about mistral"}
        result = self.importer._detect_model(data)
        assert result == "custom-llama-variant"

    @pytest.mark.unit
    def test_hint_llama(self):
        """Data containing 'llama' returns 'LLaMA'."""
        data = "I used llama-2-7b for this"
        assert self.importer._detect_model(data) == "LLaMA"

    @pytest.mark.unit
    def test_hint_mistral(self):
        """Data containing 'mistral' returns 'Mistral'."""
        data = "Generated by mistral-7b"
        assert self.importer._detect_model(data) == "Mistral"

    @pytest.mark.unit
    def test_hint_deepseek(self):
        """Data containing 'deepseek' returns 'DeepSeek'."""
        data = "deepseek-coder output"
        assert self.importer._detect_model(data) == "DeepSeek"

    @pytest.mark.unit
    def test_hint_phi(self):
        """Data containing 'phi' returns 'Phi'."""
        data = "phi-2 model response"
        assert self.importer._detect_model(data) == "Phi"

    @pytest.mark.unit
    def test_hint_alpaca(self):
        """Data containing 'alpaca' returns 'Alpaca'."""
        data = "alpaca finetuned dataset"
        assert self.importer._detect_model(data) == "Alpaca"

    @pytest.mark.unit
    def test_hint_gemma(self):
        """Data containing 'gemma' returns 'Gemma'."""
        data = [{"role": "user", "content": "gemma test"}]
        assert self.importer._detect_model(data) == "Gemma"

    @pytest.mark.unit
    def test_hint_qwen(self):
        """Data containing 'qwen' returns 'Qwen'."""
        data = {"messages": [], "source": "qwen-72b"}
        # dict without 'model' key, so falls through to string scan
        assert self.importer._detect_model(data) == "Qwen"

    @pytest.mark.unit
    def test_multiple_hints_first_wins(self):
        """When multiple hints match, the first in iteration order wins."""
        # model_hints is an ordered dict (Python 3.7+).
        # "llama" comes before "mistral" in the dict, so LLaMA should win.
        data = "trained on llama and mistral"
        result = self.importer._detect_model(data)
        assert result == "LLaMA"

    @pytest.mark.unit
    def test_no_hints_returns_local_llm(self):
        """When no model hints match, returns 'Local LLM'."""
        data = "some generic conversation data"
        assert self.importer._detect_model(data) == "Local LLM"

    @pytest.mark.unit
    def test_dict_empty_model_field_falls_through(self):
        """Dict with empty-string model field falls through to hint scan."""
        data = {"model": "", "info": "llama fine-tune"}
        # Empty string is falsy so it falls through to hint scanning
        assert self.importer._detect_model(data) == "LLaMA"

    @pytest.mark.unit
    def test_dict_without_model_key_uses_hints(self):
        """Dict without 'model' key falls through to string-based hint scan."""
        data = {"description": "falcon model output"}
        assert self.importer._detect_model(data) == "Falcon"


# ---------------------------------------------------------------------------
# TestJSONLExtractMessages
# ---------------------------------------------------------------------------
class TestJSONLExtractMessages:
    """Tests for JSONLImporter._extract_messages()"""

    def setup_method(self):
        self.importer = JSONLImporter()

    @pytest.mark.unit
    def test_role_content_lines_single_conversation(self):
        """Consecutive role+content JSONL lines form a single conversation."""
        data = (
            '{"role": "user", "content": "Hello"}\n'
            '{"role": "assistant", "content": "Hi there"}'
        )
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["content"] == "Hi there"

    @pytest.mark.unit
    def test_conversation_break_marker(self):
        """conversation_break: true separates conversations."""
        data = (
            '{"role": "user", "content": "Conv 1"}\n'
            '{"role": "assistant", "content": "Reply 1"}\n'
            '{"conversation_break": true}\n'
            '{"role": "user", "content": "Conv 2"}\n'
            '{"role": "assistant", "content": "Reply 2"}'
        )
        convs = self.importer._extract_messages(data)
        assert len(convs) == 2
        assert len(convs[0][0]) == 2
        assert len(convs[1][0]) == 2
        assert convs[0][0][0]["content"] == "Conv 1"
        assert convs[1][0][0]["content"] == "Conv 2"

    @pytest.mark.unit
    def test_blank_lines_separate_conversations(self):
        """Blank lines between JSONL blocks create separate conversations."""
        data = (
            '{"role": "user", "content": "First"}\n'
            '{"role": "assistant", "content": "Reply first"}\n'
            "\n"
            '{"role": "user", "content": "Second"}\n'
            '{"role": "assistant", "content": "Reply second"}'
        )
        convs = self.importer._extract_messages(data)
        assert len(convs) == 2
        assert convs[0][0][0]["content"] == "First"
        assert convs[1][0][0]["content"] == "Second"

    @pytest.mark.unit
    def test_metadata_line_not_a_message(self):
        """A line with only 'metadata' key updates metadata, not messages."""
        data = (
            '{"metadata": {"title": "My Chat", "model": "gpt-4"}}\n'
            '{"role": "user", "content": "Hello"}\n'
            '{"role": "assistant", "content": "Hi"}'
        )
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 2  # metadata line is not a message
        assert metadata.get("title") == "My Chat"
        assert metadata.get("model") == "gpt-4"

    @pytest.mark.unit
    def test_metadata_line_must_be_sole_key(self):
        """A line with 'metadata' PLUS other keys is not treated as pure metadata."""
        # Because len(obj) != 1 when there are extra keys, it won't match the
        # metadata-only branch.  It will also not match role+content or other patterns.
        data = '{"metadata": {"title": "X"}, "extra": "stuff"}\n{"role": "user", "content": "hi"}'
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        # The metadata-plus-extra line is NOT treated as pure metadata
        assert "title" not in metadata
        # The user message is still present
        assert len(messages) == 1

    @pytest.mark.unit
    def test_full_conversation_per_line_messages_key(self):
        """Each line having a 'messages' key creates a separate conversation."""
        line1 = json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Q1"},
                    {"role": "assistant", "content": "A1"},
                ],
                "id": "conv1",
            }
        )
        line2 = json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Q2"},
                    {"role": "assistant", "content": "A2"},
                ],
                "id": "conv2",
            }
        )
        data = f"{line1}\n{line2}"
        convs = self.importer._extract_messages(data)
        assert len(convs) == 2
        assert convs[0][0][0]["content"] == "Q1"
        assert convs[0][1]["id"] == "conv1"
        assert convs[1][0][0]["content"] == "Q2"

    @pytest.mark.unit
    def test_full_conversation_per_line_conversations_key(self):
        """Lines with 'conversations' key (alternative naming) also work."""
        line = json.dumps(
            {
                "conversations": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                ],
                "source": "custom",
            }
        )
        convs = self.importer._extract_messages(line)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 2
        assert metadata.get("source") == "custom"

    @pytest.mark.unit
    def test_instruction_response_format(self):
        """instruction/response lines produce user+assistant pairs."""
        data = json.dumps({"instruction": "Tell me a joke", "response": "Why did..."})
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Tell me a joke"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Why did..."

    @pytest.mark.unit
    def test_instruction_response_with_system(self):
        """instruction/response format with 'system' field adds system message."""
        data = json.dumps(
            {
                "system": "You are a comedian",
                "instruction": "Tell me a joke",
                "response": "Why did the chicken...",
            }
        )
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a comedian"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"

    @pytest.mark.unit
    def test_instruction_response_extra_metadata(self):
        """Extra keys in instruction/response format are preserved as metadata."""
        data = json.dumps(
            {
                "instruction": "Q",
                "response": "A",
                "category": "math",
                "difficulty": "easy",
            }
        )
        convs = self.importer._extract_messages(data)
        messages, metadata = convs[0]
        assert metadata["category"] == "math"
        assert metadata["difficulty"] == "easy"
        # system/instruction/response should be excluded from metadata
        assert "instruction" not in metadata
        assert "response" not in metadata

    @pytest.mark.unit
    def test_prompt_completion_format(self):
        """prompt/completion format produces user+assistant pair."""
        data = json.dumps({"prompt": "Complete this:", "completion": "Done!"})
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Complete this:"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Done!"

    @pytest.mark.unit
    def test_prompt_completion_extra_metadata(self):
        """Extra keys in prompt/completion format are preserved as metadata."""
        data = json.dumps({"prompt": "P", "completion": "C", "source": "dataset-v2"})
        convs = self.importer._extract_messages(data)
        _, metadata = convs[0]
        assert metadata["source"] == "dataset-v2"
        assert "prompt" not in metadata
        assert "completion" not in metadata

    @pytest.mark.unit
    def test_malformed_jsonl_line_skipped(self):
        """Malformed lines are silently skipped."""
        data = (
            '{"role": "user", "content": "Hello"}\n'
            "this is not json\n"
            '{"role": "assistant", "content": "Hi"}'
        )
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, _ = convs[0]
        assert len(messages) == 2

    @pytest.mark.unit
    def test_dict_with_messages_key(self):
        """Dict input with 'messages' key extracts correctly."""
        data = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ],
            "model": "gpt-4",
        }
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 2
        assert metadata.get("model") == "gpt-4"
        assert "messages" not in metadata

    @pytest.mark.unit
    def test_dict_with_conversations_key(self):
        """Dict input with 'conversations' key extracts correctly."""
        data = {
            "conversations": [
                {"role": "user", "content": "Hello"},
            ],
            "id": "abc",
        }
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 1
        assert metadata.get("id") == "abc"
        assert "conversations" not in metadata

    @pytest.mark.unit
    def test_list_of_conversation_objects(self):
        """List of objects with 'messages' key -> multiple conversations."""
        data = [
            {"messages": [{"role": "user", "content": "Q1"}]},
            {"messages": [{"role": "user", "content": "Q2"}]},
        ]
        convs = self.importer._extract_messages(data)
        assert len(convs) == 2
        assert convs[0][0][0]["content"] == "Q1"
        assert convs[1][0][0]["content"] == "Q2"

    @pytest.mark.unit
    def test_list_of_message_dicts(self):
        """List of role+content dicts -> single conversation."""
        data = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        messages, metadata = convs[0]
        assert len(messages) == 2
        assert metadata == {}

    @pytest.mark.unit
    def test_empty_string_returns_empty(self):
        """Empty string returns no conversations."""
        convs = self.importer._extract_messages("")
        assert convs == []

    @pytest.mark.unit
    def test_empty_dict_returns_empty(self):
        """Empty dict (no 'messages' or 'conversations') returns nothing."""
        convs = self.importer._extract_messages({})
        assert convs == []

    @pytest.mark.unit
    def test_empty_list_returns_empty(self):
        """Empty list returns nothing."""
        convs = self.importer._extract_messages([])
        assert convs == []

    @pytest.mark.unit
    def test_conversation_break_at_start(self):
        """conversation_break at the very start (no prior messages) is harmless."""
        data = '{"conversation_break": true}\n' '{"role": "user", "content": "Hello"}'
        convs = self.importer._extract_messages(data)
        assert len(convs) == 1
        assert convs[0][0][0]["content"] == "Hello"

    @pytest.mark.unit
    def test_multiple_blank_lines(self):
        """Multiple consecutive blank lines don't create empty conversations."""
        data = (
            '{"role": "user", "content": "A"}\n'
            "\n"
            "\n"
            "\n"
            '{"role": "user", "content": "B"}'
        )
        convs = self.importer._extract_messages(data)
        # The first blank line flushes conv A; subsequent blanks have no accumulated messages
        assert len(convs) == 2
        assert convs[0][0][0]["content"] == "A"
        assert convs[1][0][0]["content"] == "B"


# ---------------------------------------------------------------------------
# TestJSONLImportData
# ---------------------------------------------------------------------------
class TestJSONLImportData:
    """Tests for JSONLImporter.import_data()"""

    def setup_method(self):
        self.importer = JSONLImporter()

    @pytest.mark.unit
    def test_basic_import_from_jsonl_string(self):
        """Basic JSONL string produces a ConversationTree with correct messages."""
        data = (
            '{"role": "user", "content": "Hello"}\n'
            '{"role": "assistant", "content": "Hi there"}'
        )
        trees = self.importer.import_data(data)
        assert len(trees) == 1
        tree = trees[0]
        messages = tree.get_longest_path()
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "Hello"
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[1].content.text == "Hi there"

    @pytest.mark.unit
    def test_role_mapping_human_to_user(self):
        """Role 'human' is mapped to USER."""
        data = [{"role": "human", "content": "Hello"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.role == MessageRole.USER

    @pytest.mark.unit
    def test_role_mapping_ai_to_assistant(self):
        """Role 'ai' is mapped to ASSISTANT."""
        data = [{"role": "ai", "content": "Hi"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_mapping_bot_to_assistant(self):
        """Role 'bot' is mapped to ASSISTANT."""
        data = [{"role": "bot", "content": "Hi"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_mapping_model_to_assistant(self):
        """Role 'model' is mapped to ASSISTANT."""
        data = [{"role": "model", "content": "Hi"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_mapping_gpt_to_assistant(self):
        """Role 'gpt' is mapped to ASSISTANT."""
        data = [{"role": "gpt", "content": "Hi"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_mapping_system(self):
        """Role 'system' stays as SYSTEM."""
        data = [{"role": "system", "content": "Be helpful"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.role == MessageRole.SYSTEM

    @pytest.mark.unit
    def test_multimodal_content_list_with_strings(self):
        """Content as a list of strings is joined with newlines."""
        data = [{"role": "user", "content": ["Part one", "Part two"]}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert "Part one" in msg.content.text
        assert "Part two" in msg.content.text
        # parts field is populated
        assert msg.content.parts == ["Part one", "Part two"]

    @pytest.mark.unit
    def test_multimodal_content_list_with_text_dicts(self):
        """Content as a list of {type: text, text: ...} dicts is joined."""
        data = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this"},
                    {"type": "image_url", "url": "http://example.com/img.png"},
                ],
            }
        ]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert "Describe this" in msg.content.text
        # Non-text parts stored in content metadata
        assert "parts" in msg.content.metadata
        assert any(p.get("type") == "image_url" for p in msg.content.metadata["parts"])

    @pytest.mark.unit
    def test_timestamp_from_timestamp_field(self):
        """Numeric timestamp field is parsed into datetime."""
        ts = 1700000000.0  # 2023-11-14 approx
        data = [{"role": "user", "content": "hi", "timestamp": ts}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.timestamp is not None
        assert isinstance(msg.timestamp, datetime)
        assert msg.timestamp == datetime.fromtimestamp(ts)

    @pytest.mark.unit
    def test_timestamp_from_created_at_field(self):
        """ISO-format created_at field is parsed into datetime."""
        dt_str = "2024-06-15T10:30:00"
        data = [{"role": "user", "content": "hi", "created_at": dt_str}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.timestamp is not None
        assert msg.timestamp == datetime.fromisoformat(dt_str)

    @pytest.mark.unit
    def test_timestamp_field_takes_priority_over_created_at(self):
        """When both timestamp and created_at exist, timestamp is used."""
        ts = 1700000000.0
        data = [
            {
                "role": "user",
                "content": "hi",
                "timestamp": ts,
                "created_at": "2020-01-01T00:00:00",
            }
        ]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.timestamp == datetime.fromtimestamp(ts)

    @pytest.mark.unit
    def test_title_from_first_user_message(self):
        """Title is derived from first user message when no title in metadata."""
        data = [
            {"role": "user", "content": "What is photosynthesis?"},
            {"role": "assistant", "content": "It is..."},
        ]
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert tree.title == "What is photosynthesis?"

    @pytest.mark.unit
    def test_title_truncation_at_50_chars(self):
        """Title from first user message is truncated to 50 chars + '...'."""
        long_msg = "A" * 100
        data = [{"role": "user", "content": long_msg}]
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert tree.title == "A" * 50 + "..."
        assert len(tree.title) == 53

    @pytest.mark.unit
    def test_title_exactly_50_chars_no_ellipsis(self):
        """A message exactly 50 chars long does NOT get '...' appended."""
        msg = "B" * 50
        data = [{"role": "user", "content": msg}]
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert tree.title == msg
        assert "..." not in tree.title

    @pytest.mark.unit
    def test_title_from_metadata(self):
        """Metadata title overrides first-user-message heuristic."""
        data = (
            '{"metadata": {"title": "My Custom Title"}}\n'
            '{"role": "user", "content": "Hello"}\n'
            '{"role": "assistant", "content": "Hi"}'
        )
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert tree.title == "My Custom Title"

    @pytest.mark.unit
    def test_title_fallback_untitled_when_no_user_message(self):
        """If no user/human messages exist, title stays 'Untitled Conversation'."""
        data = [
            {"role": "system", "content": "You are helpful"},
            {"role": "assistant", "content": "How can I help?"},
        ]
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert tree.title == "Untitled Conversation"

    @pytest.mark.unit
    def test_empty_messages_skipped(self):
        """Conversations with empty messages list are skipped entirely."""
        data = {
            "messages": [],
        }
        trees = self.importer.import_data(data)
        assert len(trees) == 0

    @pytest.mark.unit
    def test_metadata_propagated_to_custom_data(self):
        """Extra fields from conversation metadata appear in custom_data."""
        line = json.dumps(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "id": "conv-123",
                "category": "science",
                "difficulty": "hard",
            }
        )
        trees = self.importer.import_data(line)
        tree = trees[0]
        assert tree.metadata.custom_data.get("category") == "science"
        assert tree.metadata.custom_data.get("difficulty") == "hard"

    @pytest.mark.unit
    def test_conv_id_from_metadata(self):
        """Conversation ID is taken from conv_metadata 'id' field if present."""
        line = json.dumps(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "id": "my-custom-id",
            }
        )
        trees = self.importer.import_data(line)
        assert trees[0].id == "my-custom-id"

    @pytest.mark.unit
    def test_conv_id_generated_when_not_provided(self):
        """Conversation ID is auto-generated when no 'id' in metadata."""
        data = [{"role": "user", "content": "Hello"}]
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert tree.id.startswith("jsonl_0_")

    @pytest.mark.unit
    def test_model_in_metadata_overrides_detection(self):
        """Conv-level model from metadata overrides the detected model."""
        line = json.dumps(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "model": "custom-model-v3",
            }
        )
        trees = self.importer.import_data(line)
        tree = trees[0]
        assert tree.metadata.model == "custom-model-v3"

    @pytest.mark.unit
    def test_metadata_tags_include_model(self):
        """Tags include 'local', 'jsonl', and a lowercased model name."""
        data = [{"role": "user", "content": "hi"}]
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert "local" in tree.metadata.tags
        assert "jsonl" in tree.metadata.tags

    @pytest.mark.unit
    def test_metadata_source_is_local(self):
        """Source metadata is always 'Local'."""
        data = [{"role": "user", "content": "hi"}]
        trees = self.importer.import_data(data)
        assert trees[0].metadata.source == "Local"

    @pytest.mark.unit
    def test_metadata_format_is_jsonl(self):
        """Format metadata is always 'jsonl'."""
        data = [{"role": "user", "content": "hi"}]
        trees = self.importer.import_data(data)
        assert trees[0].metadata.format == "jsonl"

    @pytest.mark.unit
    def test_import_index_in_custom_data(self):
        """import_index in custom_data reflects the conversation's position."""
        data = (
            '{"role": "user", "content": "First"}\n'
            '{"role": "assistant", "content": "R1"}\n'
            '{"conversation_break": true}\n'
            '{"role": "user", "content": "Second"}\n'
            '{"role": "assistant", "content": "R2"}'
        )
        trees = self.importer.import_data(data)
        assert len(trees) == 2
        assert trees[0].metadata.custom_data["import_index"] == 0
        assert trees[1].metadata.custom_data["import_index"] == 1

    @pytest.mark.unit
    def test_message_count_in_custom_data(self):
        """message_count in custom_data reflects the number of messages."""
        data = [
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "A"},
            {"role": "user", "content": "Follow-up"},
        ]
        trees = self.importer.import_data(data)
        assert trees[0].metadata.custom_data["message_count"] == 3

    @pytest.mark.unit
    def test_messages_linked_as_linear_chain(self):
        """Messages are added as a linear chain (each parent_id is the previous)."""
        data = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        trees = self.importer.import_data(data)
        tree = trees[0]
        path = tree.get_longest_path()
        assert len(path) == 3
        # First message has no parent
        assert path[0].parent_id is None
        # Second message's parent is first
        assert path[1].parent_id == path[0].id
        # Third message's parent is second
        assert path[2].parent_id == path[1].id

    @pytest.mark.unit
    def test_message_extra_fields_in_metadata(self):
        """Extra fields on individual messages are stored in message metadata."""
        data = [{"role": "user", "content": "hi", "weight": 1.0, "label": "good"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.metadata.get("weight") == 1.0
        assert msg.metadata.get("label") == "good"
        # Standard fields should NOT be in metadata
        assert "role" not in msg.metadata
        assert "content" not in msg.metadata


# ---------------------------------------------------------------------------
# TestJSONLTimestampParsing
# ---------------------------------------------------------------------------
class TestJSONLTimestampParsing:
    """Tests for JSONLImporter._parse_timestamp()"""

    def setup_method(self):
        self.importer = JSONLImporter()

    @pytest.mark.unit
    def test_parse_unix_int_timestamp(self):
        """Integer Unix timestamp is parsed correctly."""
        result = self.importer._parse_timestamp(1700000000)
        assert result == datetime.fromtimestamp(1700000000)

    @pytest.mark.unit
    def test_parse_unix_float_timestamp(self):
        """Float Unix timestamp is parsed correctly."""
        result = self.importer._parse_timestamp(1700000000.123)
        assert result == datetime.fromtimestamp(1700000000.123)

    @pytest.mark.unit
    def test_parse_iso_string_timestamp(self):
        """ISO-format string timestamp is parsed correctly."""
        result = self.importer._parse_timestamp("2024-06-15T10:30:00")
        assert result == datetime(2024, 6, 15, 10, 30, 0)

    @pytest.mark.unit
    def test_parse_invalid_string_returns_none(self):
        """Non-ISO string returns None."""
        result = self.importer._parse_timestamp("not-a-date")
        assert result is None

    @pytest.mark.unit
    def test_parse_none_returns_none(self):
        """None input returns None."""
        result = self.importer._parse_timestamp(None)
        assert result is None

    @pytest.mark.unit
    def test_parse_overflow_int_returns_none(self):
        """Extremely large int that overflows returns None."""
        result = self.importer._parse_timestamp(99999999999999)
        assert result is None


# ---------------------------------------------------------------------------
# TestJSONLEdgeCases
# ---------------------------------------------------------------------------
class TestJSONLEdgeCases:
    """Various edge-case scenarios."""

    def setup_method(self):
        self.importer = JSONLImporter()

    @pytest.mark.unit
    def test_unicode_content(self):
        """Unicode content is preserved through import."""
        data = [
            {"role": "user", "content": "Bonjour! Comment ca va? \u2603 \U0001f600"},
            {"role": "assistant", "content": "\u4f60\u597d\u4e16\u754c"},
        ]
        trees = self.importer.import_data(data)
        messages = trees[0].get_longest_path()
        assert "\u2603" in messages[0].content.text
        assert "\U0001f600" in messages[0].content.text
        assert "\u4f60\u597d\u4e16\u754c" in messages[1].content.text

    @pytest.mark.unit
    def test_large_number_of_messages(self):
        """Importing many messages in a single conversation works."""
        msg_count = 200
        data = []
        for i in range(msg_count):
            role = "user" if i % 2 == 0 else "assistant"
            data.append({"role": role, "content": f"Message {i}"})
        trees = self.importer.import_data(data)
        assert len(trees) == 1
        path = trees[0].get_longest_path()
        assert len(path) == msg_count
        assert trees[0].metadata.custom_data["message_count"] == msg_count

    @pytest.mark.unit
    def test_empty_content_string(self):
        """Empty content string is still imported (not skipped)."""
        data = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "I see you sent nothing."},
        ]
        trees = self.importer.import_data(data)
        messages = trees[0].get_longest_path()
        assert len(messages) == 2
        assert messages[0].content.text == ""

    @pytest.mark.unit
    def test_only_system_messages(self):
        """Conversation with only system messages falls back to 'Untitled'."""
        data = [
            {"role": "system", "content": "System prompt 1"},
            {"role": "system", "content": "System prompt 2"},
        ]
        trees = self.importer.import_data(data)
        assert len(trees) == 1
        tree = trees[0]
        # No user/human message means title stays Untitled
        assert tree.title == "Untitled Conversation"
        messages = tree.get_longest_path()
        assert len(messages) == 2
        assert messages[0].role == MessageRole.SYSTEM

    @pytest.mark.unit
    def test_mixed_formats_in_single_file(self):
        """A file mixing role+content lines and instruction/response lines."""
        line1 = '{"role": "user", "content": "Direct msg"}'
        line2 = '{"role": "assistant", "content": "Direct reply"}'
        line3 = ""  # blank line separator
        line4 = json.dumps({"instruction": "Do X", "response": "Done X"})
        data = f"{line1}\n{line2}\n{line3}\n{line4}"
        trees = self.importer.import_data(data)
        # First conv from role+content, second from instruction/response
        assert len(trees) == 2
        path1 = trees[0].get_longest_path()
        assert len(path1) == 2
        assert path1[0].content.text == "Direct msg"
        path2 = trees[1].get_longest_path()
        assert len(path2) == 2
        assert path2[0].content.text == "Do X"

    @pytest.mark.unit
    def test_conversations_key_alternative_naming(self):
        """Dict with 'conversations' key works like 'messages' key."""
        data = {
            "conversations": [
                {"role": "user", "content": "Hello via conversations key"},
                {"role": "assistant", "content": "Hi!"},
            ]
        }
        trees = self.importer.import_data(data)
        assert len(trees) == 1
        messages = trees[0].get_longest_path()
        assert len(messages) == 2
        assert messages[0].content.text == "Hello via conversations key"

    @pytest.mark.unit
    def test_content_missing_defaults_to_empty(self):
        """Missing 'content' key in a message dict defaults to empty string."""
        data = [{"role": "user"}]
        trees = self.importer.import_data(data)
        msg = trees[0].get_longest_path()[0]
        assert msg.content.text == ""

    @pytest.mark.unit
    def test_role_missing_skipped_by_extract(self):
        """Missing 'role' key means the dict doesn't match message format in _extract_messages."""
        # _extract_messages requires 'role' + 'content' to recognize a message
        data = [{"content": "No explicit role"}]
        trees = self.importer.import_data(data)
        # Without 'role', extract_messages doesn't recognize it as a message
        assert len(trees) == 0

    @pytest.mark.unit
    def test_multiple_conversations_from_list_of_objects(self):
        """List of conversation objects with 'messages' creates multiple trees."""
        data = [
            {
                "messages": [
                    {"role": "user", "content": "Q1"},
                    {"role": "assistant", "content": "A1"},
                ],
                "id": "conv-1",
            },
            {
                "messages": [
                    {"role": "user", "content": "Q2"},
                    {"role": "assistant", "content": "A2"},
                ],
                "id": "conv-2",
            },
        ]
        trees = self.importer.import_data(data)
        assert len(trees) == 2
        assert trees[0].id == "conv-1"
        assert trees[1].id == "conv-2"
        assert trees[0].get_longest_path()[0].content.text == "Q1"
        assert trees[1].get_longest_path()[0].content.text == "Q2"

    @pytest.mark.unit
    def test_title_from_human_role_message(self):
        """Title generation also checks for 'human' role (not just 'user')."""
        data = [
            {"role": "human", "content": "My question about Python"},
            {"role": "ai", "content": "Python is great!"},
        ]
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert tree.title == "My question about Python"

    @pytest.mark.unit
    def test_whitespace_only_lines_treated_as_blank(self):
        """Lines with only whitespace act as blank line separators."""
        data = (
            '{"role": "user", "content": "A"}\n'
            "   \n"
            '{"role": "user", "content": "B"}'
        )
        # The line "   " has strip() == "", so `not line.strip()` is True
        # This means it acts as a blank line separator
        convs = self.importer._extract_messages(data)
        assert len(convs) == 2

    @pytest.mark.unit
    def test_newline_in_content(self):
        """Newlines within JSON string content are preserved."""
        msg = {"role": "user", "content": "Line 1\nLine 2\nLine 3"}
        data = json.dumps(msg)
        trees = self.importer.import_data(data)
        text = trees[0].get_longest_path()[0].content.text
        assert "Line 1\nLine 2\nLine 3" == text

    @pytest.mark.unit
    def test_model_tag_lowercased_and_hyphenated(self):
        """The model-based tag is lowercased with spaces replaced by hyphens."""
        data = {"messages": [{"role": "user", "content": "hi"}], "model": "My Model"}
        trees = self.importer.import_data(data)
        tree = trees[0]
        assert "my-model" in tree.metadata.tags
