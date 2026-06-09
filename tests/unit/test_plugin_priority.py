from ctk.core.plugin import PluginRegistry


def test_auto_detect_prefers_higher_priority():
    # Function-local on purpose: module-level subclasses of ImporterPlugin
    # would enter every test's plugin discovery via __subclasses__().
    class _GreedyImporter:
        name = "greedy-test"
        detection_priority = 0

        def validate(self, data):
            return True

        def import_data(self, data, **kwargs):
            return []

        def detect_format(self, data):
            return self.validate(data)

    class _SpecificImporter:
        name = "specific-test"
        detection_priority = 100

        def validate(self, data):
            return isinstance(data, dict) and data.get("format") == "specific"

        def import_data(self, data, **kwargs):
            return []

        def detect_format(self, data):
            return self.validate(data)

    reg = PluginRegistry()
    # Bypass discovery by setting the internal flag directly.
    reg._discovered = True
    # Worst-case insertion order: greedy is registered first (lower priority).
    reg.importers = {
        "greedy-test": _GreedyImporter(),
        "specific-test": _SpecificImporter(),
    }
    chosen = reg.auto_detect_importer({"format": "specific"})
    assert chosen.name == "specific-test"
