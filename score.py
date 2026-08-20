import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import quality
from project_config import PROJECT_ROOT, WORKSPACE_ROOT, RESULT_DIR, OCR_CSV

BASE = str(PROJECT_ROOT)
IN_CSV = str(OCR_CSV)
OUT_CSV = str(RESULT_DIR / "评分总表.csv")
EVAL_LEVEL = 70

sys.path.insert(0, os.path.join(BASE, "score"))
from local_expected import (  # noqa: E402
    compute_expected,
    EVALUATION_MAIN_SKILL_LEVEL,
    food_ids_for_pattern,
)
from local_rank import score_iv_local, ALGORITHM_VERSION, ingredient_pattern_of  # noqa: E402

def score_expected_local(row):
    """本地期待値(移植 pokeSleepCalc):果実能量 + 食材数,统一 EVAL_LEVEL,无加成."""
    species = row["final_form"]
    subs = [row.get(f"subskill{i}") or "" for i in range(1, 6)]
    nature = row.get("nature") or ""
    level = EVAL_LEVEL

    use_food_ids = None
    # A/B/C meanings and per-slot quantities come directly from pokedex.json.
    pattern = ingredient_pattern_of(row)
    if pattern:
        try:
            use_food_ids = food_ids_for_pattern(species, pattern)
        except ValueError as exc:
            return {"status": str(exc)}

    res = compute_expected(
        species, level, subs, nature,
        main_skill_lv=EVALUATION_MAIN_SKILL_LEVEL,
        use_food_ids=use_food_ids,
        main_skill_level_is_final=True,
    )
    if "error" in res:
        return {"status": res["error"]}
    return {"status": "OK", "berry": res["berry_energy"], "total_ing": res["food_count"]}


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    if not os.path.exists(IN_CSV):
        print("box_ocr.csv not found - run extract.py first")
        return
    rows = []
    with open(IN_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    PROGRESS_FILE = str(WORKSPACE_ROOT / "score_progress.json")
    progress = []
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            progress = json.load(f)
    done_ids = {p.get("folder") for p in progress}

    print(f"scoring {len(rows)} Pokémon (個体値 + 期待値, 全本地); resume skipping {len(done_ids)}...", flush=True)

    def is_bad(res):
        # re-score rows that failed or produced no rank
        if not res or res.get("status") not in ("OK", "需手动选进化形态"):
            return True
        if res.get("status") == "OK" and not res.get("rank") and not res.get("pct") and not res.get("berry"):
            return True
        return False

    results = []
    for idx, row in enumerate(rows):
        folder = row.get("folder", "")
        fingerprint = hashlib.sha256(
            json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if not row.get("final_form"):
            # species not recognized by OCR; cannot score
            iv = {"status": "物种OCR识别失败"}
            exp = {"status": "skip"}
            results.append((iv, exp))
            print(f"[{idx+1}/{len(rows)}] species unknown, skip", flush=True)
            continue
        prev = next((x for x in progress if x.get("folder") == folder), None)
        if (prev is not None and prev.get("algorithm_version") == ALGORITHM_VERSION
                and prev.get("input_fingerprint") == fingerprint
                and not is_bad(prev.get("iv")) and not is_bad(prev.get("exp"))):
            iv = prev.get("iv")
            exp = prev.get("exp")
            print(f"[{idx+1}/{len(rows)}] {row.get('final_form')} Lv.{row.get('level')} (resumed) -> "
                  f"IV:{iv.get('rank','')}{iv.get('pct','')} 期待:{exp.get('berry','')}", flush=True)
        else:
            exp = score_expected_local(row)
            iv = score_iv_local(row, EVAL_LEVEL)
            progress = [p for p in progress if p.get("folder") != folder]
            progress.append({
                "folder": folder,
                "algorithm_version": ALGORITHM_VERSION,
                "input_fingerprint": fingerprint,
                "iv": iv,
                "exp": exp,
            })
            quality.atomic_write_json(Path(PROGRESS_FILE), progress)
            print(f"[{idx+1}/{len(rows)}] {row.get('final_form')} Lv.{row.get('level')} -> "
                  f"IV:{iv.get('rank','')}{iv.get('pct','')} 期待:{exp.get('berry','')}", flush=True)
        results.append((iv, exp))

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#", "精灵", "等级", "最终形态", f"个体值评级(评测{EVAL_LEVEL}级)", "百分比",
                    f"期待值-果実能量(评测{EVAL_LEVEL}级)", "期待值-食材数", "食材分布", "食材修正",
                    "子技能", "性格", "状态", "算法版本"])
        for i, (row, (iv, exp)) in enumerate(zip(rows, results), start=1):
            subs = " / ".join(row.get(f"subskill{j}") or "-" for j in range(1, 6))
            w.writerow([i, row.get("species"), row.get("level"), row.get("final_form"),
                        iv.get("rank", ""), iv.get("pct", ""), exp.get("berry", ""), exp.get("total_ing", ""),
                        iv.get("ingredient_pattern") or "未知", iv.get("ingredient_multiplier", 1.0),
                        subs, row.get("nature"), iv.get("status"), ALGORITHM_VERSION])
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
