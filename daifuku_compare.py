"""Submit OCR results to Daifuku's IV checker and merge the comparison CSV."""

import csv
import argparse
from collections import Counter
import hashlib
import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import extract
import quality
from project_config import PROJECT_ROOT, WORKSPACE_ROOT, RESULT_DIR, OCR_CSV


BASE = str(PROJECT_ROOT)
INPUT = str(OCR_CSV)
LOCAL_RESULT = str(RESULT_DIR / "评分总表.csv")
OUTPUT = str(RESULT_DIR / "评分总表_大福对照.csv")
PROGRESS = str(WORKSPACE_ROOT / "daifuku_progress.json")
URL = "https://www.pokemonsleepdaifuku.com/checker/"
PROXY = os.environ.get("DAIFUKU_PROXY", "").strip()
SCRIPT_VERSION = "daifuku-lv70-skill5-v4-new-row"

EEVEE_EVOLUTIONS = (
    "シャワーズ", "サンダース", "ブースター", "エーフィ",
    "ブラッキー", "リーフィア", "グレイシア", "ニンフィア",
)
RANK_ORDER = {"増田": 7, "SS": 6, "S": 5, "A": 4, "B": 3, "C": 2, "D": 1}


SITE_NAME = {
    "ピカチュウ(ハロウィン)": "ハロウィンピカチュウ",
    "ピカチュウ(ホリデー)": "ホリデーピカチュウ",
    "ピカチュウ(船長)": "キャプテンピカチュウ",
    "イーブイ(ホリデー)": "ホリデーイーブイ",
    "イーブイ(ハロウィン)": "ハロウィンイーブイ",
    "タマザラシ(花輪)": "タマザラシ（ホリデー）",
    "アローラキュウコン": "キュウコン（アローラのすがた）",
    "ストリンダー": "ストリンダー（ハイなすがた）",
    "ストリンダー(ロー)": "ストリンダー（ローなすがた）",
    "パンプジン": "パンプジン（ちゅうだましゅ）",
    "ミュウ": "ミュウ（スキル得意で仮入力）",
    "ダークライ": "ダークライ（スキル得意で仮入力）",
}

EXTRA_EVOLUTION_COUNT = {
    "ヤドキング": 1,
    "ハガネール": 1,
    "エルレイド": 2,
    "シャワーズ": 1,
    "サンダース": 1,
    "ブースター": 1,
    "エーフィ": 1,
    "ブラッキー": 1,
    "リーフィア": 1,
    "グレイシア": 1,
    "ニンフィア": 1,
}


def fingerprint(row):
    payload = {"version": SCRIPT_VERSION, "row": row}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def load_progress():
    if not os.path.exists(PROGRESS):
        return {}
    with open(PROGRESS, encoding="utf-8") as handle:
        return json.load(handle)


def save_progress(progress):
    quality.atomic_write_json(Path(PROGRESS), progress)


def evolution_count(final_form, evolution_map):
    sources = [name for name, target in evolution_map.items() if target == final_form]
    if len(sources) >= 2:
        return 2
    if len(sources) == 1:
        return 1
    return EXTRA_EVOLUTION_COUNT.get(final_form, 0)


def result_rows(page):
    rows = page.eval_on_selector_all(
        "tr",
        "trs => trs.map(tr => Array.from(tr.querySelectorAll('th,td'), "
        "td => td.innerText.trim())).filter(c => c.length >= 4 && /%/.test(c[2] || ''))",
    )
    return rows


def select_species(page, site_name, option_map):
    value = option_map.get(site_name)
    if value is None:
        raise ValueError(f"大福无此形态: {site_name}")
    page.select_option("#pokemonNameSelect", value=value)
    page.eval_on_selector(
        "#pokemonNameSelect",
        "e => { window.jQuery(e).trigger('change').trigger('select2:select'); }",
    )
    page.wait_for_timeout(350)


def set_radio(page, name, value):
    page.eval_on_selector(
        f'[name="{name}"][value="{value}"]',
        "e => { e.checked = true; e.dispatchEvent(new Event('change', {bubbles:true})); }",
    )


def submit_form(page, row, mappings, option_map, final_form):
    if not final_form or not row.get("nature") or not row.get("ingredient_ids"):
        return {"status": "OCR字段不完整", "error": "缺少形态、性格或食材"}

    site_name = SITE_NAME.get(final_form, final_form)
    select_species(page, site_name, option_map)

    # Daifuku currently evaluates Lv.30/50/60/70; index 3 is Lv.70.
    page.eval_on_selector(
        "#levelSlider",
        "e => { e.value=3; e.dispatchEvent(new Event('input',{bubbles:true})); "
        "e.dispatchEvent(new Event('change',{bubbles:true})); }",
    )

    food_ids = row["ingredient_ids"].split("/")
    if len(food_ids) != 3:
        raise ValueError(f"食材ID不完整: {row['ingredient_ids']}")
    if final_form in {"ミュウ", "ダークライ"}:
        # Their provisional option list is populated by a slower site branch.
        page.wait_for_timeout(1000)
    food_fallback = False
    for index, food_id in enumerate(food_ids, 1):
        selector = f'[name="pokemon_ingredient{index}"]'
        available = page.eval_on_selector(
            selector, "e => Array.from(e.options, o => o.value).filter(Boolean)"
        )
        chosen = food_id
        if food_id not in available:
            if final_form not in {"ミュウ", "ダークライ"} or not available:
                raise ValueError(f"大福不支持食材ID: {food_id}")
            # Daifuku explicitly lists these two as provisional skill-type
            # entries and offers only placeholder foods. Their IV metric is
            # skill activation, so use the site's first supported placeholder.
            chosen = available[0]
            food_fallback = True
        page.select_option(selector, value=chosen)

    for index in range(1, 5):
        name = row.get(f"subskill{index}", "")
        value = mappings["subskill_id"].get(name, "")
        page.select_option(f'[name="pokemon_subskill{index}"]', value=value)
    nature_id = mappings["nature_id"].get(row["nature"])
    if not nature_id:
        raise ValueError(f"大福无此性格: {row['nature']}")
    page.select_option('[name="pokemon_personality"]', value=nature_id)

    # User-requested upper-limit convention: main skill is exactly Lv.5.
    set_radio(page, "mainskill_level", 5)
    set_radio(page, "num_evolved", evolution_count(final_form, mappings["evolution"]))

    before = result_rows(page)
    # Ads occasionally cover the visible button; dispatching the native click
    # keeps the form semantics without depending on screen hit-testing.
    page.eval_on_selector("button.submitButton", "e => e.click()")
    rows = []
    for _ in range(40):
        page.wait_for_timeout(250)
        rows = result_rows(page)
        if rows != before:
            break
    before_counts = Counter(tuple(cells) for cells in before)
    added = []
    for cells in rows:
        key = tuple(cells)
        if before_counts[key]:
            before_counts[key] -= 1
        else:
            added.append(cells)
    matching = [cells for cells in added if cells[0] == site_name]
    if not matching and rows == before:
        # An exact duplicate is not appended by Daifuku. Reuse it only when a
        # row for the requested species already exists.
        matching = [cells for cells in before if cells[0] == site_name]
    if not matching:
        raise TimeoutError("大福未返回结果")

    cells = matching[-1]
    match = re.search(r"([^：:]+)[：:]\s*([0-9.]+)%", cells[2])
    if not match:
        raise ValueError(f"无法解析大福评价: {cells[2]}")
    result = {
        "status": "OK",
        "site_name": site_name,
        "level": cells[1],
        "rank": match.group(1).strip(),
        "pct": match.group(2),
        "tokui": cells[3],
        "evaluation": cells[2],
        "evolution_count": evolution_count(final_form, mappings["evolution"]),
    }
    if food_fallback:
        result["note"] = "大福将该特殊物种标为技能型暂定数据，食材使用网站占位选项"
    return result


def submit_one(page, row, mappings, option_map):
    final_form = row["final_form"]
    if final_form != "イーブイ":
        return submit_form(page, row, mappings, option_map, final_form)

    branches = [
        submit_form(page, row, mappings, option_map, branch)
        for branch in EEVEE_EVOLUTIONS
    ]
    best = max(
        branches,
        key=lambda item: (RANK_ORDER.get(item.get("rank"), 0), float(item.get("pct") or 0)),
    )
    result = dict(best)
    result["branches"] = branches
    result["best_branch"] = best["site_name"]
    return result


def write_comparison(box_rows, local_rows, progress):
    extra = [
        "大福状态", "大福形态", "大福等级", "大福评级", "大福百分比",
        "大福得意分类", "大福进化次数", "本地与大福评级一致", "本地减大福百分点",
        "大福伊布最优分支", "大福伊布各分支", "大福备注", "大福错误",
    ]
    with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(local_rows[0].keys()) + extra)
        writer.writeheader()
        for box, local in zip(box_rows, local_rows):
            result = progress.get(box["folder"], {}).get("result", {})
            merged = dict(local)
            rank_column = next((key for key in local if key.startswith("个体值评级(")), "")
            local_rank = local.get(rank_column, "")
            local_pct = local.get("百分比", "")
            daifuku_pct = result.get("pct", "")
            delta = ""
            if local_pct and daifuku_pct:
                delta = f"{float(local_pct) - float(daifuku_pct):.2f}"
            merged.update({
                "大福状态": result.get("status", "未运行"),
                "大福形态": result.get("site_name", ""),
                "大福等级": result.get("level", ""),
                "大福评级": result.get("rank", ""),
                "大福百分比": daifuku_pct,
                "大福得意分类": result.get("tokui", ""),
                "大福进化次数": result.get("evolution_count", ""),
                "本地与大福评级一致": "是" if local_rank and local_rank == result.get("rank") else "否",
                "本地减大福百分点": delta,
                "大福伊布最优分支": result.get("best_branch", ""),
                "大福伊布各分支": " / ".join(
                    f"{item.get('site_name')}:{item.get('rank')} {item.get('pct')}%"
                    for item in result.get("branches", [])
                ),
                "大福备注": result.get("note", ""),
                "大福错误": result.get("error", ""),
            })
            writer.writerow(merged)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only process this many uncached rows")
    args = parser.parse_args()
    with open(INPUT, encoding="utf-8-sig") as handle:
        box_rows = list(csv.DictReader(handle))
    with open(LOCAL_RESULT, encoding="utf-8-sig") as handle:
        local_rows = list(csv.DictReader(handle))
    if len(box_rows) != len(local_rows):
        raise ValueError("OCR与本地评分行数不一致")

    mappings = extract.load_mappings()
    progress = load_progress()
    terminal_statuses = {"OK", "OCR字段不完整"}
    todo = [
        row for row in box_rows
        if progress.get(row["folder"], {}).get("fingerprint") != fingerprint(row)
        or progress.get(row["folder"], {}).get("result", {}).get("status") not in terminal_statuses
    ]
    uncached_count = len(todo)
    if args.limit is not None:
        todo = todo[:args.limit]
    print(
        f"Daifuku: rows={len(box_rows)}, cached={len(box_rows)-uncached_count}, "
        f"remaining={uncached_count}, this_run={len(todo)}",
        flush=True,
    )

    with sync_playwright() as playwright:
        launch_options = {"headless": True}
        if PROXY:
            launch_options["proxy"] = {"server": PROXY}
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.dismiss())

        def open_checker():
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_selector("#pokemonNameSelect", timeout=20000)
            page.wait_for_timeout(1200)
            options = page.eval_on_selector_all(
                "#pokemonNameSelect option",
                "opts => opts.map(o => ({value:o.value, text:o.textContent.trim()}))",
            )
            return {item["text"].split(" | ", 1)[-1]: item["value"] for item in options if item["value"]}

        option_map = open_checker()
        for index, row in enumerate(todo, 1):
            if index > 1 and (index - 1) % 40 == 0:
                option_map = open_checker()
            result = None
            for attempt in range(2):
                try:
                    result = submit_one(page, row, mappings, option_map)
                    break
                except Exception as exc:
                    if attempt == 0:
                        option_map = open_checker()
                        continue
                    result = {"status": "ERROR", "error": str(exc)}
            progress[row["folder"]] = {"fingerprint": fingerprint(row), "result": result}
            save_progress(progress)
            print(
                f"[{index}/{len(todo)}] {row.get('final_form') or '?'} -> "
                f"{result.get('rank', result.get('status'))} {result.get('pct', '')}",
                flush=True,
            )
            time.sleep(0.35)
        browser.close()

    write_comparison(box_rows, local_rows, progress)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
