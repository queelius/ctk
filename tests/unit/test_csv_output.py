import csv
import io

from ctk.cli import _display_sql_results


def test_sql_csv_quotes_commas_and_newlines(capsys):
    rows = [("conv-1", "Hello, world\nsecond line")]
    keys = ["id", "title"]
    _display_sql_results(console=None, rows=rows, keys=keys,
                         format_type="csv", limit=0)
    out = capsys.readouterr().out
    parsed = list(csv.reader(io.StringIO(out)))
    # Header + exactly one data row; the comma/newline title stays one field.
    assert parsed[0] == ["id", "title"]
    assert parsed[1] == ["conv-1", "Hello, world\nsecond line"]
