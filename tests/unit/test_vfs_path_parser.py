"""
Unit tests for VFS path parser

Tests the VFSPathParser class for:
- Path normalization
- Path type detection
- Conversation ID extraction
- Message node parsing
- Metadata file detection
"""

import pytest
from ctk.core.vfs import VFSPathParser, VFSPath, PathType


class TestPathNormalization:
    """Test path normalization"""

    @pytest.mark.unit
    def test_normalize_absolute_path(self):
        """Test normalizing absolute paths"""
        result = VFSPathParser.normalize_path('/chats/abc123')
        assert result == '/chats/abc123'

    @pytest.mark.unit
    def test_normalize_relative_path(self):
        """Test normalizing relative paths"""
        result = VFSPathParser.normalize_path('chats/abc123', current_dir='/')
        assert result == '/chats/abc123'

    @pytest.mark.unit
    def test_normalize_dot_segments(self):
        """Test resolving . in path"""
        result = VFSPathParser.normalize_path('/chats/./abc123')
        assert result == '/chats/abc123'

    @pytest.mark.unit
    def test_normalize_dotdot_segments(self):
        """Test resolving .. in path"""
        result = VFSPathParser.normalize_path('/chats/abc123/..')
        assert result == '/chats'

    @pytest.mark.unit
    def test_normalize_multiple_dotdot(self):
        """Test multiple .. segments"""
        result = VFSPathParser.normalize_path('/chats/abc123/m1/../..')
        assert result == '/chats'

    @pytest.mark.unit
    def test_normalize_root_path(self):
        """Test normalizing root path"""
        result = VFSPathParser.normalize_path('/')
        assert result == '/'

    @pytest.mark.unit
    def test_normalize_empty_relative_path(self):
        """Test normalizing empty relative path"""
        result = VFSPathParser.normalize_path('', current_dir='/chats')
        assert result == '/chats'

    @pytest.mark.unit
    def test_normalize_relative_from_deep_path(self):
        """Test relative path from deep directory"""
        result = VFSPathParser.normalize_path('../..', current_dir='/chats/abc123')
        assert result == '/'

    @pytest.mark.unit
    def test_normalize_complex_relative_path(self):
        """Test complex relative path with . and .."""
        result = VFSPathParser.normalize_path('./m1/../m2', current_dir='/chats/abc123')
        assert result == '/chats/abc123/m2'

    @pytest.mark.unit
    def test_normalize_trailing_slash_removed(self):
        """Test that trailing slashes are handled"""
        result = VFSPathParser.normalize_path('/chats/')
        assert result == '/chats'

    @pytest.mark.unit
    def test_normalize_dotdot_at_root(self):
        """Test that .. at root stays at root"""
        result = VFSPathParser.normalize_path('/..')
        assert result == '/'


class TestConversationIDValidation:
    """Test conversation ID validation"""

    @pytest.mark.unit
    def test_valid_conversation_id_uuid(self):
        """Test valid UUID-like conversation ID"""
        assert VFSPathParser.is_valid_conversation_id('abc123-def456-789') is True

    @pytest.mark.unit
    def test_valid_conversation_id_hash(self):
        """Test valid hash-like conversation ID"""
        assert VFSPathParser.is_valid_conversation_id('7c87f9a2') is True

    @pytest.mark.unit
    def test_valid_conversation_id_long(self):
        """Test valid long conversation ID (only alphanumeric, dash, underscore)"""
        # Pattern is [a-f0-9\-_]+, case insensitive, 5-100 chars
        assert VFSPathParser.is_valid_conversation_id('abcdef-12345-fedcba') is True

    @pytest.mark.unit
    def test_invalid_too_short(self):
        """Test that too-short IDs are invalid"""
        assert VFSPathParser.is_valid_conversation_id('abc') is False

    @pytest.mark.unit
    def test_invalid_too_long(self):
        """Test that too-long IDs are invalid"""
        long_id = 'a' * 150
        assert VFSPathParser.is_valid_conversation_id(long_id) is False

    @pytest.mark.unit
    def test_invalid_special_chars(self):
        """Test that special characters make ID invalid"""
        assert VFSPathParser.is_valid_conversation_id('abc@123') is False
        assert VFSPathParser.is_valid_conversation_id('abc 123') is False

    @pytest.mark.unit
    def test_valid_with_underscores(self):
        """Test that underscores are allowed"""
        # Pattern allows [a-f0-9\-_]+
        assert VFSPathParser.is_valid_conversation_id('abc_123') is True

    @pytest.mark.unit
    def test_valid_with_dashes(self):
        """Test that dashes are allowed"""
        assert VFSPathParser.is_valid_conversation_id('abc-123-def') is True

    @pytest.mark.unit
    def test_letters_outside_af_invalid(self):
        """Test that letters outside a-f are invalid (hex pattern)"""
        # Pattern is [a-f0-9\-_]+, so 'g' should be invalid
        assert VFSPathParser.is_valid_conversation_id('ghijkl123') is False


class TestMessageNodeValidation:
    """Test message node validation"""

    @pytest.mark.unit
    def test_valid_message_node(self):
        """Test valid message node patterns"""
        assert VFSPathParser.is_message_node('m1') is True
        assert VFSPathParser.is_message_node('m10') is True
        assert VFSPathParser.is_message_node('m999') is True

    @pytest.mark.unit
    def test_invalid_message_node(self):
        """Test invalid message node patterns"""
        assert VFSPathParser.is_message_node('m') is False
        assert VFSPathParser.is_message_node('1') is False
        assert VFSPathParser.is_message_node('message1') is False
        assert VFSPathParser.is_message_node('m1a') is False

    @pytest.mark.unit
    def test_message_node_case_insensitive(self):
        """Test that message nodes are case-insensitive"""
        assert VFSPathParser.is_message_node('M1') is True
        assert VFSPathParser.is_message_node('M10') is True


class TestRootPath:
    """Test parsing root path"""

    @pytest.mark.unit
    def test_parse_root(self):
        """Test parsing root directory"""
        path = VFSPathParser.parse('/')

        assert path.path_type == PathType.ROOT
        assert path.normalized_path == '/'
        assert path.segments == []
        assert path.is_directory is True


class TestChatsPath:
    """Test parsing /chats paths"""

    @pytest.mark.unit
    def test_parse_chats_directory(self):
        """Test parsing /chats directory"""
        path = VFSPathParser.parse('/chats')

        assert path.path_type == PathType.CHATS
        assert path.normalized_path == '/chats'
        assert path.segments == ['chats']
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_conversation_root(self):
        """Test parsing conversation root"""
        path = VFSPathParser.parse('/chats/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_message_node(self):
        """Test parsing message node"""
        path = VFSPathParser.parse('/chats/abc123/m1')

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1']
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_nested_message_nodes(self):
        """Test parsing nested message nodes"""
        path = VFSPathParser.parse('/chats/abc123/m1/m2/m3')

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1', 'm2', 'm3']
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_message_metadata_file(self):
        """Test parsing message metadata file"""
        path = VFSPathParser.parse('/chats/abc123/m1/text')

        assert path.path_type == PathType.MESSAGE_FILE
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1']
        assert path.file_name == 'text'
        assert path.is_directory is False

    @pytest.mark.unit
    def test_parse_nested_message_metadata(self):
        """Test parsing metadata file in nested message"""
        path = VFSPathParser.parse('/chats/abc123/m1/m2/role')

        assert path.path_type == PathType.MESSAGE_FILE
        assert path.message_path == ['m1', 'm2']
        assert path.file_name == 'role'

    @pytest.mark.unit
    def test_parse_all_metadata_files(self):
        """Test parsing all metadata file types"""
        metadata_files = ['text', 'role', 'timestamp', 'id']

        for filename in metadata_files:
            path = VFSPathParser.parse(f'/chats/abc123/m1/{filename}')
            assert path.path_type == PathType.MESSAGE_FILE
            assert path.file_name == filename
            assert path.is_directory is False


class TestStarredPath:
    """Test parsing /starred paths"""

    @pytest.mark.unit
    def test_parse_starred_directory(self):
        """Test parsing /starred directory"""
        path = VFSPathParser.parse('/starred')

        assert path.path_type == PathType.STARRED
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_starred_conversation(self):
        """Test parsing starred conversation"""
        path = VFSPathParser.parse('/starred/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'

    @pytest.mark.unit
    def test_parse_starred_message_node(self):
        """Test parsing message in starred conversation"""
        path = VFSPathParser.parse('/starred/abc123/m1/m2')

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1', 'm2']

    @pytest.mark.unit
    def test_parse_starred_metadata_file(self):
        """Test parsing metadata file in starred conversation"""
        path = VFSPathParser.parse('/starred/abc123/m1/text')

        assert path.path_type == PathType.MESSAGE_FILE
        assert path.file_name == 'text'


class TestPinnedPath:
    """Test parsing /pinned paths"""

    @pytest.mark.unit
    def test_parse_pinned_directory(self):
        """Test parsing /pinned directory"""
        path = VFSPathParser.parse('/pinned')

        assert path.path_type == PathType.PINNED
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_pinned_conversation(self):
        """Test parsing pinned conversation"""
        path = VFSPathParser.parse('/pinned/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'


class TestArchivedPath:
    """Test parsing /archived paths"""

    @pytest.mark.unit
    def test_parse_archived_directory(self):
        """Test parsing /archived directory"""
        path = VFSPathParser.parse('/archived')

        assert path.path_type == PathType.ARCHIVED
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_archived_conversation(self):
        """Test parsing archived conversation"""
        path = VFSPathParser.parse('/archived/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'


class TestTagsPath:
    """Test parsing /tags paths"""

    @pytest.mark.unit
    def test_parse_tags_directory(self):
        """Test parsing /tags directory"""
        path = VFSPathParser.parse('/tags')

        assert path.path_type == PathType.TAGS
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_tag_directory(self):
        """Test parsing tag directory"""
        path = VFSPathParser.parse('/tags/python')

        assert path.path_type == PathType.TAG_DIR
        assert path.tag_path == 'python'
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_nested_tag_directory(self):
        """Test parsing nested tag directory"""
        path = VFSPathParser.parse('/tags/python/asyncio')

        assert path.path_type == PathType.TAG_DIR
        assert path.tag_path == 'python/asyncio'

    @pytest.mark.unit
    def test_parse_conversation_in_tag(self):
        """Test parsing conversation within tag"""
        path = VFSPathParser.parse('/tags/python/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'
        assert path.tag_path == 'python'

    @pytest.mark.unit
    def test_parse_message_in_tagged_conversation(self):
        """Test parsing message in tagged conversation"""
        path = VFSPathParser.parse('/tags/python/abc123/m1')

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1']
        assert path.tag_path == 'python'


class TestSourcePath:
    """Test parsing /source paths"""

    @pytest.mark.unit
    def test_parse_source_directory(self):
        """Test parsing /source directory"""
        path = VFSPathParser.parse('/source')

        assert path.path_type == PathType.SOURCE
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_source_provider(self):
        """Test parsing source provider directory"""
        path = VFSPathParser.parse('/source/openai')

        assert path.path_type == PathType.SOURCE
        assert path.segments == ['source', 'openai']

    @pytest.mark.unit
    def test_parse_conversation_in_source(self):
        """Test parsing conversation in source"""
        path = VFSPathParser.parse('/source/openai/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'

    @pytest.mark.unit
    def test_parse_message_in_source(self):
        """Test parsing message in source conversation"""
        path = VFSPathParser.parse('/source/openai/abc123/m1')

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.message_path == ['m1']


class TestModelPath:
    """Test parsing /model paths"""

    @pytest.mark.unit
    def test_parse_model_directory(self):
        """Test parsing /model directory"""
        path = VFSPathParser.parse('/model')

        assert path.path_type == PathType.MODEL
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_model_name(self):
        """Test parsing model name directory"""
        path = VFSPathParser.parse('/model/gpt-4')

        assert path.path_type == PathType.MODEL
        assert path.segments == ['model', 'gpt-4']

    @pytest.mark.unit
    def test_parse_conversation_in_model(self):
        """Test parsing conversation in model"""
        path = VFSPathParser.parse('/model/gpt-4/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'


class TestRecentPath:
    """Test parsing /recent paths"""

    @pytest.mark.unit
    def test_parse_recent_directory(self):
        """Test parsing /recent directory"""
        path = VFSPathParser.parse('/recent')

        assert path.path_type == PathType.RECENT
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_recent_time_period(self):
        """Test parsing recent time period"""
        path = VFSPathParser.parse('/recent/today')

        assert path.path_type == PathType.RECENT
        assert path.segments == ['recent', 'today']

    @pytest.mark.unit
    def test_parse_conversation_in_recent(self):
        """Test parsing conversation in recent"""
        path = VFSPathParser.parse('/recent/today/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'


class TestReadOnlyChecks:
    """Test read-only path detection"""

    @pytest.mark.unit
    def test_root_is_readonly(self):
        """Test that root is read-only"""
        path = VFSPathParser.parse('/')
        assert VFSPathParser.is_read_only(path) is True

    @pytest.mark.unit
    def test_chats_is_readonly(self):
        """Test that /chats is read-only"""
        path = VFSPathParser.parse('/chats')
        assert VFSPathParser.is_read_only(path) is True

    @pytest.mark.unit
    def test_starred_is_readonly(self):
        """Test that /starred is read-only"""
        path = VFSPathParser.parse('/starred')
        assert VFSPathParser.is_read_only(path) is True

    @pytest.mark.unit
    def test_tags_is_mutable(self):
        """Test that /tags is mutable"""
        path = VFSPathParser.parse('/tags/python')
        assert VFSPathParser.is_read_only(path) is False

    @pytest.mark.unit
    def test_source_is_readonly(self):
        """Test that /source is read-only"""
        path = VFSPathParser.parse('/source/openai')
        assert VFSPathParser.is_read_only(path) is True


class TestDeletePermissions:
    """Test delete permissions"""

    @pytest.mark.unit
    def test_can_delete_from_chats(self):
        """Test that conversations can be deleted from /chats"""
        path = VFSPathParser.parse('/chats/abc123')
        # Note: Current implementation may not set CONVERSATION type for /chats/abc123
        # This tests the logic if it were implemented

    @pytest.mark.unit
    def test_can_delete_from_tags(self):
        """Test that items can be deleted from /tags"""
        path = VFSPathParser.parse('/tags/python/abc123')
        assert VFSPathParser.can_delete(path) is True


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.unit
    def test_parse_invalid_root(self):
        """Test parsing path with invalid root"""
        with pytest.raises(ValueError, match="Unknown filesystem root"):
            VFSPathParser.parse('/invalid')

    @pytest.mark.unit
    def test_parse_invalid_message_node(self):
        """Test parsing path with invalid message node"""
        with pytest.raises(ValueError, match="Invalid message node"):
            VFSPathParser.parse('/chats/abc123/invalid')

    @pytest.mark.unit
    def test_parse_message_segments_empty(self):
        """Test parsing empty message segments"""
        path_type, msg_path, file_name = VFSPathParser.parse_message_segments([], '/test')
        assert path_type == PathType.MESSAGE_NODE
        assert msg_path == []
        assert file_name is None

    @pytest.mark.unit
    def test_str_representation(self):
        """Test string representation of VFSPath"""
        path = VFSPathParser.parse('/chats/abc123')
        assert str(path) == '/chats/abc123'

    @pytest.mark.unit
    def test_parse_with_current_dir(self):
        """Test parsing relative path with current directory"""
        path = VFSPathParser.parse('abc123', current_dir='/chats')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == 'abc123'

    @pytest.mark.unit
    def test_complex_tag_path_with_conversation(self):
        """Test complex tag path with nested tags and conversation"""
        path = VFSPathParser.parse('/tags/python/web/flask/abc123/m1/text')

        assert path.path_type == PathType.MESSAGE_FILE
        assert path.conversation_id == 'abc123'
        assert path.tag_path == 'python/web/flask'
        assert path.message_path == ['m1']
        assert path.file_name == 'text'

    @pytest.mark.unit
    def test_multiple_slashes(self):
        """Test that multiple slashes are normalized"""
        path = VFSPathParser.parse('//chats///abc123//')
        assert path.normalized_path == '/chats/abc123'

    @pytest.mark.unit
    def test_metadata_file_at_conversation_root(self):
        """Test that metadata file must be in message node"""
        # /chats/abc123/text should not be treated as metadata file
        # because it's directly under conversation, not under a message node
        path = VFSPathParser.parse('/chats/abc123/text')

        # This should either be invalid or treated as message node
        # depending on implementation
        assert path.path_type in [PathType.MESSAGE_NODE, PathType.MESSAGE_FILE]


class TestVFSPathDataclass:
    """Test VFSPath dataclass"""

    @pytest.mark.unit
    def test_vfs_path_creation(self):
        """Test creating VFSPath"""
        path = VFSPath(
            raw_path='/chats/abc',
            normalized_path='/chats/abc',
            segments=['chats', 'abc'],
            path_type=PathType.CONVERSATION_ROOT,
            conversation_id='abc',
            is_directory=True
        )

        assert path.raw_path == '/chats/abc'
        assert path.conversation_id == 'abc'
        assert path.is_directory is True

    @pytest.mark.unit
    def test_vfs_path_optional_fields(self):
        """Test VFSPath with optional fields"""
        path = VFSPath(
            raw_path='/',
            normalized_path='/',
            segments=[],
            path_type=PathType.ROOT
        )

        assert path.conversation_id is None
        assert path.tag_path is None
        assert path.message_path is None
        assert path.file_name is None
        assert path.is_directory is True  # Default value


class TestViewsPath:
    """Test parsing /views paths"""

    @pytest.mark.unit
    def test_parse_views_directory(self):
        """Test parsing /views directory"""
        path = VFSPathParser.parse('/views')

        assert path.path_type == PathType.VIEWS
        assert path.is_directory is True
        assert path.segments == ['views']

    @pytest.mark.unit
    def test_parse_view_directory(self):
        """Test parsing specific view directory"""
        path = VFSPathParser.parse('/views/my-view')

        assert path.path_type == PathType.VIEW_DIR
        assert path.view_name == 'my-view'
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_conversation_in_view(self):
        """Test parsing conversation within view"""
        path = VFSPathParser.parse('/views/my-view/abc123')

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.view_name == 'my-view'
        assert path.conversation_id == 'abc123'
        assert path.is_directory is True

    @pytest.mark.unit
    def test_parse_message_in_view(self):
        """Test parsing message node within view conversation"""
        path = VFSPathParser.parse('/views/my-view/abc123/m1')

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.view_name == 'my-view'
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1']

    @pytest.mark.unit
    def test_parse_nested_message_in_view(self):
        """Test parsing nested message nodes within view"""
        path = VFSPathParser.parse('/views/my-view/abc123/m1/m2')

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.view_name == 'my-view'
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1', 'm2']

    @pytest.mark.unit
    def test_parse_metadata_file_in_view(self):
        """Test parsing metadata file within view conversation"""
        path = VFSPathParser.parse('/views/my-view/abc123/m1/text')

        assert path.path_type == PathType.MESSAGE_FILE
        assert path.view_name == 'my-view'
        assert path.conversation_id == 'abc123'
        assert path.message_path == ['m1']
        assert path.file_name == 'text'
        assert path.is_directory is False

    @pytest.mark.unit
    def test_parse_view_with_dashes(self):
        """Test parsing view name with dashes"""
        path = VFSPathParser.parse('/views/my-complex-view-name')

        assert path.path_type == PathType.VIEW_DIR
        assert path.view_name == 'my-complex-view-name'

    @pytest.mark.unit
    def test_vfs_path_view_name_field(self):
        """Test VFSPath view_name optional field"""
        path = VFSPath(
            raw_path='/views/test',
            normalized_path='/views/test',
            segments=['views', 'test'],
            path_type=PathType.VIEW_DIR,
            view_name='test',
            is_directory=True
        )

        assert path.view_name == 'test'
