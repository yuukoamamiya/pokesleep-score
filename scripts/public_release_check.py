"""Fail if obvious private/runtime artifacts slipped into the public tree."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
FORBIDDEN_DIRS = {"workspace", "pw-profile", "cap", "评分结果", ".opencode", "_reference_pokeSleepCalc"}
FORBIDDEN_FILES = {
    "box_ocr.csv",
    "capture_progress.json",
    "capture_quality.json",
    "score_progress.json",
    "evo_score_progress.json",
    "daifuku_progress.json",
    "manifest.json",
    "baseline.json",
}
MAX_FILE_BYTES = 10 * 1024 * 1024


def main() -> int:
    problems: list[str] = []
    tracked: set[Path] | None = None
    if (ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        )
        tracked = {
            Path(item.decode("utf-8"))
            for item in result.stdout.split(b"\0")
            if item
        }
        for rel in tracked:
            if any(part in FORBIDDEN_DIRS for part in rel.parts):
                problems.append(f"tracked private path: {rel}")
    for current, dirs, files in os.walk(ROOT):
        relative = Path(current).relative_to(ROOT)
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        dirs[:] = [name for name in dirs if name not in FORBIDDEN_DIRS]
        for name in files:
            path = Path(current) / name
            rel = path.relative_to(ROOT)
            is_publishable = tracked is None or rel in tracked
            if is_publishable and name in FORBIDDEN_FILES and "examples" not in rel.parts:
                problems.append(f"runtime file: {rel}")
            if is_publishable and path.stat().st_size > MAX_FILE_BYTES:
                problems.append(f"large file ({path.stat().st_size} bytes): {rel}")
    if problems:
        print("Public release check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("Public release check passed: no obvious private artifacts or files over 10 MiB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
