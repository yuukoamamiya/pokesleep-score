import csv
import cv2
import difflib
import json
import numpy as np
import os
import re
import subprocess
import sys
import unicodedata

from project_config import PROJECT_ROOT, CAP_DIR, OCR_CSV

BASE = str(PROJECT_ROOT)
CAP = str(CAP_DIR)
VENV = os.path.join(BASE, ".venv", "Scripts", "python.exe")
OUT = str(OCR_CSV)

sys.path.insert(0, os.path.join(BASE, "score"))
from ocr import ocr as ocr_engine  # noqa: E402 (in-process OCR, model loaded once)
from local_expected import species_food_types  # noqa: E402


FOOD_ICON_DIR = os.path.join(BASE, "score", "data", "food_icons")
PORTRAIT_DIR = os.path.join(BASE, "score", "data", "portraits")
FOOD_SLOT_ROIS = (
    # The detail page can settle at different vertical offsets after the same
    # gesture (notably after the first visit). Search the full ability panel
    # height while keeping each ingredient column isolated.
    (440, 250, 620, 1050),
    (620, 250, 800, 1050),
    (800, 250, 1010, 1050),
)
_FOOD_ICON_CACHE = {}
_PORTRAIT_CACHE = {}

FORM_CANDIDATES = {
    "ピカチュウ": (
        (25, "ピカチュウ"),
        (9001, "ピカチュウ(ハロウィン)"),
        (9002, "ピカチュウ(ホリデー)"),
        (9007, "ピカチュウ(船長)"),
    ),
    "イーブイ": (
        (133, "イーブイ"),
        (9004, "イーブイ(ホリデー)"),
        (9005, "イーブイ(ハロウィン)"),
    ),
    "タマザラシ": (
        (363, "タマザラシ"),
        (9006, "タマザラシ(花輪)"),
    ),
}


def normalize(s):
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("ー", "-").replace("〜", "-").replace("~", "-")
    s = re.sub(r"[\s.．・\s]+", "", s)
    s = s.lower()
    return s


def close_match(text, candidates, cutoff=0.72):
    nt = normalize(text)
    if not nt:
        return None
    for c in candidates:
        if normalize(c) == nt:
            return c
    best = difflib.get_close_matches(nt, [normalize(c) for c in candidates], n=1, cutoff=cutoff)
    if best:
        idx = [normalize(c) for c in candidates].index(best[0])
        return candidates[idx]
    return None


UI_BLACKLIST = {
    "レベルアップ", "最大所持数", "おてつだい時間", "おてつだい能力", "詳細ステータス",
    "出会った日", "出会ったフィールド", "一緒に眠った時間", "げんき", "食材", "樹果",
    "リボン", "タイプ", "せいかく", "メインスキル", "サブスキル", "スキル",
    "とくいなもの", "お気に入り", "性別", "リーダー", "現在のチーム", "進化",
}


def match_subskill(text, candidates):
    nt = normalize(text)
    if not nt:
        return None
    if any(normalize(b) == nt for b in UI_BLACKLIST):
        return None
    # exact normalized match first
    for c in candidates:
        if normalize(c) == nt:
            return c
    best = difflib.get_close_matches(nt, [normalize(c) for c in candidates], n=1, cutoff=0.82)
    if best:
        idx = [normalize(c) for c in candidates].index(best[0])
        nc = normalize(candidates[idx])
        # reject prefix-only matches where candidate is much longer
        if len(nt) < len(nc) * 0.75 and nc.startswith(nt):
            return None
        return candidates[idx]
    return None


def load_mappings():
    data = json.load(open(os.path.join(BASE, "box-exporter", "pokemon_data.json"), encoding="utf-8"))
    pokedex = {v: k for k, v in data.get("pokedex_names", {}).items() if k != "_comment"}
    subskills = [v for k, v in data.get("subskill_names", {}).items() if k != "_comment"]
    natures = [v for k, v in data.get("nature_names", {}).items() if k != "_comment"]
    main_skills = [v for k, v in data.get("main_skill_names", {}).items() if k != "_comment"]
    # daifuku maps from index.html
    html = open(os.path.join(BASE, "box-exporter", "index.html"), encoding="utf-8").read()
    def extract_js_map(name):
        m = re.search(rf"const {name} = \{{(.*?)\}};", html, re.S)
        if not m:
            return {}
        out = {}
        for k, v in re.findall(r'"([^"]+)":"([^"]+)"', m.group(1)):
            out[k] = v
        return out
    subskill_id = extract_js_map("DAIFUKU_SUBSKILL_ID")
    nature_id = extract_js_map("DAIFUKU_NATURE_ID")
    evolution = extract_js_map("DAIFUKU_EVOLUTION_MAP")
    subskills = list(subskill_id.keys())
    return {
        "pokedex": pokedex, "subskills": subskills, "natures": natures,
        "main_skills": main_skills, "subskill_id": subskill_id,
        "nature_id": nature_id, "evolution": evolution,
    }


def ocr_img(path):
    items = []
    for it in ocr_engine(path):
        b = it["box"]
        items.append({"x0": int(b[0]), "y0": int(b[1]), "x1": int(b[2]), "y1": int(b[3]),
                      "text": it["text"]})
    return items


def _tesseract_text(image, psm=6):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        return ""
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", "jpn", "--psm", str(psm)],
        input=encoded.tobytes(), capture_output=True, check=False,
    )
    return result.stdout.decode("utf-8", errors="ignore")


def recognize_nature_fallback(image_path, natures):
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if image is None:
        return None
    # The nature text sits inside a rounded outline which RapidOCR sometimes
    # treats as decoration. Tesseract is reliable on this tight fixed region.
    text = _tesseract_text(image[930:1220, 100:540], psm=6)
    return close_match(text, natures, cutoff=0.55)


def recognize_slot5_berry_fallback(image_path):
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if image is None:
        return False
    text = normalize(_tesseract_text(image[570:760, 40:560], psm=6))
    return normalize("きのみの数S") in text


LV_RE = re.compile(r"[LlＬ][VＶv]?[\.．]?\s*(\d+)")
JA_RE = re.compile(r"[ぁ-んァ-ヶ一-龯]")


def _food_icon(food_id):
    if food_id not in _FOOD_ICON_CACHE:
        path = os.path.join(FOOD_ICON_DIR, f"{food_id}.png")
        icon = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if icon is None or icon.ndim != 3 or icon.shape[2] != 4:
            raise FileNotFoundError(f"food icon template missing or invalid: {path}")
        _FOOD_ICON_CACHE[food_id] = icon
    return _FOOD_ICON_CACHE[food_id]


def _portrait(pokemon_id):
    if pokemon_id not in _PORTRAIT_CACHE:
        path = os.path.join(PORTRAIT_DIR, f"{pokemon_id}.png")
        portrait = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if portrait is None or portrait.ndim != 3 or portrait.shape[2] != 4:
            raise FileNotFoundError(f"portrait template missing or invalid: {path}")
        _PORTRAIT_CACHE[pokemon_id] = portrait
    return _PORTRAIT_CACHE[pokemon_id]


def recognize_costume_form(image_path, species):
    """Distinguish costume forms whose detail-page name is the base species."""
    candidates = FORM_CANDIDATES.get(species)
    if not candidates:
        return {"species": species, "confidence": None, "margin": None, "error": None}
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if image is None:
        return {"species": species, "confidence": None, "margin": None,
                "error": "identity screenshot missing"}
    if image.shape[1] != 1080 or image.shape[0] != 1920:
        image = cv2.resize(image, (1080, 1920), interpolation=cv2.INTER_AREA)
    # The character artwork is centered in this stable identity-page region.
    roi = image[250:850, 220:860]
    roi_edges = cv2.Canny(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), 35, 110)
    scores = []
    for pokemon_id, form_name in candidates:
        raw = _portrait(pokemon_id)
        ys, xs = np.where(raw[:, :, 3] > 8)
        if len(xs) and len(ys):
            raw = raw[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        alpha = raw[:, :, 3:4].astype(np.float32) / 255.0
        on_white = (raw[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
        gray = cv2.cvtColor(on_white, cv2.COLOR_BGR2GRAY)
        best = -1.0
        for scale in np.linspace(0.35, 0.85, 21):
            width = max(16, round(raw.shape[1] * scale))
            height = max(16, round(raw.shape[0] * scale))
            if width > roi.shape[1] or height > roi.shape[0]:
                continue
            template = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
            template_edges = cv2.Canny(template, 35, 110)
            matched = cv2.matchTemplate(roi_edges, template_edges, cv2.TM_CCORR_NORMED)
            best = max(best, float(matched.max()))
        scores.append((best, form_name, pokemon_id))
    scores.sort(reverse=True)
    confidence, form_name, pokemon_id = scores[0]
    margin = confidence - scores[1][0]
    if confidence < 0.22 or margin < 0.02:
        return {"species": species, "confidence": confidence, "margin": margin,
                "best_species": form_name, "pokemon_id": pokemon_id,
                "error": f"costume match ambiguous: {form_name}/{scores[1][1]}"}
    return {"species": form_name, "pokemon_id": pokemon_id,
            "confidence": confidence, "margin": margin, "error": None}


def _match_food_icon(roi, candidate_ids):
    # Edge matching is intentionally used instead of color matching. Locked
    # Lv.30/Lv.60 slots are faded toward orange/white, which can make a pale
    # leek look more like meat in RGB while its silhouette remains stable.
    roi_edges = cv2.Canny(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), 30, 100)
    scores = []
    for food_id in candidate_ids:
        raw = _food_icon(food_id)
        alpha = raw[:, :, 3:4].astype(np.float32) / 255.0
        on_white = (raw[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
        gray = cv2.cvtColor(on_white, cv2.COLOR_BGR2GRAY)
        best = -1.0
        for scale in np.linspace(0.55, 1.05, 11):
            width = max(8, round(raw.shape[1] * scale))
            height = max(8, round(raw.shape[0] * scale))
            if width > roi.shape[1] or height > roi.shape[0]:
                continue
            template = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
            template_edges = cv2.Canny(template, 30, 100)
            matched = cv2.matchTemplate(roi_edges, template_edges, cv2.TM_CCORR_NORMED)
            best = max(best, float(matched.max()))
        scores.append((best, food_id))
    scores.sort(reverse=True)
    best_score, best_id = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0.0
    return best_id, best_score, best_score - second_score, {
        food_id: score for score, food_id in scores
    }


def recognize_ingredient_pattern(image_path, species):
    """Recognize the three ingredient icons from capture page 1.

    Candidate matching is restricted to the species-defined A/B/C foods. This
    also works for locked, faded slots and avoids confusing visually similar
    icons from unrelated species.
    """
    food_types = species_food_types(species)
    if len(food_types) < 2:
        return {"pattern": None, "error": "special ingredient system"}
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if image is None:
        return {"pattern": None, "error": "ingredient screenshot missing"}
    if image.shape[1] != 1080 or image.shape[0] != 1920:
        image = cv2.resize(image, (1080, 1920), interpolation=cv2.INTER_AREA)

    slot_scores = []
    for x0, y0, x1, y1 in FOOD_SLOT_ROIS:
        _, _, _, scores = _match_food_icon(image[y0:y1, x0:x1], food_types)
        slot_scores.append(scores)

    # Mythical Pokémon can draw each slot from a broad food pool rather than
    # the normal A/B/C table. Keep the concrete IDs for Daifuku submission.
    if len(food_types) > 3:
        matched_ids = [max(scores.items(), key=lambda item: item[1])[0]
                       for scores in slot_scores]
        confidences = [slot_scores[i][food_id]
                       for i, food_id in enumerate(matched_ids)]
        margins = []
        for scores in slot_scores:
            ranked_scores = sorted(scores.values(), reverse=True)
            margins.append(ranked_scores[0] - ranked_scores[1])
        return {
            "pattern": None, "ids": matched_ids,
            "confidence": min(confidences), "margin": min(margins),
            "error": "special ingredient system",
        }

    # Score complete legal A/B/C patterns rather than choosing each icon in
    # isolation.  This encodes the game's rules (slot 1 is always A; slots 2/3
    # have restricted choices) and is much more stable for faded locked icons.
    legal = ("AAA", "AAB", "ABA", "ABB") if len(food_types) == 2 else (
        "AAA", "AAB", "AAC", "ABA", "ABB", "ABC"
    )
    ranked = []
    for pattern in legal:
        ids = [food_types[ord(letter) - ord("A")] for letter in pattern]
        values = [slot_scores[i][food_id] for i, food_id in enumerate(ids)]
        ranked.append((sum(values) / len(values), min(values), pattern, ids))
    ranked.sort(reverse=True)
    total, confidence, pattern, matched_ids = ranked[0]
    margin = total - ranked[1][0]
    warning = None
    if confidence < 0.20 or margin < 0.010:
        warning = f"low-confidence legal match: {pattern}"
    return {
        "pattern": pattern, "ids": matched_ids,
        "confidence": confidence, "margin": margin, "error": warning,
    }


def parse_pokemon(folder, M):
    d = os.path.join(CAP, folder)
    all_items = []
    for i in range(4):
        p = os.path.join(d, f"{i}.png")
        if os.path.exists(p):
            page_items = ocr_img(p)
            for item in page_items:
                item["page"] = i
            all_items.extend(page_items)
    texts = [it["text"] for it in all_items]

    # species + level
    species = None
    level = None
    identity_items = [item for item in all_items if item.get("page") == 0]
    level_items = [item for item in identity_items if LV_RE.search(item["text"])]
    if level_items:
        # The topmost level on page 0 belongs to the Pokémon identity card;
        # later levels are ingredient/subskill unlock labels.
        identity_level = min(level_items, key=lambda item: item["y0"])
        level = int(LV_RE.search(identity_level["text"]).group(1))
        # OCR occasionally reads the small punctuation after a level as a
        # trailing "1" (Lv.20! -> 201, Lv.14! -> 141).
        if level > 80 and level % 10 == 1 and level // 10 <= 80:
            level //= 10
    for item in identity_items:
        t = item["text"]
        m = LV_RE.search(t)
        if m:
            rest = re.sub(r"[LlＬ][VＶv]?[\.．]?\s*\d+\s*[ー\-]?\s*", "", t)
            cand = close_match(rest, list(M["pokedex"].keys()))
            if cand:
                species = cand
                break
    if species is None:
        # try matching any full text against species list
        for t in [item["text"] for item in identity_items]:
            if len(t) >= 2:
                cand = close_match(t, list(M["pokedex"].keys()), cutoff=0.78)
                if cand:
                    species = cand
                    break

    # nature
    nature = None
    for i, it in enumerate(all_items):
        if normalize(it["text"]) == normalize("せいかく"):
            below = [x for x in all_items if it["y0"] < x["y0"] < it["y0"] + 220 and abs(x["x0"] - it["x0"]) < 320]
            for b in sorted(below, key=lambda x: x["y0"]):
                cand = close_match(b["text"], M["natures"])
                if cand:
                    nature = cand
                    break
            if nature:
                break
    if nature is None:
        nature = recognize_nature_fallback(os.path.join(d, "3.png"), M["natures"])

    # main skill + level: locate a valid Lv.1-Lv.7 marker at the right edge of
    # a main-skill card, then read the label on the same page and row.
    main_skill = None
    main_skill_lv = None
    for marker in all_items:
        match = LV_RE.search(marker["text"])
        if not match or marker["x0"] < 700 or not 1 <= int(match.group(1)) <= 7:
            continue
        labels = [item for item in all_items
                  if item.get("page") == marker.get("page")
                  and item["x0"] < 700
                  and abs(item["y0"] - marker["y0"]) < 55
                  and JA_RE.search(item["text"])]
        if not labels:
            continue
        label = min(labels, key=lambda item: abs(item["y0"] - marker["y0"]))["text"]
        main_skill = close_match(label, M["main_skills"], cutoff=0.72) or label.strip()
        main_skill_lv = int(match.group(1))
        break

    # subskills in slot order (two-column layout: rows of [left, right], left=odd slot, right=even slot)
    found = []
    for it in all_items:
        cand = match_subskill(it["text"], M["subskills"])
        if cand:
            found.append({"y": it["y0"], "x": it["x0"], "name": cand})
    subskills = []
    if found:
        found.sort(key=lambda f: (f["y"], f["x"]))
        rows = []
        for f in found:
            placed = False
            for r in rows:
                if abs(r[0]["y"] - f["y"]) < 40:
                    r.append(f)
                    placed = True
                    break
            if not placed:
                rows.append([f])
        rows.sort(key=lambda r: r[0]["y"])
        seen = set()
        for r in rows:
            r.sort(key=lambda f: f["x"])
            for f in r:
                if f["name"] not in seen:
                    seen.add(f["name"])
                    subskills.append(f["name"])
        subskills = subskills[:5]
    if len(subskills) == 4 and recognize_slot5_berry_fallback(os.path.join(d, "3.png")):
        subskills.append("きのみの数S")

    base_species = species
    form = {"species": species, "confidence": None, "margin": None, "error": None}
    form_method = "name"
    identity_image = os.path.join(d, "0.png")
    if species and os.path.exists(identity_image):
        form = recognize_costume_form(identity_image, species)
        visual_species = form.get("species") or species
        best_visual_species = form.get("best_species") or visual_species
        if base_species == "ピカチュウ":
            if main_skill and "食材ゲット" in main_skill:
                species, form_method = "ピカチュウ(船長)", "main_skill"
            elif main_skill and "ゆめのかけら" in main_skill:
                species, form_method = "ピカチュウ(ホリデー)", "main_skill"
            elif best_visual_species == "ピカチュウ(ハロウィン)":
                species, form_method = best_visual_species, "portrait"
            else:
                species, form_method = "ピカチュウ", "portrait"
        elif base_species == "タマザラシ":
            if main_skill and "料理チャンス" in main_skill:
                species, form_method = "タマザラシ(花輪)", "main_skill"
            else:
                species, form_method = "タマザラシ", "main_skill"
        elif base_species == "イーブイ":
            if main_skill and "ゆめのかけら" in main_skill:
                species, form_method = "イーブイ(ホリデー)", "main_skill"
            else:
                species, form_method = "イーブイ", "ingredient_pending"
        else:
            species, form_method = visual_species, "portrait"

    # final form
    final_form = M["evolution"].get(species, species)
    ingredient = {"pattern": None, "ids": [], "confidence": None, "margin": None, "error": None}
    ingredient_image = os.path.join(d, "1.png")
    if species and os.path.exists(ingredient_image):
        ingredient = recognize_ingredient_pattern(ingredient_image, species)
    if base_species == "イーブイ" and os.path.exists(ingredient_image):
        ingredient_image_data = cv2.imread(ingredient_image, cv2.IMREAD_COLOR)
        if ingredient_image_data is not None:
            if ingredient_image_data.shape[:2] != (1920, 1080):
                ingredient_image_data = cv2.resize(ingredient_image_data, (1080, 1920), interpolation=cv2.INTER_AREA)
            x0, y0, x1, y1 = FOOD_SLOT_ROIS[0]
            first_id, first_confidence, first_margin = _match_food_icon(
                ingredient_image_data[y0:y1, x0:x1], (8, 18)
            )
            if first_id == 18 and first_confidence >= 0.25 and first_margin >= 0.025:
                species, form_method = "イーブイ(ハロウィン)", "first_ingredient"
                ingredient = recognize_ingredient_pattern(ingredient_image, species)
            elif species != "イーブイ(ホリデー)":
                species, form_method = "イーブイ", "first_ingredient"
            final_form = M["evolution"].get(species, species)
    return {
        "folder": folder,
        "base_species": base_species,
        "species": species,
        "level": level,
        "final_form": final_form,
        "main_skill": main_skill,
        "main_skill_lv": main_skill_lv,
        "subskills": subskills,
        "nature": nature,
        "ingredient_pattern": ingredient.get("pattern"),
        "ingredient_ids": "/".join(str(v) for v in ingredient.get("ids") or []),
        "ingredient_confidence": ingredient.get("confidence"),
        "ingredient_margin": ingredient.get("margin"),
        "ingredient_error": ingredient.get("error"),
        "form_confidence": form.get("confidence"),
        "form_margin": form.get("margin"),
        "form_error": form.get("error"),
        "form_method": form_method,
    }


def main():
    M = load_mappings()
    folders = sorted([d for d in os.listdir(CAP) if os.path.isdir(os.path.join(CAP, d))])
    rows = []
    for f in folders:
        try:
            p = parse_pokemon(f, M)
        except Exception as e:
            p = {"folder": f, "error": str(e)}
        rows.append(p)
        print(f"{f}: {p.get('species')} Lv.{p.get('level')} [{','.join(p.get('subskills',[]))}] {p.get('nature')} "
              f"ms={p.get('main_skill')}lv{p.get('main_skill_lv')} food={p.get('ingredient_pattern') or p.get('ingredient_error')} "
              f"-> {p.get('final_form')}", flush=True)

    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["folder", "base_species", "species", "level", "final_form", "main_skill", "main_skill_lv",
                    "subskill1", "subskill2", "subskill3", "subskill4", "subskill5", "nature",
                    "ingredient_pattern", "ingredient_ids", "ingredient_confidence", "ingredient_margin",
                    "ingredient_error", "form_confidence", "form_margin", "form_error", "form_method"])
        for r in rows:
            subs = (r.get("subskills") or []) + [""] * 5
            subs = subs[:5]
            w.writerow([r.get("folder", ""), r.get("base_species", ""), r.get("species", ""), r.get("level", ""),
                        r.get("final_form", ""), r.get("main_skill", ""), r.get("main_skill_lv", ""),
                        subs[0], subs[1], subs[2], subs[3], subs[4], r.get("nature", ""),
                        r.get("ingredient_pattern", ""), r.get("ingredient_ids", ""),
                        r.get("ingredient_confidence", ""), r.get("ingredient_margin", ""),
                        r.get("ingredient_error", ""), r.get("form_confidence", ""),
                        r.get("form_margin", ""), r.get("form_error", ""), r.get("form_method", "")])
    print(f"\nWrote {OUT} with {len(rows)} unique rows")


if __name__ == "__main__":
    main()
