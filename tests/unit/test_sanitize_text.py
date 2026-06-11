import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy"))
from sanitize_text import sanitize_text


@pytest.mark.unit
class TestSanitizeText:
    def test_strips_emoji_and_control_characters(self):
        assert sanitize_text("hello 😀 world\x00test") == "hello worldtest"

    def test_collapses_whitespace(self):
        assert sanitize_text("  hello   world  ") == "hello world"

    def test_returns_empty_string_for_emoji_only_input(self):
        assert sanitize_text("😀🎉") == ""
