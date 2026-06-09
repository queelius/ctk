from ctk.core.plugin import ImporterPlugin, PluginRegistry


class _GreedyImporter(ImporterPlugin):
    name = "greedy-test"
    detection_priority = 0

    def validate(self, data):
        return True

    def import_data(self, data, **kwargs):
        return []


class _SpecificImporter(ImporterPlugin):
    name = "specific-test"
    detection_priority = 100

    def validate(self, data):
        return isinstance(data, dict) and data.get("format") == "specific"

    def import_data(self, data, **kwargs):
        return []


def test_auto_detect_prefers_higher_priority():
    reg = PluginRegistry()
    # Bypass discovery by setting the internal flag directly.
    reg._discovered = True
    reg.importers = {
        "greedy-test": _GreedyImporter(),
        "specific-test": _SpecificImporter(),
    }
    chosen = reg.auto_detect_importer({"format": "specific"})
    assert chosen.name == "specific-test"
