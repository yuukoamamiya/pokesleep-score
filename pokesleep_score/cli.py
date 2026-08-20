"""Stable public command-line entry point."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def configure_console() -> None:
    """Keep Japanese/Chinese paths printable on non-UTF-8 Windows runners."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def workspace_path(value: str | None) -> Path:
    return Path(value or os.environ.get("POKESLEEP_WORKSPACE", ROOT / "workspace")).expanduser().resolve()


def doctor(workspace: Path, as_json: bool = False) -> int:
    required_files = [
        ROOT / "score" / "data" / "pokedex.json",
        ROOT / "score" / "data" / "subSkills.json",
        ROOT / "score" / "data" / "nature.json",
        ROOT / "box-exporter" / "pokemon_data.json",
    ]
    packages = ["numpy", "cv2", "PIL", "onnxruntime", "rapidocr"]
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 12),
            "detail": sys.version.split()[0],
        },
        "data": {
            "ok": all(path.is_file() for path in required_files),
            "detail": [path.name for path in required_files if not path.is_file()] or "ok",
        },
        "dependencies": {
            "ok": all(importlib.util.find_spec(name) is not None for name in packages),
            "detail": [name for name in packages if importlib.util.find_spec(name) is None] or "ok",
        },
        "playwright_optional": {
            "ok": importlib.util.find_spec("playwright") is not None,
            "detail": "required only for --with-daifuku",
        },
        "adb_optional": {
            "ok": bool(shutil.which("adb") or Path(os.environ.get("POKESLEEP_ADB", r"C:\Program Files\Netease\MuMu\nx_main\adb.exe")).is_file()),
            "detail": "required only for full MuMu capture",
        },
        "workspace": {"ok": True, "detail": str(workspace)},
    }
    critical_ok = all(checks[name]["ok"] for name in ("python", "data", "dependencies"))
    if as_json:
        print(json.dumps({"ok": critical_ok, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        for name, result in checks.items():
            mark = "OK" if result["ok"] else ("OPTIONAL" if name.endswith("_optional") else "MISSING")
            print(f"[{mark:8}] {name}: {result['detail']}")
    return 0 if critical_ok else 1


def demo(workspace: Path) -> int:
    demo_results = workspace / "demo" / "results"
    demo_results.mkdir(parents=True, exist_ok=True)
    source = ROOT / "examples" / "评分总表_大福对照.sample.csv"
    output = demo_results / "评分总表_个人规则.csv"
    sys.path.insert(0, str(ROOT))
    from personal_adjustment import build

    build(source, output)
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts = Counter(row["个人建议"] for row in rows)
    print("Demo summary: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    print(f"Output: {output}")
    return 0


def pipeline(command: str, workspace: Path, extra: list[str]) -> int:
    env = os.environ.copy()
    env["POKESLEEP_WORKSPACE"] = str(workspace)
    return subprocess.call(
        [sys.executable, "-X", "utf8", str(ROOT / "run_pipeline.py"), command, *extra],
        cwd=ROOT,
        env=env,
    )


def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(prog="pokesleep-score", description="Pokémon Sleep box OCR and scoring")
    parser.add_argument("--workspace", help="private runtime directory (default: ./workspace)")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor", help="check the local installation")
    doctor_parser.add_argument("--json", action="store_true")
    sub.add_parser("demo", help="run a sanitized offline scoring-rule demo")
    sub.add_parser("report", help="regenerate reports from existing workspace data")
    offline_parser = sub.add_parser("offline", help="OCR and score existing screenshots")
    offline_parser.add_argument("--reuse-ocr", action="store_true")
    offline_parser.add_argument("--with-daifuku", action="store_true")
    full_parser = sub.add_parser("full", help="capture from MuMu, OCR and score")
    full_parser.add_argument("--with-daifuku", action="store_true")
    args = parser.parse_args()
    workspace = workspace_path(args.workspace)

    if args.command == "doctor":
        raise SystemExit(doctor(workspace, args.json))
    if args.command == "demo":
        raise SystemExit(demo(workspace))
    extra: list[str] = []
    if getattr(args, "reuse_ocr", False):
        extra.append("--reuse-ocr")
    if getattr(args, "with_daifuku", False):
        extra.append("--with-daifuku")
    raise SystemExit(pipeline(args.command, workspace, extra))
