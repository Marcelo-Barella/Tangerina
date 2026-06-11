import sys
import tempfile
from pathlib import Path
from typing import Optional

_deploy_dir = Path(__file__).resolve().parents[2] / "deploy"
if str(_deploy_dir) not in sys.path:
    sys.path.insert(0, str(_deploy_dir))
from temp_files import unlink_temp


def ensure_output_path(output_path: Optional[str]) -> str:
    if output_path:
        return output_path
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    path = temp_file.name
    temp_file.close()
    return path
