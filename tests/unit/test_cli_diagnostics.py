import subprocess
import sys

import ctk


def test_version_flag_prints_version():
    out = subprocess.run(
        [sys.executable, "-m", "ctk.cli", "--version"],
        capture_output=True, text=True,
    )
    assert ctk.__version__ in (out.stdout + out.stderr)
    assert out.returncode == 0


def test_usage_uses_ctk_prog():
    out = subprocess.run(
        [sys.executable, "-m", "ctk.cli", "--help"],
        capture_output=True, text=True,
    )
    assert "usage: ctk" in out.stdout
