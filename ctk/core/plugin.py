"""
Plugin system for importers and exporters
"""

import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Type, Callable
from abc import ABC, abstractmethod
import json

from .models import ConversationTree


class BasePlugin(ABC):
    """Base class for all plugins"""
    
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    supported_formats: List[str] = []
    
    @abstractmethod
    def validate(self, data: Any) -> bool:
        """Validate if this plugin can handle the data"""
        pass


class ImporterPlugin(BasePlugin):
    """Base class for importer plugins"""
    
    @abstractmethod
    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        """Import data and return ConversationTree objects"""
        pass
    
    def detect_format(self, data: Any) -> bool:
        """Auto-detect if this importer can handle the data"""
        return self.validate(data)


class ExporterPlugin(BasePlugin):
    """Base class for exporter plugins"""
    
    @abstractmethod
    def export_data(self, conversations: List[ConversationTree], **kwargs) -> Any:
        """Export ConversationTree objects to target format"""
        pass
    
    def export_to_file(self, conversations: List[ConversationTree], 
                      file_path: str, **kwargs) -> None:
        """Export to file"""
        data = self.export_data(conversations, **kwargs)
        
        if isinstance(data, str):
            mode = 'w'
        elif isinstance(data, bytes):
            mode = 'wb'
        else:
            # Assume JSON serializable
            data = json.dumps(data, indent=2)
            mode = 'w'
        
        with open(file_path, mode) as f:
            f.write(data)


class PluginRegistry:
    """Registry for managing plugins"""
    
    def __init__(self):
        self.importers: Dict[str, ImporterPlugin] = {}
        self.exporters: Dict[str, ExporterPlugin] = {}
        self._discovered = False
    
    def register_importer(self, name: str, plugin: ImporterPlugin):
        """Register an importer plugin"""
        self.importers[name] = plugin
    
    def register_exporter(self, name: str, plugin: ExporterPlugin):
        """Register an exporter plugin"""
        self.exporters[name] = plugin
    
    def discover_plugins(self, plugin_dir: Optional[str] = None):
        """Discover and load plugins from directory"""
        if self._discovered:
            return
        
        if plugin_dir is None:
            # Default to integrations directory
            base_dir = Path(__file__).parent.parent
            plugin_dir = base_dir / "integrations"
        else:
            plugin_dir = Path(plugin_dir)
        
        # Discover importers
        importers_dir = plugin_dir / "importers"
        if importers_dir.exists():
            self._load_plugins_from_dir(importers_dir, ImporterPlugin, self.importers)
        
        # Discover exporters
        exporters_dir = plugin_dir / "exporters"
        if exporters_dir.exists():
            self._load_plugins_from_dir(exporters_dir, ExporterPlugin, self.exporters)
        
        self._discovered = True
    
    def _load_plugins_from_dir(self, directory: Path, base_class: Type, 
                               registry: Dict[str, BasePlugin]):
        """Load plugins from a directory"""
        for file_path in directory.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            module_name = file_path.stem
            spec = importlib.util.spec_from_file_location(
                f"ctk_plugin_{module_name}", file_path
            )
            
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find plugin classes in module
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, base_class) and 
                        obj != base_class and
                        not inspect.isabstract(obj)):
                        
                        plugin_instance = obj()
                        plugin_name = plugin_instance.name or module_name
                        registry[plugin_name] = plugin_instance
    
    def get_importer(self, name: str) -> Optional[ImporterPlugin]:
        """Get an importer plugin by name"""
        self.discover_plugins()
        return self.importers.get(name)
    
    def get_exporter(self, name: str) -> Optional[ExporterPlugin]:
        """Get an exporter plugin by name"""
        self.discover_plugins()
        return self.exporters.get(name)
    
    def auto_detect_importer(self, data: Any) -> Optional[ImporterPlugin]:
        """Auto-detect appropriate importer for data"""
        self.discover_plugins()
        
        for name, importer in self.importers.items():
            if importer.detect_format(data):
                return importer
        
        return None
    
    def list_importers(self) -> List[str]:
        """List available importers"""
        self.discover_plugins()
        return list(self.importers.keys())
    
    def list_exporters(self) -> List[str]:
        """List available exporters"""
        self.discover_plugins()
        return list(self.exporters.keys())
    
    def import_file(self, file_path: str, format: Optional[str] = None) -> List[ConversationTree]:
        """Import from file with auto-detection"""
        with open(file_path, 'r') as f:
            data = f.read()
        
        # Try to parse as JSON
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            pass
        
        if format:
            importer = self.get_importer(format)
            if not importer:
                raise ValueError(f"Unknown import format: {format}")
        else:
            importer = self.auto_detect_importer(data)
            if not importer:
                raise ValueError("Could not auto-detect format")
        
        return importer.import_data(data)
    
    def export_file(self, conversations: List[ConversationTree], 
                   file_path: str, format: str, **kwargs):
        """Export to file"""
        exporter = self.get_exporter(format)
        if not exporter:
            raise ValueError(f"Unknown export format: {format}")
        
        exporter.export_to_file(conversations, file_path, **kwargs)


# Global registry instance
registry = PluginRegistry()