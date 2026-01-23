# Contributors

Thank you to everyone who has contributed to CTK!

## Project Lead

- **Alex Towell** ([@queelius](https://github.com/queelius)) - Creator and maintainer
  - ORCID: [0000-0001-6443-9897](https://orcid.org/0000-0001-6443-9897)

## Contributors

<!--
Add yourself here when you contribute!
Format: - **Name** ([@github-username](https://github.com/username)) - Brief description of contribution
-->

*Be the first contributor! See below for how to get started.*

---

## How to Contribute

We welcome contributions of all kinds:

### Code Contributions

1. **Fork** the repository
2. **Create a branch** for your feature (`git checkout -b feature/amazing-feature`)
3. **Make your changes** with tests
4. **Run tests** (`make test`)
5. **Format code** (`make format`)
6. **Submit a PR**

### Types of Contributions

| Type | Description |
|------|-------------|
| **Importers** | Add support for new AI providers (see `ctk/integrations/importers/`) |
| **Exporters** | Add new export formats (see `ctk/integrations/exporters/`) |
| **Bug Fixes** | Fix issues and improve stability |
| **Documentation** | Improve README, docstrings, examples |
| **Tests** | Increase test coverage |

### Adding a New Importer

1. Create `ctk/integrations/importers/provider_name.py`
2. Implement `ImporterPlugin` with `validate()` and `import_data()` methods
3. Add tests in `tests/unit/test_importers.py`
4. Update README with usage example

### Adding a New Exporter

1. Create `ctk/integrations/exporters/format_name.py`
2. Implement `ExporterPlugin` with `export_to_file()` method
3. Add tests in `tests/unit/test_exporters.py`
4. Update README and CLI help

---

## Recognition

Contributors are recognized in:
- This file
- Release notes
- The project's Zenodo record (for significant contributions)

## Code of Conduct

Be respectful, inclusive, and constructive. We're all here to build something useful together.
