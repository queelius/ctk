# Repository Guidelines

## Project Structure & Module Organization

- `ctk/`: main Python package.
  - `ctk/core/`: database, models, plugin registry, core commands.
  - `ctk/integrations/`: provider integrations (importers/exporters, LLM, taggers).
  - `ctk/interfaces/`: CLI/TUI and optional interfaces (MCP, REST, web).
- `tests/`: pytest suite (`tests/unit/`, `tests/integration/`).
- `docs/`: MkDocs content; `mkdocs.yml` defines nav and theme.
- `examples/`: example configs and usage notes.
- `dist/`: release artifacts (built by `python -m build`).

When adding a new provider/format, place code under `ctk/integrations/importers/` or
`ctk/integrations/exporters/` and ensure it is discoverable via the plugin registry.

## Build, Test, and Development Commands

Recommended setup:

```bash
python -m venv .venv && source .venv/bin/activate
make install
```

Common commands:

- `make test`: run the full test suite.
- `make test-unit` / `make test-integration`: run marked subsets.
- `make coverage`: generate `htmlcov/` coverage report.
- `make lint`: run `flake8` + `mypy` (CI uses `mypy --ignore-missing-imports`).
- `make format`: format with `black` and `isort`.
- `python -m build`: build sdist/wheel into `dist/` (release workflow).
- `mkdocs serve`: serve docs locally (install `mkdocs-material` if needed).

## Coding Style & Naming Conventions

- Python: 4-space indentation, type hints where practical.
- Formatting: `black` (CI enforces `black --check ctk tests`).
- Linting: `flake8 ctk tests --max-line-length=100 --ignore=E203,W503`.
- Imports: keep stable ordering (`isort` is used by `make format`).
- Tests: `test_*.py`, `Test*` classes, `test_*` functions.

## Testing Guidelines

- Framework: `pytest` with `pytest-cov` (see `pytest.ini`).
- Coverage gate: `--cov-fail-under=59` by default.
- Use markers for expensive/external tests: `slow`, `requires_ollama`, `requires_api_key`.
  Example: `pytest -m "not slow and not requires_api_key"`.

## Commit & Pull Request Guidelines

- Commit subjects follow an imperative style seen in history: `Add …`, `Fix …`, `Refactor …`, `Bump version …`.
- Keep commits focused; include test updates when changing behavior.
- PRs should include: clear problem/solution description, how to test locally, and screenshots for UI/TUI changes.

## Security & Configuration Tips

- Do not commit secrets. Copy `config.example.json` to a local config and add keys via environment variables or ignored files.
- Treat exported conversations and databases (`*.db`) as sensitive user data.
