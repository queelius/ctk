# Windows support follow-up (after 2.20.2)

Until 2.20.2, `import ctk` failed on Windows (`ctk/core/database.py` imported
`fcntl`), so the Windows CI jobs never got past conftest. 2.20.2 removed the
file lock. In the first real run (CI run 40169910131, Python 3.10-3.13),
2347 tests passed and the failures below remained. The Windows jobs are
`continue-on-error` in `.github/workflows/test.yml` until this list is empty;
remove that line when it is.

Fixed in 2.20.2 before release: FTS5 `MATCH` through read-only SQL (the old
SQLite bundled with these Pythons checks `UPDATE sqlite_master` while
building the FTS5 table).

## Likely product bugs (fix in code)

- **CSV exporter doubles line endings.** `test_csv_exporter.py::TestCSVExporterFileIO`
  (both tests, `assert 4 == 2`): the file is opened without `newline=""`, so the
  csv module's `\r\n` becomes `\r\r\n` and readers see blank rows.
- **Database left open by CLI paths.** `WinError 32` (file in use) in
  `tests/integration/test_cli.py` (export, export with filters, import conversion,
  full workflow, search workflow) and `test_zip_import.py`. Windows refuses to
  delete an open SQLite file, so some command paths aren't closing
  `ConversationDB`. Harmless on POSIX, but a real leak.
- **Hugo export with id `..`.** `test_hotfix_export_security.py::TestHugoConversationIdTraversal`
  (`..` with and without a title, `assert 0 == 1`): the expected file isn't
  written. Check `safe_component("..")` and the Hugo path join on Windows
  before assuming it's test-only; this is a 2.20.1 security fix.
- **Plugin trusted-dir checks.** `test_plugin_system.py::TestPluginSecurity`
  (`test_add_trusted_plugin_dir`, `test_plugin_dir_allowed_validation`):
  probably path comparison without `resolve()`/case normalization.

## Likely test-only issues

- `test_cli.py::TestCLIErrorHandling` permission tests: rely on `chmod`, which
  doesn't restrict access on Windows. Skip on Windows, or use a path that's
  invalid on every OS.
- `WinError 267` (directory name invalid) in `test_api.py`, `test_cli_core.py`
  (two import tests), and `test_end_to_end.py`: the tests pass a `*.db` file path
  where ctk expects a directory, or vice versa; check each.
- `test_hotfix_readonly_sql.py::...[db?mode=rwc]`: `?` is illegal in Windows
  filenames; skip that parameter on Windows (`#` and `%` still cover the bug).
- `test_tui_images.py::TestResolveImagePath::test_relative_url_resolves_against_media_root`:
  short (`RUNNER~1`) vs long path in the comparison; compare resolved paths.
