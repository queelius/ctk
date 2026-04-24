"""Built-in exporter plugins.

Importing this package loads every first-party exporter so the plugin
registry can discover them via ``ExporterPlugin.__subclasses__()``.

Add new exporters here to register them automatically.
"""

from ctk.exporters.csv_exporter import CSVExporter
from ctk.exporters.echo import ECHOExporter
from ctk.exporters.html import HTMLExporter
from ctk.exporters.hugo import HugoExporter
from ctk.exporters.json import JSONExporter
from ctk.exporters.jsonl import JSONLExporter
from ctk.exporters.markdown import MarkdownExporter

__all__ = [
    "CSVExporter",
    "ECHOExporter",
    "HTMLExporter",
    "HugoExporter",
    "JSONExporter",
    "JSONLExporter",
    "MarkdownExporter",
]
