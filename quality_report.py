"""Generate a concise OCR/capture QA report and a manual review queue."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import quality
from project_config import WORKSPACE_ROOT, RESULT_DIR


ROOT = WORKSPACE_ROOT
DETAIL_OUT = RESULT_DIR / "OCR质检.csv"
REVIEW_OUT = RESULT_DIR / "待复核清单.csv"
SUMMARY_OUT = RESULT_DIR / "质检摘要.json"


def priority(errors: list[str], warnings: list[str]) -> str:
    if any(item.startswith("缺少") or "异常" in item for item in errors):
        return "必须补抓"
    if errors:
        return "必须复核"
    if any(item.startswith("换皮识别:") or "无法解析" in item for item in warnings):
        return "建议复核"
    if warnings:
        return "监控"
    return "通过"


def build() -> dict[str, object]:
    rows = quality.read_ocr_rows()
    row_by_folder = {row.get("folder", ""): row for row in rows}
    manifest_path = ROOT / "manifest.json"
    expected_folders: set[str] = set()
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_folders = {f"{int(item['seq']):04d}" for item in manifest}
        except (OSError, ValueError, KeyError, TypeError):
            expected_folders = set()
    captured_folders = {
        path.name for path in quality.CAP_DIR.iterdir() if path.is_dir()
    } if quality.CAP_DIR.exists() else set()
    all_folders = sorted(expected_folders | captured_folders | set(row_by_folder))
    details: list[dict[str, str]] = []
    for folder in all_folders:
        row = row_by_folder.get(folder, {"folder": folder})
        image_errors = quality.validate_capture_files(quality.CAP_DIR / folder)
        field_errors, warnings = quality.validate_parsed(row)
        errors = image_errors + field_errors
        level = priority(errors, warnings)
        details.append({
            "箱位": str(int(folder) + 1) if folder.isdigit() else folder,
            "文件夹": folder,
            "精灵": row.get("species", ""),
            "等级": row.get("level", ""),
            "食材分布": row.get("ingredient_pattern", ""),
            "优先级": level,
            "错误": "；".join(errors),
            "警告": "；".join(warnings),
            "建议": {
                "必须补抓": "重新采集该箱位四页详情",
                "必须复核": "查看截图并校正字段",
                "建议复核": "重点核对食材或换皮形态",
                "监控": "已通过合法组合约束，保留置信度记录",
                "通过": "",
            }[level],
        })

    fields = list(details[0]) if details else []
    DETAIL_OUT.parent.mkdir(parents=True, exist_ok=True)
    with DETAIL_OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(details)
    review = [row for row in details if row["优先级"] in {"必须补抓", "必须复核", "建议复核"}]
    with REVIEW_OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review)

    counts = Counter(row["优先级"] for row in details)
    summary: dict[str, object] = {
        "应有箱位": len(expected_folders) if expected_folders else len(all_folders),
        "截图文件夹": len(captured_folders),
        "OCR行数": len(rows),
        "总数": len(details),
        "通过": counts["通过"],
        "建议复核": counts["建议复核"],
        "监控": counts["监控"],
        "必须复核": counts["必须复核"],
        "必须补抓": counts["必须补抓"],
        "待复核箱位": [row["箱位"] for row in review],
    }
    quality.atomic_write_json(SUMMARY_OUT, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {DETAIL_OUT}")
    print(f"Wrote {REVIEW_OUT}")
    return summary


if __name__ == "__main__":
    build()
