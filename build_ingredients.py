import csv
import json
import os
import re

from project_config import PROJECT_ROOT, WORKSPACE_ROOT, OCR_CSV

BASE = str(PROJECT_ROOT)

ING_ID_TO_NAME = {
    1: "ふといながねぎ", 2: "あじわいキノコ", 3: "とくせんエッグ", 4: "ほっこりポテト",
    5: "とくせんリンゴ", 6: "げきからハーブ", 7: "マメミート", 8: "モーモーミルク",
    9: "あまいミツ", 10: "ピュアなオイル", 11: "あったかジンジャー", 12: "あんみんトマト",
    13: "リラックスカカオ", 14: "おいしいシッポ", 15: "ワカクサ大豆", 16: "ワカクサコーン",
    17: "めざましコーヒー", 18: "ずっしりカボチャ", 19: "つやつやアボカド",
}

EXTRA_NAME_NO = {
    "エンペルト": 395, "ゴウカザル": 392, "ドダイトス": 389, "ハルクジラ": 974,
    "マスカーニャ": 908, "ウェーニバル": 914, "ラウドボーン": 911, "パーモット": 923,
    "ストリンダー": 849, "パンプジン": 711, "ニンフィア": 700, "デカグース": 735,
}


def parse_pokedex(path):
    data = open(path, encoding="utf-8").read()
    blocks = list(re.finditer(r"\n\s*id: (\d+),", data))
    species_food = {}   # id -> {"A": id, "B": id, "C": id or None, "special": bool}
    for i in range(len(blocks)):
        e = blocks[i + 1].start() if i + 1 < len(blocks) else len(data)
        seg = data[blocks[i].start():e]
        i0 = seg.find("food:")
        if i0 < 0:
            continue
        fm = re.search(r"type: \[([\d, ]+)\]", seg[i0:])
        if not fm:
            continue
        ids = [int(x) for x in fm.group(1).split(",")]
        nums = {}
        for cm in re.finditer(r"(\d+): \{ num: \[([\d, ]+)\]", seg[i0:]):
            nums[int(cm.group(1))] = [int(x) for x in cm.group(2).split(",")]
        if len(ids) == 3:
            species_food[int(blocks[i].group(1))] = {"A": ids[0], "B": ids[1], "C": ids[2]}
        elif len(ids) == 2:
            # determine A/B by first-nonzero num; C slot unknown
            a = b = None
            for ing in ids:
                n = nums.get(ing, [0, 0, 0])
                if n[0] > 0:
                    a = ing
                elif n[0] == 0 and n[1] > 0:
                    b = ing
            if a is not None and b is not None:
                species_food[int(blocks[i].group(1))] = {"A": a, "B": b, "C": None}
            else:
                species_food[int(blocks[i].group(1))] = {"A": ids[0], "B": ids[1], "C": None}
        else:
            species_food[int(blocks[i].group(1))] = {"A": None, "B": None, "C": None, "special": True}

    s = data.find("const evoLine = [")
    e = data.find("];", s)
    lines = []
    for ln in data[s + len("const evoLine = ["):e].split("],"):
        mem = []
        for x in ln.replace("[", "").replace("]", "").split(","):
            x = x.strip().strip("'")
            if x.isdigit():
                mem.append(int(x))
        if mem:
            lines.append(mem)
    return species_food, lines


def resolve(sid, species_food, lines):
    if sid in species_food:
        return species_food[sid]
    for ln in lines:
        if sid in ln:
            for m in ln:
                if m in species_food:
                    return species_food[m]
    return None


def main():
    species_food, lines = parse_pokedex(os.path.join(BASE, "data_src", "pokedex.js"))

    ocr = []
    with open(OCR_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ocr.append(r)
    box = sorted({r["final_form"] for r in ocr if r.get("final_form")})

    pd = json.load(open(os.path.join(BASE, "box-exporter", "pokemon_data.json"), encoding="utf-8"))["pokedex_names"]
    name_to_no = {v: k for k, v in pd.items() if k != "_comment"}
    name_to_no.update(EXTRA_NAME_NO)

    out = {}
    need_pattern = []
    missing = []
    for sp in box:
        no = name_to_no.get(sp)
        if no is None:
            missing.append((sp, "无图鉴号"))
            continue
        food = resolve(int(no), species_food, lines)
        if food is None:
            missing.append((sp, f"#{no} 无食材数据"))
            continue
        if food.get("special"):
            missing.append((sp, "特殊(梦幻/达克莱伊)"))
            continue
        a, b, c = food["A"], food["B"], food["C"]
        if a is None or b is None:
            missing.append((sp, f"#{no} 无法解析"))
            continue
        if c is None:
            need_pattern.append((sp, a, b))
            out[sp] = [ING_ID_TO_NAME.get(a), ING_ID_TO_NAME.get(b), "?"]
        else:
            out[sp] = [ING_ID_TO_NAME.get(a), ING_ID_TO_NAME.get(b), ING_ID_TO_NAME.get(c)]

    output_path = WORKSPACE_ROOT / "species_ingredients.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(output_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"写出 {len(out)} 个物种;需图标判模式 {len(need_pattern)};缺失/特殊 {len(missing)}")
    print("需图标判模式的物种:", [sp for sp, _, _ in need_pattern])
    for m in missing:
        print("  缺失/特殊:", m)
    for sp in ["イーブイ", "ブラッキー", "カメックス", "ジュカイン", "ライチュウ"]:
        print(f"  {sp}: {out.get(sp)}")


if __name__ == "__main__":
    main()
