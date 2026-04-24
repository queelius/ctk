"""Unit tests for the two taggers that ship with ctk.

Earlier versions shipped OllamaTagger / AnthropicTagger / OpenRouterTagger
/ LocalTagger; those were removed in 2.10.0 because they all spoke the
OpenAI chat-completions protocol. OpenAITagger (wrapping the openai SDK)
now covers every remote endpoint.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ctk.core.models import (ConversationTree, Message, MessageContent,
                             MessageRole)
from ctk.taggers.openai_tagger import OpenAITagger
from ctk.taggers.tfidf_tagger import TFIDFTagger


class TestTFIDFTagger:
    """Test TF-IDF based tagger"""

    @pytest.mark.unit
    def test_tokenize(self):
        """Test text tokenization"""
        tagger = TFIDFTagger()

        text = "Hello World! This is a TEST of tokenization."
        tokens = tagger.tokenize(text)

        # Should be lowercase and filtered
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "tokenization" in tokens

        # Stop words should be removed
        assert "this" not in tokens
        assert "is" not in tokens
        assert "a" not in tokens

        # Short words should be removed
        assert "of" not in tokens

    @pytest.mark.unit
    def test_domain_tag_extraction(self):
        """Test domain-specific tag extraction"""
        tagger = TFIDFTagger()

        text = "I'm learning Python and using pandas for data analysis with machine learning"
        tags = tagger.extract_domain_tags(text)

        assert "python" in tags
        assert "data-science" in tags
        assert "machine-learning" in tags

    @pytest.mark.unit
    def test_tag_conversation(self, sample_conversation):
        """Test tagging a conversation"""
        tagger = TFIDFTagger()

        # Add some technical content
        msg = Message(
            id="msg_tech",
            role=MessageRole.USER,
            content=MessageContent(
                text="Can you help me with Python programming and machine learning?"
            ),
            parent_id="msg_004",
        )
        sample_conversation.add_message(msg)

        tags = tagger.tag_conversation(sample_conversation, num_tags=5)

        assert isinstance(tags, list)
        assert len(tags) <= 5
        # Should identify Python from content
        assert any("python" in tag.lower() for tag in tags)

    @pytest.mark.unit
    def test_key_phrase_extraction(self):
        """Test extracting key phrases"""
        tagger = TFIDFTagger()

        text = """
        I'm working with React Native and Python 3.9.
        The API uses GraphQL for queries.
        We're implementing OAuth 2.0 for authentication.
        """

        phrases = tagger.extract_key_phrases(text, [])

        # Should extract version numbers
        assert any("python-3.9" in phrase for phrase in phrases)

        # Should extract acronyms
        assert any("api" in phrase.lower() for phrase in phrases)

    @pytest.mark.unit
    def test_corpus_statistics_update(self):
        """Test updating corpus statistics for better TF-IDF"""
        tagger = TFIDFTagger()

        # Create sample conversations
        conversations = []
        for i in range(3):
            conv = ConversationTree(id=f"conv_{i}")
            msg = Message(
                id=f"msg_{i}",
                role=MessageRole.USER,
                content=MessageContent(text=f"Python programming {i}"),
            )
            conv.add_message(msg)
            conversations.append(conv)

        # Update statistics
        tagger.update_corpus_statistics(conversations)

        assert tagger.total_documents == 3
        assert "python" in tagger.document_frequencies
        assert tagger.document_frequencies["python"] == 3

    @pytest.mark.unit
    def test_analyze_conversation(self, sample_conversation):
        """Test detailed conversation analysis"""
        tagger = TFIDFTagger()

        analysis = tagger.analyze_conversation(sample_conversation)

        assert "word_count" in analysis
        assert "unique_words" in analysis
        assert "message_count" in analysis
        assert "suggested_tags" in analysis
        assert "has_code" in analysis
        assert "questions" in analysis

        assert analysis["message_count"] == 4
        assert isinstance(analysis["suggested_tags"], list)


def _mock_chat_response(content: str) -> MagicMock:
    """Build a minimal stand-in for an openai ChatCompletion response.

    We only touch ``.choices[0].message.content`` in the tagger, so the
    stand-in can stop at that attribute chain.
    """
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _mock_models_response(ids: list) -> SimpleNamespace:
    return SimpleNamespace(
        data=[SimpleNamespace(id=i, created=0, owned_by="test") for i in ids]
    )


def _patch_openai_client(mock_client: MagicMock):
    """Patch the openai.OpenAI constructor globally.

    The tagger imports ``from openai import OpenAI`` inside a method,
    so patching the source module catches every callsite regardless of
    import timing.
    """
    return patch("openai.OpenAI", return_value=mock_client)


class TestOpenAITagger:
    """Tests for the single LLM tagger now that taggers use the openai SDK."""

    @pytest.mark.unit
    def test_call_api_success(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_chat_response(
            '["python", "api", "testing"]'
        )

        with _patch_openai_client(mock_client):
            tagger = OpenAITagger(api_key="test_key")
            response = tagger.call_api("Test prompt")

        assert response == '["python", "api", "testing"]'
        # Sanity: we actually talked to the patched SDK.
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.unit
    def test_call_api_error_returns_none(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")

        with _patch_openai_client(mock_client):
            tagger = OpenAITagger(api_key="test_key")
            response = tagger.call_api("Test prompt")

        assert response is None

    @pytest.mark.unit
    def test_call_api_unexpected_shape_returns_none(self):
        # A response with no choices trips the AttributeError/IndexError guard.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(choices=[])

        with _patch_openai_client(mock_client):
            tagger = OpenAITagger(api_key="test_key")
            response = tagger.call_api("Test prompt")

        assert response is None

    @pytest.mark.unit
    def test_list_models(self):
        mock_client = MagicMock()
        mock_client.models.list.return_value = _mock_models_response(
            ["gpt-3.5-turbo", "gpt-4"]
        )

        with _patch_openai_client(mock_client):
            tagger = OpenAITagger(api_key="test_key")
            models = tagger.list_models()

        assert models == ["gpt-3.5-turbo", "gpt-4"]

    @pytest.mark.unit
    def test_tag_conversation(self, sample_conversation):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_chat_response(
            '["conversation", "greeting", "chat"]'
        )

        with _patch_openai_client(mock_client):
            tagger = OpenAITagger(api_key="test_key")
            tags = tagger.tag_conversation(sample_conversation)

        assert "conversation" in tags
        assert "greeting" in tags
        assert "chat" in tags


class TestBaseLLMTagger:
    """Test base LLM tagger functionality"""

    @pytest.mark.unit
    def test_extract_text(self, branching_conversation):
        """Test text extraction from conversation"""
        from ctk.taggers.base import BaseLLMTagger

        # Create a mock tagger
        class MockTagger(BaseLLMTagger):
            def get_provider_name(self):
                return "mock"

            def call_api(self, prompt):
                return '["test"]'

        tagger = MockTagger()
        text = tagger.extract_text(branching_conversation)

        assert "What's 2+2?" in text
        assert "equals 4" in text or "answer is 4" in text
        assert "user:" in text
        assert "assistant:" in text

    @pytest.mark.unit
    def test_create_tagging_prompt(self):
        """Test prompt creation for tagging"""
        from ctk.taggers.base import BaseLLMTagger

        class MockTagger(BaseLLMTagger):
            def get_provider_name(self):
                return "mock"

            def call_api(self, prompt):
                return ""

        tagger = MockTagger()
        prompt = tagger.create_tagging_prompt("Sample conversation text")

        assert "Sample conversation text" in prompt
        assert "tags" in prompt.lower()
        assert "JSON" in prompt

    @pytest.mark.unit
    def test_parse_categorization_response(self):
        """Test parsing categorization response"""
        from ctk.taggers.base import BaseLLMTagger

        class MockTagger(BaseLLMTagger):
            def get_provider_name(self):
                return "mock"

            def call_api(self, prompt):
                return ""

        tagger = MockTagger()

        response = """
        {
            "primary_topic": "programming",
            "tags": ["python", "api"],
            "complexity": "intermediate",
            "type": "tutorial"
        }
        """

        result = tagger.parse_categorization_response(response)

        assert result["primary_topic"] == "programming"
        assert "python" in result["tags"]
        assert result["complexity"] == "intermediate"
        assert result["type"] == "tutorial"
