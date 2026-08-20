"""One entry point for capture, offline processing, QA and report generation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from project_config import PROJECT_ROOT, RESULT_DIR, ensure_workspace


ROOT = PROJECT_ROOT
PYTHON = Path(sys.executable)


def run_script(name: str, *arguments: str) -> None:
    command = [str(PYTHON), "-X", "utf8", str(ROOT / name), *arguments]
    print(f"\n=== {name} {' '.join(arguments)} ===", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def reports() -> None:
    run_script("quality_report.py")
    comparison = RESULT_DIR / "评分总表_大福对照.csv"
    if comparison.exists():
        run_script("personal_adjustment.py")
        run_script("make_box_longshot.py", "--rank-source", "daifuku")
        run_script("make_box_longshot.py", "--rank-source", "personal")
    else:
        print("未找到大福对照表，跳过个人修正和评分长图。", flush=True)


def offline(reuse_ocr: bool, with_daifuku: bool) -> None:
    if not reuse_ocr:
        run_script("extract.py")
    run_script("quality_report.py")
    run_script("score.py")
    if with_daifuku:
        run_script("daifuku_compare.py")
    comparison = RESULT_DIR / "评分总表_大福对照.csv"
    if comparison.exists():
        run_script("personal_adjustment.py")
        run_script("make_box_longshot.py", "--rank-source", "daifuku")
        run_script("make_box_longshot.py", "--rank-source", "personal")


def main() -> None:
    ensure_workspace()
    parser = argparse.ArgumentParser(description="Pokémon Sleep 批量评分流水线")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("report", help="用现有CSV重新生成质检、个人规则和长图")
    offline_parser = subparsers.add_parser("offline", help="从已有截图执行OCR及后续处理")
    offline_parser.add_argument("--reuse-ocr", action="store_true", help="复用现有box_ocr.csv")
    offline_parser.add_argument("--with-daifuku", action="store_true", help="联网提交大福")
    full_parser = subparsers.add_parser("full", help="从MuMu采集开始执行完整流程")
    full_parser.add_argument("--with-daifuku", action="store_true", help="联网提交大福")
    args = parser.parse_args()

    if args.command == "report":
        reports()
    elif args.command == "offline":
        offline(args.reuse_ocr, args.with_daifuku)
    else:
        run_script("capture.py")
        offline(False, args.with_daifuku)


if __name__ == "__main__":
    main()
