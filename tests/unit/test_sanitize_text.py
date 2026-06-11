import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy"))
from sanitize_text import sanitize_text
from temp_files import unlink_temp


@pytest.mark.unit
class TestSanitizeText:
    def test_strips_emoji_and_control_characters(self):
        assert sanitize_text("hello 😀 world\x00test") == "hello worldtest"

    def test_collapses_whitespace(self):
        assert sanitize_text("  hello   world  ") == "hello world"

    def test_returns_empty_string_for_emoji_only_input(self):
        assert sanitize_text("😀🎉") == ""


@pytest.mark.unit
class TestUnlinkTemp:
    def test_unlink_temp_removes_existing_file(self, tmp_path):
        temp_file = tmp_path / "sidecar.wav"
        temp_file.write_bytes(b"RIFF")
        unlink_temp(str(temp_file))
        assert not temp_file.exists()

    def test_unlink_temp_ignores_missing_file(self, tmp_path):
        unlink_temp(str(tmp_path / "missing.wav"))
