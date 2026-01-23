"""
Unit tests for taggers
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
import responses

from ctk.core.models import (ConversationTree, Message, MessageContent,
                             MessageRole)
from ctk.integrations.taggers.ollama_tagger import OllamaTagger
from ctk.integrations.taggers.openai_tagger import OpenAITagger
from ctk.integrations.taggers.tfidf_tagger import TFIDFTagger


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


class TestOllamaTagger:
    """Test Ollama-based tagger"""

    @pytest.mark.unit
    @responses.activate
    def test_call_api_success(self):
        """Test successful API call to Ollama"""
        responses.add(
            responses.POST,
            "http://localhost:11434/api/generate",
            json={"response": '["python", "programming", "api"]'},
            status=200,
        )

        tagger = OllamaTagger(base_url="http://localhost:11434")
        response = tagger.call_api("Test prompt")

        assert response == '["python", "programming", "api"]'

    @pytest.mark.unit
    @responses.activate
    def test_call_api_failure(self):
        """Test handling API failure"""
        responses.add(responses.POST, "http://localhost:11434/api/generate", status=500)

        tagger = OllamaTagger(base_url="http://localhost:11434")
        response = tagger.call_api("Test prompt")

        assert response is None

    @pytest.mark.unit
    @responses.activate
    def test_check_connection(self):
        """Test checking Ollama connection"""
        responses.add(
            responses.GET,
            "http://localhost:11434/api/tags",
            json={"models": []},
            status=200,
        )

        tagger = OllamaTagger(base_url="http://localhost:11434")
        is_connected = tagger.check_connection()

        assert is_connected is True

    @pytest.mark.unit
    @responses.activate
    def test_list_models(self):
        """Test listing available models"""
        responses.add(
            responses.GET,
            "http://localhost:11434/api/tags",
            json={"models": [{"name": "llama2"}, {"name": "codellama"}]},
            status=200,
        )

        tagger = OllamaTagger(base_url="http://localhost:11434")
        models = tagger.list_models()

        assert "llama2" in models
        assert "codellama" in models

    @pytest.mark.unit
    def test_parse_tags_response(self):
        """Test parsing LLM response for tags"""
        tagger = OllamaTagger()

        # Test JSON array response
        response = '["Python", "Machine Learning", "API"]'
        tags = tagger.parse_tags_response(response)

        assert "python" in tags
        assert "machine-learning" in tags
        assert "api" in tags

        # Test comma-separated response
        response = "python, machine learning, data science"
        tags = tagger.parse_tags_response(response)

        assert "python" in tags
        assert "machine-learning" in tags
        assert "data-science" in tags

        # Test malformed response
        response = "Some random text without proper format"
        tags = tagger.parse_tags_response(response)
        assert isinstance(tags, list)


class TestOpenAITagger:
    """Test OpenAI-based tagger"""

    @pytest.mark.unit
    @responses.activate
    def test_call_api_success(self):
        """Test successful API call to OpenAI"""
        responses.add(
            responses.POST,
            "https://api.openai.com/v1/chat/completions",
            json={
                "choices": [{"message": {"content": '["python", "api", "testing"]'}}]
            },
            status=200,
        )

        tagger = OpenAITagger(api_key="test_key")
        response = tagger.call_api("Test prompt")

        assert response == '["python", "api", "testing"]'

    @pytest.mark.unit
    def test_call_api_no_key(self):
        """Test API call without API key"""
        tagger = OpenAITagger(api_key=None)
        response = tagger.call_api("Test prompt")

        assert response is None

    @pytest.mark.unit
    @responses.activate
    def test_call_api_error(self):
        """Test handling API error response"""
        responses.add(
            responses.POST,
            "https://api.openai.com/v1/chat/completions",
            json={"error": {"message": "Invalid API key"}},
            status=401,
        )

        tagger = OpenAITagger(api_key="invalid_key")
        response = tagger.call_api("Test prompt")

        assert response is None

    @pytest.mark.unit
    @responses.activate
    def test_list_models(self):
        """Test listing available models"""
        responses.add(
            responses.GET,
            "https://api.openai.com/v1/models",
            json={"data": [{"id": "gpt-3.5-turbo"}, {"id": "gpt-4"}]},
            status=200,
        )

        tagger = OpenAITagger(api_key="test_key")
        models = tagger.list_models()

        assert "gpt-3.5-turbo" in models
        assert "gpt-4" in models

    @pytest.mark.unit
    @responses.activate
    def test_tag_conversation(self, sample_conversation):
        """Test tagging a conversation"""
        responses.add(
            responses.POST,
            "https://api.openai.com/v1/chat/completions",
            json={
                "choices": [
                    {"message": {"content": '["conversation", "greeting", "chat"]'}}
                ]
            },
            status=200,
        )

        tagger = OpenAITagger(api_key="test_key")
        tags = tagger.tag_conversation(sample_conversation)

        assert isinstance(tags, list)
        assert "conversation" in tags
        assert "greeting" in tags
        assert "chat" in tags


class TestBaseLLMTagger:
    """Test base LLM tagger functionality"""

    @pytest.mark.unit
    def test_extract_text(self, branching_conversation):
        """Test text extraction from conversation"""
        from ctk.integrations.taggers.base import BaseLLMTagger

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
        from ctk.integrations.taggers.base import BaseLLMTagger

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
        from ctk.integrations.taggers.base import BaseLLMTagger

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
