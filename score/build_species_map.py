"""Build score/data/species_map.json: 日文物种名 -> pokeSleepCalc pokedex id.
Uses box-exporter/pokemon_data.json (pokedex_names 图鉴号->日文名) + EXTRA_NAME_NO fallback."""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXTRA_NAME_NO = {
    "エンペルト": 395, "ゴウカザル": 392, "ドダイトス": 389, "ハルクジラ": 974,
    "マスカーニャ": 908, "ウェーニバル": 914, "ラウドボーン": 911, "パーモット": 923,
    "ストリンダー": 849, "パンプジン": 711, "ニンフィア": 700, "デカグース": 735,
}

def main():
    be = json.load(open(os.path.join(BASE, "box-exporter", "pokemon_data.json"), encoding="utf-8"))
    pokedex_names = be["pokedex_names"]
    name2no = {v: k for k, v in pokedex_names.items() if k != "_comment"}
    name2no.update(EXTRA_NAME_NO)

    pokedex = json.load(open(os.path.join(BASE, "score", "data", "pokedex.json"), encoding="utf-8"))
    out = {}
    missing = []
    for sp, no in name2no.items():
        if str(no) in pokedex:
            out[sp] = int(no)
        else:
            missing.append((sp, no))
    # also record all pokeSleepCalc ids for reference
    out_json = {"name_to_id": out, "missing": missing}
    dst = os.path.join(BASE, "score", "data", "species_map.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out_json, f, ensure_ascii=False, indent=1)
    print(f"name_to_id: {len(out)} species; missing {len(missing)}")
    for m in missing:
        print("  missing:", m)
    print("wrote", dst)

if __name__ == "__main__":
    main()
