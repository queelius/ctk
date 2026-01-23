"""
Tests for export format preservation of tool calls and multimodal content.
"""

import json
import pytest
from datetime import datetime

from ctk.core.models import (
    ConversationTree,
    Message,
    MessageRole,
    MessageContent,
    ToolCall,
    MediaContent,
    ContentType,
)
from ctk.integrations.exporters.jsonl import JSONLExporter
from ctk.integrations.exporters.json import JSONExporter


class TestJSONLToolCallPreservation:
    """Test that JSONL exporter preserves tool calls."""

    @pytest.fixture
    def conversation_with_tool_calls(self):
        """Create a conversation with tool calls."""
        conv = ConversationTree(id='test-tools', title='Tool Call Test')

        # User message
        user_msg = Message(
            id='m1',
            role=MessageRole.USER,
            content=MessageContent(text='Search for Python tutorials'),
            timestamp=datetime.now(),
        )
        conv.add_message(user_msg)

        # Assistant message with tool call
        assistant_content = MessageContent(text='Let me search for that.')
        tool_call = ToolCall(
            id='tc1',
            name='search_web',
            arguments={'query': 'Python tutorials', 'limit': 10},
            status='completed',
            result={'results': [{'title': 'Python Tutorial', 'url': 'https://example.com'}]}
        )
        assistant_content.tool_calls.append(tool_call)

        assistant_msg = Message(
            id='m2',
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            parent_id='m1',
            timestamp=datetime.now(),
        )
        conv.add_message(assistant_msg)

        return conv

    def test_jsonl_preserves_tool_calls(self, conversation_with_tool_calls):
        """Test that tool calls are preserved in JSONL export."""
        exporter = JSONLExporter()
        output = exporter.export_data([conversation_with_tool_calls])

        parsed = json.loads(output)
        messages = parsed['messages']

        # Find assistant message with tool calls
        assistant_msg = messages[1]
        assert isinstance(assistant_msg['content'], list), "Content should be a list for structured messages"

        # Find tool call in content
        tool_calls = [p for p in assistant_msg['content'] if p.get('type') == 'tool_call']
        assert len(tool_calls) == 1, "Should have one tool call"

        tool_call = tool_calls[0]
        assert tool_call['name'] == 'search_web'
        assert tool_call['arguments'] == {'query': 'Python tutorials', 'limit': 10}
        assert tool_call['status'] == 'completed'
        assert 'result' in tool_call

    def test_jsonl_preserves_tool_call_id(self, conversation_with_tool_calls):
        """Test that tool call IDs are preserved."""
        exporter = JSONLExporter()
        output = exporter.export_data([conversation_with_tool_calls])

        parsed = json.loads(output)
        messages = parsed['messages']

        assistant_msg = messages[1]
        tool_calls = [p for p in assistant_msg['content'] if p.get('type') == 'tool_call']

        assert tool_calls[0]['id'] == 'tc1'

    def test_jsonl_preserves_multiple_tool_calls(self):
        """Test that multiple tool calls in one message are preserved."""
        conv = ConversationTree(id='multi-tools', title='Multi Tool Test')

        user_msg = Message(
            id='m1',
            role=MessageRole.USER,
            content=MessageContent(text='Query'),
        )
        conv.add_message(user_msg)

        assistant_content = MessageContent(text='Processing...')
        for i in range(3):
            tool = ToolCall(
                id=f'tc{i}',
                name=f'tool_{i}',
                arguments={'index': i},
                status='completed',
            )
            assistant_content.tool_calls.append(tool)

        assistant_msg = Message(
            id='m2',
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            parent_id='m1',
        )
        conv.add_message(assistant_msg)

        exporter = JSONLExporter()
        output = exporter.export_data([conv])

        parsed = json.loads(output)
        assistant_msg_data = parsed['messages'][1]
        tool_calls = [p for p in assistant_msg_data['content'] if p.get('type') == 'tool_call']

        assert len(tool_calls) == 3
        assert [tc['name'] for tc in tool_calls] == ['tool_0', 'tool_1', 'tool_2']


class TestJSONLMultimodalPreservation:
    """Test that JSONL exporter preserves multimodal content."""

    @pytest.fixture
    def conversation_with_images(self):
        """Create a conversation with images."""
        conv = ConversationTree(id='test-images', title='Image Test')

        # User message with image
        user_content = MessageContent(text='What is in this image?')
        user_content.add_image(
            data='base64encodeddata',
            mime_type='image/png',
            caption='Test image',
        )

        user_msg = Message(
            id='m1',
            role=MessageRole.USER,
            content=user_content,
            timestamp=datetime.now(),
        )
        conv.add_message(user_msg)

        return conv

    def test_jsonl_preserves_images(self, conversation_with_images):
        """Test that images are preserved in JSONL export."""
        exporter = JSONLExporter()
        output = exporter.export_data([conversation_with_images])

        parsed = json.loads(output)
        messages = parsed['messages']

        user_msg = messages[0]
        assert isinstance(user_msg['content'], list), "Content should be a list for multimodal"

        # Find image in content
        images = [p for p in user_msg['content'] if p.get('type') == 'image']
        assert len(images) == 1, "Should have one image"

        image = images[0]
        assert image['data'] == 'base64encodeddata'
        assert image['mime_type'] == 'image/png'
        assert image['caption'] == 'Test image'


class TestJSONAnthropicFormat:
    """Test JSON exporter Anthropic format preserves tool calls."""

    def test_anthropic_format_preserves_tool_use(self):
        """Test that tool calls are exported as tool_use blocks."""
        conv = ConversationTree(id='test-anthropic', title='Anthropic Test')

        user_msg = Message(
            id='m1',
            role=MessageRole.USER,
            content=MessageContent(text='Query'),
        )
        conv.add_message(user_msg)

        assistant_content = MessageContent(text='Response')
        tool = ToolCall(
            id='tc1',
            name='search',
            arguments={'q': 'test'},
        )
        assistant_content.tool_calls.append(tool)

        assistant_msg = Message(
            id='m2',
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            parent_id='m1',
        )
        conv.add_message(assistant_msg)

        exporter = JSONExporter()
        output = exporter.export_conversations([conv], format_style='anthropic')

        data = json.loads(output)
        messages = data['conversations'][0]['messages']

        # Find assistant message
        assistant_msg_data = messages[1]
        assert isinstance(assistant_msg_data['content'], list)

        # Find tool_use block
        tool_use_blocks = [b for b in assistant_msg_data['content'] if b.get('type') == 'tool_use']
        assert len(tool_use_blocks) == 1

        block = tool_use_blocks[0]
        assert block['name'] == 'search'
        assert block['input'] == {'q': 'test'}
        assert block['id'] == 'tc1'

    def test_anthropic_format_preserves_images(self):
        """Test that images are exported with Anthropic source format."""
        conv = ConversationTree(id='test-anthropic-img', title='Anthropic Image Test')

        user_content = MessageContent(text='Describe this image')
        user_content.add_image(
            data='imagedata123',
            mime_type='image/jpeg',
        )

        user_msg = Message(
            id='m1',
            role=MessageRole.USER,
            content=user_content,
        )
        conv.add_message(user_msg)

        exporter = JSONExporter()
        output = exporter.export_conversations([conv], format_style='anthropic')

        data = json.loads(output)
        messages = data['conversations'][0]['messages']

        user_msg_data = messages[0]
        assert isinstance(user_msg_data['content'], list)

        # Find image block
        image_blocks = [b for b in user_msg_data['content'] if b.get('type') == 'image']
        assert len(image_blocks) == 1

        block = image_blocks[0]
        assert block['source']['type'] == 'base64'
        assert block['source']['data'] == 'imagedata123'
        assert block['source']['media_type'] == 'image/jpeg'


class TestJSONOpenAIFormat:
    """Test JSON exporter OpenAI format preserves tool calls."""

    def test_openai_format_preserves_tool_calls(self):
        """Test that tool calls are exported in OpenAI format."""
        conv = ConversationTree(id='test-openai', title='OpenAI Test')

        user_msg = Message(
            id='m1',
            role=MessageRole.USER,
            content=MessageContent(text='Query'),
        )
        conv.add_message(user_msg)

        assistant_content = MessageContent(text='Response')
        tool = ToolCall(
            id='call_123',
            name='get_weather',
            arguments={'location': 'NYC'},
        )
        assistant_content.tool_calls.append(tool)

        assistant_msg = Message(
            id='m2',
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            parent_id='m1',
        )
        conv.add_message(assistant_msg)

        exporter = JSONExporter()
        output = exporter.export_conversations([conv], format_style='openai')

        data = json.loads(output)
        messages = data[0]['messages']

        # Find assistant message
        assistant_msg_data = messages[1]

        # OpenAI format has tool_calls as separate field
        assert 'tool_calls' in assistant_msg_data
        assert len(assistant_msg_data['tool_calls']) == 1

        tool_call = assistant_msg_data['tool_calls'][0]
        assert tool_call['id'] == 'call_123'
        assert tool_call['function']['name'] == 'get_weather'


class TestExportRoundtrip:
    """Test that data survives export/import roundtrip."""

    def test_ctk_format_preserves_everything(self):
        """Test that CTK format preserves full tree structure and metadata."""
        conv = ConversationTree(id='test-ctk', title='CTK Roundtrip Test')

        # Create branching conversation
        root = Message(
            id='m1',
            role=MessageRole.USER,
            content=MessageContent(text='Question'),
        )
        conv.add_message(root)

        # Two branches
        for i in range(2):
            assistant_content = MessageContent(text=f'Response {i}')
            tool = ToolCall(
                id=f'tc{i}',
                name=f'tool_{i}',
                arguments={'branch': i},
            )
            assistant_content.tool_calls.append(tool)

            msg = Message(
                id=f'm2_{i}',
                role=MessageRole.ASSISTANT,
                content=assistant_content,
                parent_id='m1',
            )
            conv.add_message(msg)

        exporter = JSONExporter()
        output = exporter.export_conversations([conv], format_style='ctk')

        data = json.loads(output)
        conv_data = data['conversations'][0]

        # Verify tree structure
        assert len(conv_data['messages']) == 3
        assert len(conv_data['root_message_ids']) == 1

        # Verify tool calls in messages
        for msg_id, msg in conv_data['messages'].items():
            if msg['role'] == 'assistant':
                assert 'tool_calls' in msg['content']
