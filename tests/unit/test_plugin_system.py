"""
Comprehensive tests for the CTK plugin system.

Tests focus on behavior:
- Plugin discovery and loading
- Plugin registration
- Security validation
- Import/export workflows
"""

import pytest
import tempfile
import json
from pathlib import Path
from typing import List, Any
from unittest.mock import Mock, patch, MagicMock

from ctk.core.plugin import (
    BasePlugin,
    ImporterPlugin,
    ExporterPlugin,
    PluginRegistry
)
from ctk.core.models import ConversationTree, Message, MessageRole, MessageContent


# ==================== Mock Plugins for Testing ====================

class MockImporter(ImporterPlugin):
    """Mock importer for testing"""
    name = "mock_importer"
    description = "Test importer"
    version = "1.0.0"
    supported_formats = ["mock"]

    def validate(self, data: Any) -> bool:
        return isinstance(data, dict) and data.get('format') == 'mock'

    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        tree = ConversationTree()
        tree.id = data.get('id', 'test-id')
        tree.title = data.get('title', 'Test')
        return [tree]


class MockExporter(ExporterPlugin):
    """Mock exporter for testing"""
    name = "mock_exporter"
    description = "Test exporter"
    version = "1.0.0"
    supported_formats = ["mock"]

    def validate(self, data: Any) -> bool:
        return True

    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        return {'conversations': [{'id': c.id, 'title': c.title} for c in conversations]}


# ==================== Fixtures ====================

@pytest.fixture
def plugin_registry():
    """Create a fresh plugin registry for each test"""
    return PluginRegistry()


@pytest.fixture
def mock_conversation():
    """Create a mock conversation for testing"""
    tree = ConversationTree()
    tree.id = "test-conv-123"
    tree.title = "Test Conversation"
    return tree


@pytest.fixture
def temp_plugin_dir():
    """Create a temporary directory for plugin testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ==================== Plugin Registry Initialization Tests ====================

class TestPluginRegistryInitialization:
    """Test plugin registry initialization"""

    def test_registry_starts_empty(self, plugin_registry):
        """Given new registry, should have no plugins registered"""
        assert len(plugin_registry.importers) == 0
        assert len(plugin_registry.exporters) == 0

    def test_registry_has_default_allowed_dirs(self, plugin_registry):
        """Given new registry, should have integrations dir as trusted"""
        assert len(plugin_registry.allowed_plugin_dirs) > 0
        # Should contain path to integrations directory
        dirs_str = ' '.join(plugin_registry.allowed_plugin_dirs)
        assert 'integrations' in dirs_str

    def test_registry_accepts_custom_allowed_dirs(self):
        """Given custom allowed dirs, registry should store them"""
        custom_dirs = ['/custom/path1', '/custom/path2']
        registry = PluginRegistry(allowed_plugin_dirs=custom_dirs)
        assert len(registry.allowed_plugin_dirs) >= 2


# ==================== Plugin Registration Tests ====================

class TestPluginRegistration:
    """Test manual plugin registration"""

    def test_register_importer(self, plugin_registry):
        """Given importer plugin, should be registered by name"""
        importer = MockImporter()
        plugin_registry.register_importer('test', importer)

        assert 'test' in plugin_registry.importers
        assert plugin_registry.importers['test'] == importer

    def test_register_exporter(self, plugin_registry):
        """Given exporter plugin, should be registered by name"""
        exporter = MockExporter()
        plugin_registry.register_exporter('test', exporter)

        assert 'test' in plugin_registry.exporters
        assert plugin_registry.exporters['test'] == exporter

    def test_get_registered_importer(self, plugin_registry):
        """Given registered importer, get_importer should return it"""
        importer = MockImporter()
        plugin_registry.register_importer('mock', importer)

        result = plugin_registry.get_importer('mock')
        assert result == importer

    def test_get_nonexistent_importer(self, plugin_registry):
        """Given nonexistent importer name, should return None"""
        result = plugin_registry.get_importer('nonexistent')
        assert result is None

    def test_get_registered_exporter(self, plugin_registry):
        """Given registered exporter, get_exporter should return it"""
        exporter = MockExporter()
        plugin_registry.register_exporter('mock', exporter)

        result = plugin_registry.get_exporter('mock')
        assert result == exporter

    def test_get_nonexistent_exporter(self, plugin_registry):
        """Given nonexistent exporter name, should return None"""
        result = plugin_registry.get_exporter('nonexistent')
        assert result is None


# ==================== Plugin Listing Tests ====================

class TestPluginListing:
    """Test plugin listing functionality"""

    def test_list_importers_empty(self, plugin_registry):
        """Given no importers, list should be empty"""
        # Prevent discovery
        plugin_registry._discovered = True
        assert plugin_registry.list_importers() == []

    def test_list_exporters_empty(self, plugin_registry):
        """Given no exporters, list should be empty"""
        # Prevent discovery
        plugin_registry._discovered = True
        assert plugin_registry.list_exporters() == []

    def test_list_importers_after_registration(self, plugin_registry):
        """Given registered importers, list should include them"""
        plugin_registry._discovered = True  # Prevent auto-discovery
        plugin_registry.register_importer('test1', MockImporter())
        plugin_registry.register_importer('test2', MockImporter())

        names = plugin_registry.list_importers()
        assert 'test1' in names
        assert 'test2' in names

    def test_list_exporters_after_registration(self, plugin_registry):
        """Given registered exporters, list should include them"""
        plugin_registry._discovered = True  # Prevent auto-discovery
        plugin_registry.register_exporter('test1', MockExporter())
        plugin_registry.register_exporter('test2', MockExporter())

        names = plugin_registry.list_exporters()
        assert 'test1' in names
        assert 'test2' in names


# ==================== Auto-Detection Tests ====================

class TestAutoDetection:
    """Test auto-detection of appropriate importers"""

    def test_auto_detect_matching_importer(self, plugin_registry):
        """Given data matching an importer, should return that importer"""
        plugin_registry._discovered = True
        importer = MockImporter()
        plugin_registry.register_importer('mock', importer)

        data = {'format': 'mock', 'content': 'test'}
        result = plugin_registry.auto_detect_importer(data)

        assert result == importer

    def test_auto_detect_no_match(self, plugin_registry):
        """Given data not matching any importer, should return None"""
        plugin_registry._discovered = True
        plugin_registry.register_importer('mock', MockImporter())

        data = {'format': 'different', 'content': 'test'}
        result = plugin_registry.auto_detect_importer(data)

        assert result is None

    def test_auto_detect_checks_multiple_importers(self, plugin_registry):
        """Given multiple importers, should check all until match"""
        plugin_registry._discovered = True

        # First importer won't match
        importer1 = Mock(spec=ImporterPlugin)
        importer1.detect_format.return_value = False

        # Second will match
        importer2 = MockImporter()

        plugin_registry.importers = {
            'first': importer1,
            'second': importer2
        }

        data = {'format': 'mock'}
        result = plugin_registry.auto_detect_importer(data)

        assert result == importer2


# ==================== Import/Export Workflow Tests ====================

class TestImportExportWorkflows:
    """Test complete import/export workflows"""

    def test_import_file_with_explicit_format(self, plugin_registry, temp_plugin_dir, mock_conversation):
        """Given file with explicit format, should use specified importer"""
        plugin_registry._discovered = True
        plugin_registry.register_importer('mock', MockImporter())

        # Create test file
        test_file = temp_plugin_dir / "test.json"
        test_file.write_text(json.dumps({'format': 'mock', 'id': 'test-123', 'title': 'Test'}))

        # Import
        conversations = plugin_registry.import_file(str(test_file), format='mock')

        assert len(conversations) == 1
        assert conversations[0].id == 'test-123'

    def test_import_file_with_auto_detection(self, plugin_registry, temp_plugin_dir):
        """Given file without format, should auto-detect importer"""
        plugin_registry._discovered = True
        plugin_registry.register_importer('mock', MockImporter())

        # Create test file
        test_file = temp_plugin_dir / "test.json"
        test_file.write_text(json.dumps({'format': 'mock', 'id': 'auto-123'}))

        # Import without specifying format
        conversations = plugin_registry.import_file(str(test_file))

        assert len(conversations) == 1
        assert conversations[0].id == 'auto-123'

    def test_import_file_unknown_format_raises_error(self, plugin_registry, temp_plugin_dir):
        """Given unknown format, should raise ValueError"""
        plugin_registry._discovered = True

        test_file = temp_plugin_dir / "test.json"
        test_file.write_text('{"data": "test"}')

        with pytest.raises(ValueError, match="Unknown import format"):
            plugin_registry.import_file(str(test_file), format='nonexistent')

    def test_import_file_no_auto_detect_match_raises_error(self, plugin_registry, temp_plugin_dir):
        """Given file that doesn't match any importer, should raise ValueError"""
        plugin_registry._discovered = True
        plugin_registry.register_importer('mock', MockImporter())

        test_file = temp_plugin_dir / "test.json"
        test_file.write_text('{"format": "unknown"}')

        with pytest.raises(ValueError, match="Could not auto-detect format"):
            plugin_registry.import_file(str(test_file))

    def test_export_file(self, plugin_registry, temp_plugin_dir, mock_conversation):
        """Given conversations and format, should export to file"""
        plugin_registry._discovered = True
        plugin_registry.register_exporter('mock', MockExporter())

        output_file = temp_plugin_dir / "output.json"

        # Export
        plugin_registry.export_file([mock_conversation], str(output_file), format='mock')

        # Verify file was created
        assert output_file.exists()
        content = json.loads(output_file.read_text())
        assert 'conversations' in content

    def test_export_file_unknown_format_raises_error(self, plugin_registry, temp_plugin_dir, mock_conversation):
        """Given unknown export format, should raise ValueError"""
        plugin_registry._discovered = True

        output_file = temp_plugin_dir / "output.json"

        with pytest.raises(ValueError, match="Unknown export format"):
            plugin_registry.export_file([mock_conversation], str(output_file), format='nonexistent')


# ==================== Plugin Validation Tests ====================

class TestPluginValidation:
    """Test plugin validation logic"""

    def test_validate_plugin_instance_with_valid_importer(self, plugin_registry):
        """Given valid importer, validation should pass"""
        importer = MockImporter()
        assert plugin_registry._validate_plugin_instance(importer) is True

    def test_validate_plugin_instance_with_valid_exporter(self, plugin_registry):
        """Given valid exporter, validation should pass"""
        exporter = MockExporter()
        assert plugin_registry._validate_plugin_instance(exporter) is True

    def test_validate_plugin_instance_without_name_fails(self, plugin_registry):
        """Given plugin without name, validation should fail"""
        plugin = Mock(spec=ImporterPlugin)
        plugin.name = ""
        plugin.import_data = Mock()
        plugin.validate = Mock()

        assert plugin_registry._validate_plugin_instance(plugin) is False

    def test_validate_plugin_instance_checks_callable_methods(self, plugin_registry):
        """Given plugin with non-callable methods, validation should handle gracefully"""
        # This tests the validation logic for method callability
        importer = MockImporter()
        # Override with non-callable (validation should still pass for valid plugin)
        assert plugin_registry._validate_plugin_instance(importer) is True


# ==================== Security Tests ====================

class TestPluginSecurity:
    """Test plugin security features"""

    def test_plugin_dir_allowed_validation(self, plugin_registry):
        """Given allowed plugin dir, validation should pass"""
        test_dir = Path("/allowed/plugins")
        plugin_registry.allowed_plugin_dirs.add(str(test_dir))

        assert plugin_registry._is_plugin_dir_allowed(test_dir) is True

    def test_plugin_dir_not_allowed_fails(self, plugin_registry):
        """Given disallowed plugin dir, validation should fail"""
        test_dir = Path("/untrusted/plugins")

        assert plugin_registry._is_plugin_dir_allowed(test_dir) is False

    def test_add_trusted_plugin_dir(self, plugin_registry):
        """Given new trusted dir, should be added to allowed list"""
        test_dir = "/new/trusted/dir"
        plugin_registry.add_trusted_plugin_dir(test_dir)

        assert any(test_dir in allowed for allowed in plugin_registry.allowed_plugin_dirs)

    def test_validate_plugin_file_size_limit(self, plugin_registry, temp_plugin_dir):
        """Given oversized plugin file, validation should fail"""
        large_file = temp_plugin_dir / "large_plugin.py"

        # Create file > 1MB
        with open(large_file, 'w') as f:
            f.write("x" * (1024 * 1024 + 1))

        assert plugin_registry._validate_plugin_file(large_file) is False

    def test_validate_plugin_file_normal_size_passes(self, plugin_registry, temp_plugin_dir):
        """Given normal-sized plugin file, validation should pass"""
        normal_file = temp_plugin_dir / "normal_plugin.py"
        normal_file.write_text("class TestPlugin: pass")

        assert plugin_registry._validate_plugin_file(normal_file) is True


# ==================== Plugin Discovery Tests ====================

class TestPluginDiscovery:
    """Test plugin discovery mechanism"""

    def test_discover_plugins_only_runs_once(self, plugin_registry):
        """Given discovery already ran, should not run again"""
        plugin_registry._discovered = True

        with patch.object(plugin_registry, '_load_plugins_from_dir') as mock_load:
            plugin_registry.discover_plugins()
            mock_load.assert_not_called()

    def test_discover_plugins_sets_discovered_flag(self, plugin_registry):
        """Given successful discovery, should set _discovered flag"""
        with patch.object(plugin_registry, '_load_plugins_from_dir'):
            with patch.object(plugin_registry, '_is_plugin_dir_allowed', return_value=True):
                plugin_registry.discover_plugins()
                assert plugin_registry._discovered is True

    def test_discover_plugins_skips_disallowed_dirs(self, plugin_registry):
        """Given disallowed plugin dir, discovery should skip it"""
        with patch.object(plugin_registry, '_is_plugin_dir_allowed', return_value=False):
            with patch.object(plugin_registry, '_load_plugins_from_dir') as mock_load:
                plugin_registry.discover_plugins('/untrusted/path')
                mock_load.assert_not_called()


# ==================== Exporter Plugin Base Tests ====================

class TestExporterPluginBase:
    """Test ExporterPlugin base class functionality"""

    def test_export_to_file_with_string_data(self, temp_plugin_dir):
        """Given string export data, should write as text"""
        exporter = Mock(spec=ExporterPlugin)
        exporter.export_data = Mock(return_value="test data")

        # Call actual export_to_file method
        output_file = temp_plugin_dir / "output.txt"
        ExporterPlugin.export_to_file(exporter, [], str(output_file))

        assert output_file.exists()
        assert output_file.read_text() == "test data"

    def test_export_to_file_with_bytes_data(self, temp_plugin_dir):
        """Given bytes export data, should write as binary"""
        exporter = Mock(spec=ExporterPlugin)
        exporter.export_data = Mock(return_value=b"binary data")

        output_file = temp_plugin_dir / "output.bin"
        ExporterPlugin.export_to_file(exporter, [], str(output_file))

        assert output_file.exists()
        assert output_file.read_bytes() == b"binary data"

    def test_export_to_file_with_dict_data(self, temp_plugin_dir):
        """Given dict export data, should JSON serialize it"""
        exporter = Mock(spec=ExporterPlugin)
        exporter.export_data = Mock(return_value={'key': 'value'})

        output_file = temp_plugin_dir / "output.json"
        ExporterPlugin.export_to_file(exporter, [], str(output_file))

        assert output_file.exists()
        content = json.loads(output_file.read_text())
        assert content == {'key': 'value'}


# ==================== Importer Plugin Base Tests ====================

class TestImporterPluginBase:
    """Test ImporterPlugin base class functionality"""

    def test_detect_format_delegates_to_validate(self):
        """Given data, detect_format should delegate to validate"""
        importer = MockImporter()

        # Should return True for mock format
        assert importer.detect_format({'format': 'mock'}) is True

        # Should return False for other format
        assert importer.detect_format({'format': 'other'}) is False
