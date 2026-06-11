import importlib.util
import sys
from pathlib import Path

import pytest

SANITIZE_PATH = Path(__file__).resolve().parents[2] / "deploy" / "sanitize_text.py"
SANITIZE_MODULE = "sanitize_text_under_test"


def _load_sanitize_module():
    deploy_dir = str(SANITIZE_PATH.parents[1])
    if deploy_dir not in sys.path:
        sys.path.insert(0, deploy_dir)
    sys.modules.pop(SANITIZE_MODULE, None)
    spec = importlib.util.spec_from_file_location(SANITIZE_MODULE, SANITIZE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[SANITIZE_MODULE] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestSanitizeText:
    @pytest.fixture
    def sanitize(self):
        return _load_sanitize_module()

    def test_strips_emoji_and_control_characters(self, sanitize):
        assert sanitize.sanitize_text("hello 😀 world\x00test") == "hello worldtest"

    def test_collapses_whitespace(self, sanitize):
        assert sanitize.sanitize_text("  hello   world  ") == "hello world"

    def test_returns_empty_string_for_emoji_only_input(self, sanitize):
        assert sanitize.sanitize_text("😀🎉") == ""

    def test_preserves_portuguese_text(self, sanitize):
        assert sanitize.sanitize_text("Olá, tudo bem?") == "Olá, tudo bem?"
