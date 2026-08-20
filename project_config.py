"""Project and private runtime paths shared by the command-line scripts."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = Path(
    os.environ.get("POKESLEEP_WORKSPACE", PROJECT_ROOT / "workspace")
).expanduser().resolve()
CAP_DIR = WORKSPACE_ROOT / "cap"
RESULT_DIR = WORKSPACE_ROOT / "results"
OCR_CSV = WORKSPACE_ROOT / "box_ocr.csv"


def ensure_workspace() -> Path:
    CAP_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSPACE_ROOT
