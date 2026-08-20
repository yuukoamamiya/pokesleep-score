import csv
import json
import os
import sys
from pathlib import Path

import quality
from project_config import PROJECT_ROOT, WORKSPACE_ROOT, RESULT_DIR, OCR_CSV

BASE = str(PROJECT_ROOT)
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "score"))
from score import score_expected_local, EVAL_LEVEL  # noqa: E402
from local_rank import score_iv_local, ALGORITHM_VERSION  # noqa: E402

EVEEVOLUTIONS = ["ブラッキー", "サンダース", "シャワーズ", "ブースター", "エーフィ", "リーフィア", "グレイシア", "ニンフィア"]
STRINDER_FORMS = ["ストリンダー（ハイなすがた）", "ストリンダー（ローなすがた）"]
OUT_CSV = str(RESULT_DIR / "伊布与毒电音进化评分.csv")
PROG = str(WORKSPACE_ROOT / "evo_score_progress.json")


def build_fake_row(base, species):
    return {
        "folder": base["folder"],
        "species": species,
        "level": base["level"],
        "final_form": species,
        "main_skill_lv": base.get("main_skill_lv") or 1,
        "subskill1": base.get("subskill1"), "subskill2": base.get("subskill2"),
        "subskill3": base.get("subskill3"), "subskill4": base.get("subskill4"),
        "subskill5": base.get("subskill5"),
        "nature": base.get("nature"),
        "ingredient_pattern": base.get("ingredient_pattern") or base.get("food_pattern"),
    }


def main():
    with open(OCR_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    targets = []
    for r in rows:
        if r.get("species") == "イーブイ":
            for evo in EVEEVOLUTIONS:
                targets.append(("イーブイ", r, evo))
        elif r.get("species") == "ストリンダー" or r.get("species") == "エレズン":
            for form in STRINDER_FORMS:
                targets.append(("エレズン", r, form))
    print(f"total evolution scoring targets: {len(targets)}", flush=True)

    progress = {}
    if os.path.exists(PROG):
        with open(PROG, encoding="utf-8") as f:
            progress = json.load(f)

    results = []
    for i, (base_species, row, variant) in enumerate(targets):
        key = f"{row['folder']}_{variant}"
        if key in progress and progress[key].get("algorithm_version") == ALGORITHM_VERSION:
            res = progress[key]
            print(f"[{i+1}/{len(targets)}] {base_species}->{variant} (resumed) IV:{res.get('rank','')}{res.get('pct','')} 期待:{res.get('exp','')}", flush=True)
        else:
            fake = build_fake_row(row, variant)
            iv = score_iv_local(fake, EVAL_LEVEL)
            exp = score_expected_local(fake)
            res = {"rank": iv.get("rank", ""), "pct": iv.get("pct", ""),
                   "exp": exp.get("berry", ""), "status": iv.get("status", ""),
                   "algorithm_version": ALGORITHM_VERSION}
            progress[key] = res
            quality.atomic_write_json(Path(PROG), progress)
            print(f"[{i+1}/{len(targets)}] {base_species}->{variant} IV:{res['rank']}{res['pct']} 期待:{res['exp']} [{res['status']}]", flush=True)
        results.append((base_species, row, variant, res))

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["原精灵", "精灵箱位", "等级", "进化形态", f"个体值评级(评测{EVAL_LEVEL}级)", "百分比", "期待值-果实能量", "状态"])
        for base_species, row, variant, res in results:
            w.writerow([base_species, row["folder"], row.get("level"), variant,
                        res.get("rank", ""), res.get("pct", ""), res.get("exp", ""), res.get("status", "")])
    print(f"\nWrote {OUT_CSV} with {len(results)} rows")


if __name__ == "__main__":
    main()
