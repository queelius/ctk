"""Full-screen Textual TUI for ctk.

Entry point: ``ctk tui``. Provides a two-pane browse + chat UI. The
line-oriented ``ctk chat`` shell is unaffected.
"""

from ctk.tui.app import CTKApp, run

__all__ = ["CTKApp", "run"]
