import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy"


def install_deploy_path() -> None:
    deploy_path = str(DEPLOY_DIR)
    if deploy_path not in sys.path:
        sys.path.insert(0, deploy_path)


def load_sidecar_server(relative_path: str, module_name: str):
    install_deploy_path()
    if isinstance(sys.modules.get("flask"), MagicMock):
        del sys.modules["flask"]
    server_path = DEPLOY_DIR / relative_path
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, server_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def fake_named_tempfile(created_paths: list[str], tmp_path, **_kwargs):
    handle = MagicMock()
    path = str(tmp_path / f"temp-{len(created_paths)}.wav")
    created_paths.append(path)
    handle.name = path
    handle.__enter__ = MagicMock(return_value=handle)
    handle.__exit__ = MagicMock(return_value=False)
    return handle
