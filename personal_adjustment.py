"""Keep Daifuku authoritative while adding the user's food-pattern rule."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from project_config import PROJECT_ROOT, RESULT_DIR

ROOT = PROJECT_ROOT
sys.path.insert(0, str(ROOT / "score"))
from local_rank import rank_for_table  # noqa: E402


INPUT = RESULT_DIR / "评分总表_大福对照.csv"
OUTPUT = RESULT_DIR / "评分总表_个人规则.csv"
PREFERRED_PATTERNS = {"AAA", "ABB"}
FOOD_SPECIALTY_CATEGORIES = {4, 5, 6}
FOOD_MULTIPLIER = 0.70

CIRCLED_TO_NUMBER = {
    "①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5,
    "⑥": 6, "⑦": 7, "⑧": 8, "⑨": 9,
}


def category_number(value: str) -> int | None:
    value = str(value or "").strip()
    for symbol, number in CIRCLED_TO_NUMBER.items():
        if symbol in value:
            return number
    match = re.search(r"[1-9]", value)
    return int(match.group()) if match else None


def suggestion(rank: str) -> str:
    if rank in {"増田", "SS"}:
        return "星标"
    if rank == "S":
        return "保留观察"
    if rank in {"A", "B", "C", "D"}:
        return "放生候选"
    return "待复核"


def adjust_row(row: dict[str, str]) -> dict[str, str]:
    merged = dict(row)
    raw_rank = str(row.get("大福评级") or "").strip()
    raw_pct_text = str(row.get("大福百分比") or "").strip()
    pattern = str(row.get("食材分布") or "").strip().upper()
    category = category_number(row.get("大福得意分类", ""))
    multiplier = 1.0
    rule = "大福原值"
    if category in FOOD_SPECIALTY_CATEGORIES and pattern and pattern not in PREFERRED_PATTERNS:
        multiplier = FOOD_MULTIPLIER
        rule = f"食材型{pattern}非AAA/ABB，额外×{FOOD_MULTIPLIER:.2f}"

    adjusted_rank = raw_rank
    adjusted_pct = raw_pct_text
    if raw_pct_text and category:
        value = float(raw_pct_text) * multiplier
        adjusted_pct = f"{value:.2f}"
        adjusted_rank = raw_rank if multiplier == 1.0 else rank_for_table(category, value)[0]
    elif not raw_rank:
        rule = "缺少大福结果"

    merged.update({
        "个人食材修正": f"{multiplier:.2f}",
        "个人修正规则": rule,
        "个人修正百分比": adjusted_pct,
        "个人修正评级": adjusted_rank,
        "个人建议": suggestion(adjusted_rank),
    })
    return merged


def build(input_path: Path = INPUT, output_path: Path = OUTPUT) -> Path:
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    adjusted = [adjust_row(row) for row in rows]
    fields = list(adjusted[0]) if adjusted else []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(adjusted)
    print(f"Wrote {output_path} ({len(adjusted)} rows)")
    return output_path


if __name__ == "__main__":
    build()
