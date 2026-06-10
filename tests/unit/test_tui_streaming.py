"""Pilot tests for the streaming chat turn: thinking block, live bubbles,
elapsed indicator, cancellation, and in-stream errors."""

from __future__ import annotations

import pytest

from ctk.tui.main_pane import ThinkingBlock

pytestmark = [pytest.mark.unit]


class TestThinkingBlock:
    def test_appends_and_reports_text(self):
        block = ThinkingBlock()
        block.append_reasoning("step one ")
        block.append_reasoning("step two")
        assert block.reasoning_text == "step one step two"
        assert not block.folded

    def test_fold_and_toggle(self):
        block = ThinkingBlock()
        block.append_reasoning("hmm")
        block.fold()
        assert block.folded
        block.action_expand_collapse()
        assert not block.folded
