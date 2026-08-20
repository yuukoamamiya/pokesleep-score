"""Local 期待値 (expected value) calculator, ported from pokeSleepCalc
(https://github.com/bennyhe/pokeSleepCalc) src/utils/energy.js + helpcalc.js.

Computes one-day berry/food/skill energy for a Pokémon without touching the
daifuku website. No area bonus / right-berry multiplier (白板产量).
"""
import json
import math
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "score", "data")

_pokedex = None
_berry_energy = None
_food_energy = None
_skill_effects = None
_nature = None
_species_map = None
_food_id_to_name = None


def _load():
    global _pokedex, _berry_energy, _food_energy, _skill_effects, _nature, _species_map, _food_id_to_name
    if _pokedex is not None:
        return
    def j(name):
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    _pokedex = j("pokedex.json")
    _berry_energy = j("berryEnergy.json")
    _food_energy = j("foodEnergy.json")
    _skill_effects = j("skillEffects.json")
    _nature = j("nature.json")
    _species_map = j("species_map.json")["name_to_id"]
    # ingredient id -> jp name (mirror of build_ingredients.ING_ID_TO_NAME)
    _food_id_to_name = {
        1: "ふといながねぎ", 2: "あじわいキノコ", 3: "とくせんエッグ", 4: "ほっこりポテト",
        5: "とくせんリンゴ", 6: "げきからハーブ", 7: "マメミート", 8: "モーモーミルク",
        9: "あまいミツ", 10: "ピュアなオイル", 11: "あったかジンジャー", 12: "あんみんトマト",
        13: "リラックスカカオ", 14: "おいしいシッポ", 15: "ワカクサ大豆", 16: "ワカクサコーン",
        17: "めざましコーヒー", 18: "ずっしりカボチャ", 19: "つやつやアボカド",
    }


def food_name_to_id(name):
    _load()
    for i, n in _food_id_to_name.items():
        if n == name:
            return i
    return None


INGREDIENT_PATTERNS = ("AAA", "AAB", "AAC", "ABA", "ABB", "ABC")


def species_food_types(species_jp):
    """Return the species-defined ingredient IDs in A/B/C order."""
    _load()
    species_jp = normalize_species(species_jp)
    pid = _species_map.get(species_jp)
    entry = _pokedex.get(str(pid)) if pid is not None else None
    return list((entry or {}).get("food", {}).get("type", []))


def legal_ingredient_patterns(species_jp):
    """Return legal slot patterns for a regular two- or three-food species."""
    type_count = len(species_food_types(species_jp))
    if type_count == 2:
        return tuple(p for p in INGREDIENT_PATTERNS if "C" not in p)
    if type_count == 3:
        return INGREDIENT_PATTERNS
    # Mythical Pokémon use a separate random-food system, not A/B/C slots.
    return ()


def food_ids_for_pattern(species_jp, pattern):
    """Map AAA/ABB/etc. to concrete ingredient IDs for ``species_jp``."""
    pattern = str(pattern or "").strip().upper()
    legal = legal_ingredient_patterns(species_jp)
    if pattern not in legal:
        raise ValueError(f"ingredient pattern {pattern or '<empty>'} is invalid for {species_jp}")
    types = species_food_types(species_jp)
    return [types[ord(symbol) - ord("A")] for symbol in pattern]


# ---- subskill jp name -> pokeSleepCalc skill label ----
SUBSKILL_MAP = {
    "おてつだいスピードS": "hs",
    "おてつだいスピードM": "hm",
    "おてつだいボーナス": "hg",  # count separately (hg1..hg5)
    "食材確率アップS": "fs",
    "食材確率アップM": "fm",
    "スキル確率アップS": "ss",
    "スキル確率アップM": "sm",
    "スキルレベルアップS": "sls",
    "スキルレベルアップM": "slm",
    "最大所持数アップS": "cs",
    "最大所持数アップM": "cm",
    "最大所持数アップL": "cl",
    "きのみの数S": "berry",
    # 非产量子技能(活力/EXP/碎片等)不计入能量
    "げんき回復ボーナス": None,
    "ゆめのかけらボーナス": None,
    "リサーチEXPボーナス": None,
    "睡眠EXPボーナス": None,
}


# ---- nature jp name -> character label (from helpSpeed.characterOptions useNatures) ----
NATURE_MAP = {
    "さみしがり": "hup", "いじっぱり": "hupfdown", "やんちゃ": "hupsdown", "ゆうかん": "hup",
    "ずぶとい": "hdown", "わんぱく": "fdown", "のうてんき": "sdown", "のんき": "none",
    "ひかえめ": "hdownfup", "おっとり": "fup", "うっかりや": "fupsdown", "れいせい": "fup",
    "おだやか": "hdownsup", "おとなしい": "sup", "しんちょう": "supfdown", "なまいき": "sup",
    "おくびょう": "hdown", "せっかち": "none", "ようき": "fdown", "むじゃき": "sdown",
    "てれや": "none", "がんばりや": "none", "すなお": "none", "きまぐれ": "none", "まじめ": "none",
}


# Current game sub-skill unlock levels.  Keep this in one place so the
# expected-value and IV calculators cannot silently disagree about how many
# slots are active at a given evaluation level.
SUBSKILL_UNLOCK_LEVELS = (10, 25, 50, 70, 80)
EVALUATION_MAIN_SKILL_LEVEL = 5


def unlocked_subskill_count(level):
    """Return the number of active sub-skill slots at ``level``."""
    return sum(level >= unlock_level for unlock_level in SUBSKILL_UNLOCK_LEVELS)


def unlocked_subskills(subskills, level):
    """Return only the sub-skills that are active at ``level``."""
    return list(subskills or [])[:unlocked_subskill_count(level)]


def _skill_list(subskills, evolve_count):
    """subskills: list of jp subskill names (in slot order, up to 5).
    Returns the pokeSleepCalc skill label list (['none', ...]) and berry flag."""
    _load()
    skills = []
    has_berry = False
    hg_count = 0
    for name in subskills:
        label = SUBSKILL_MAP.get(name)
        if label is None:
            continue
        if label == "hg":
            hg_count += 1
        elif label == "berry":
            has_berry = True
        else:
            skills.append(label)
    if not skills:
        skills = ["none"]
    if hg_count:
        skills.append(f"hg{hg_count}")
    return skills, has_berry


def _get_nature_character(nature):
    if nature is None:
        return "none"
    return NATURE_MAP.get(nature, "none")


# ---- core calculations (transliterations of energy.js) ----
def _get_decimal_number(num, digits):
    factor = 10 ** digits
    return math.floor(num * factor + 1e-9) / factor


def get_new_help_speed(base_help_speed, level, skills, character):
    """helpers speed in seconds. skills: list of labels."""
    level_up = (level - 1) * 0.002
    basichelp = 0.0
    main_muti = 0.0
    if "hs" in skills:
        basichelp += 0.07
    if "hm" in skills:
        basichelp += 0.14
    if "hup" in character:
        main_muti = 0.1
    if "hdown" in character:
        main_muti = -0.075
    for i in range(1, 6):
        if f"hg{i}" in skills:
            basichelp += 0.05 * i
    if basichelp >= 0.35:
        basichelp = 0.35
    res = (math.floor((1 - main_muti) * (1 - basichelp) * (1 - level_up) * 10000) / 10000) * base_help_speed
    return math.floor(res)


def get_new_food_per(skills, character, food_per):
    basicfood = 0.0
    main_muti = 0.0
    if "fs" in skills:
        basicfood += 0.18
    if "fm" in skills:
        basicfood += 0.36
    if "fup" in character:
        main_muti = 0.2
    if "fdown" in character:
        main_muti = -0.2
    return math.floor(food_per * ((1 + basicfood) * (1 + main_muti)) * 1000) / 1000


def get_new_skill_per(skills, character, skill_per):
    main_skill_up = 1.0
    basic_skill = 0.0
    main_muti = 0.0
    if "ss" in skills:
        basic_skill += 0.18
    if "sm" in skills:
        basic_skill += 0.36
    if "sup" in character:
        main_muti = 0.2
    if "sdown" in character:
        main_muti = -0.2
    return math.floor(skill_per * ((1 + basic_skill) * (1 + main_muti)) * main_skill_up * 1000) / 1000


def get_new_maxcarry(skills, maxcarry):
    if "cs" in skills:
        maxcarry += 6
    if "cm" in skills:
        maxcarry += 12
    if "cl" in skills:
        maxcarry += 18
    return maxcarry


def get_new_skill_level(skills, evolve_count, base_skill_level=1):
    max_level = base_skill_level
    if "sls" in skills:
        max_level += 1
    if "slm" in skills:
        max_level += 2
    if evolve_count:
        max_level += evolve_count
    return max_level


def get_one_day_help_count(help_speed, food_per, skill_per, calc_time=86400):
    food_per = float(food_per or 0)
    skill_per = float(skill_per or 0)
    calc_time = int(calc_time or 86400)
    count = {
        "sum": math.floor(calc_time / (help_speed / 2.2)),
        "food": 0.0,
        "berry": 0.0,
        "skill": 0.0,
    }
    skill_count = _get_decimal_number(count["sum"] * (skill_per / 100), 1)
    count["skill"] = skill_count
    if skill_per > 0 and skill_count < 1:
        skill_count = 1
    food_count = _get_decimal_number(count["sum"] * (food_per / 100), 2)
    if food_per > 0 and food_count < 1:
        food_count = 1
    count["food"] = food_count
    count["berry"] = _get_decimal_number(count["sum"] - food_count, 2)
    return count


def _get_one_day_berry_energy(poke_item, poke_level, is_double_berry, area_bonus=0):
    poke_type = 2 if poke_item.get("pokeType") in (1, 4) else 1
    if is_double_berry:
        poke_type += 1
    berry_count = _get_decimal_number(poke_item["oneDayHelpCount"]["berry"] * poke_type, 1)
    energy_entry = _berry_energy[str(poke_item["berryType"])]["energy"][poke_level - 1]["energy"]
    res = berry_count * energy_entry
    berry_energy = math.floor(res * (1 + area_bonus / 100))
    return berry_count, berry_energy


def _get_one_day_food_energy(poke_item, use_food_ids, area_bonus=0):
    use_foods = list(use_food_ids)
    help_food = {"useFoods": list(use_foods), "count": [], "energy": [], "allEnergy": 0.0}
    food_count = poke_item.get("food", {}).get("count", {})
    for i, fid in enumerate(use_foods):
        default = food_count.get(str(fid), {}).get("num", [0, 0, 0])[i]
        c = _get_decimal_number(poke_item["oneDayHelpCount"]["food"] / len(use_foods) * default, 1)
        if c >= 100:
            c = math.floor(c)
        help_food["count"].append(c)
        e = c * _food_energy[str(fid)]
        help_food["energy"].append(e)
        help_food["allEnergy"] += e
    # merge same ingredient
    y = 0
    while y < len(help_food["useFoods"]):
        j = 0
        merged = False
        while j < len(help_food["useFoods"]):
            for k in range(j + 1, len(help_food["useFoods"])):
                if help_food["useFoods"][j] == help_food["useFoods"][k]:
                    c = _get_decimal_number(help_food["count"][j] + help_food["count"][k], 1)
                    if c >= 100:
                        c = math.floor(c)
                    help_food["count"][j] = c
                    del help_food["useFoods"][k]
                    del help_food["count"][k]
                    merged = True
                    break
            if merged:
                break
            j += 1
        y += 1
    if area_bonus > 0:
        help_food["allEnergy"] = sum(e * (1 + area_bonus / 100) for e in help_food["energy"])
    help_food["allEnergy"] = math.floor(help_food["allEnergy"])
    return help_food


def _get_one_day_skill_effects(poke_item, poke_level, area_bonus=0):
    can_calc = [1, 2, 5, 3, 6, 23, 17, 21, 24, 25, 28, 35, 36]
    skill_count = poke_item.get("oneDayHelpCount", {}).get("skill", 0)
    skill_type = int(poke_item.get("skillType") or 0)
    skill_level = int(poke_item.get("skilllevel") or 1)
    res_type = "energy"
    if skill_type in (3, 6, 36):
        res_type = "shards"
    elif skill_type in (17, 21, 35):
        res_type = "berrys"
    elif skill_type in (24, 25, 28):
        res_type = "foods"
    se = _skill_effects.get(str(skill_type))
    if not skill_count or skill_type not in can_calc or not se:
        return {}
    effects = se.get("effects", [])
    if skill_level - 1 >= len(effects):
        return {}
    cur_val = effects[skill_level - 1].get("value")
    skill_once_energy = 0.0
    extra = {}
    if skill_type in (1, 2, 5, 3, 6, 23, 36):
        if isinstance(cur_val, list):
            skill_once_energy = sum(cur_val) / len(cur_val)
        else:
            skill_once_energy = cur_val
    elif skill_type in (17, 21, 35):
        berry_count = _get_decimal_number(cur_val * skill_count, 1)
        res = berry_count * _berry_energy[str(poke_item["berryType"])]["energy"][poke_level - 1]["energy"]
        skill_once_energy = res
        extra["berrys"] = [{"berryType": poke_item["berryType"], "berryCount": berry_count}]
    elif skill_type in (24, 25, 28):
        food_list = None
        if skill_type == 28 and poke_item.get("skillFood"):
            food_list = [{"foodtype": t, "percent": se.get("foodPercent", 0)} for t in poke_item["skillFood"]]
        else:
            food_list = se.get("foodTypes", [])
        foods = []
        for food_item in food_list:
            food_count = _get_decimal_number(cur_val * food_item.get("percent", 0) * skill_count, 1)
            if skill_type == 25:
                food_count = _get_decimal_number(
                    cur_val * food_item.get("percent", 0) * skill_count +
                    cur_val * 2 * food_item.get("morePercent", 0) * skill_count, 1)
            skill_once_energy += food_count * _food_energy[str(food_item["foodtype"])]
            foods.append({"foodType": food_item["foodtype"], "foodCount": food_count})
        extra["foods"] = foods
    energy = skill_count * skill_once_energy
    if skill_type in (17, 21, 28):
        energy = skill_once_energy
    if skill_type in (1, 2, 5, 23, 17, 21, 28) and area_bonus:
        energy = energy * (1 + area_bonus / 100)
    return {"type": res_type, "value": math.floor(energy), "extra": extra}


# 形态名归一化: daifuku 用全角括号形态名(如 ストリンダー（ハイなすがた）),
# 映射回 species_map 里的基础名
FORM_NORMALIZE = {
    "ストリンダー（ハイなすがた）": "ストリンダー",
    "ストリンダー（ローなすがた）": "ストリンダー(ロー)",
}


def normalize_species(name):
    if name is None:
        return None
    return FORM_NORMALIZE.get(name, name)


def compute_expected(species_jp, level, subskills, nature, main_skill_lv=1, evolve_count=0,
                     use_food_ids=None, area_bonus=0, is_double_berry=False,
                     main_skill_level_is_final=False):
    """Compute one-day expected values for a Pokémon.
    species_jp: 日文最终形态名. subskills: list of jp subskill names (slot order).
    use_food_ids: optional explicit ingredient ids [A,B,C]; default from pokedex A/B/C.
    Returns dict {berry_energy, food_energy, total_energy, food_count, help_count, food_ids}.
    """
    _load()
    species_jp = normalize_species(species_jp)
    pid = _species_map.get(species_jp)
    if pid is None:
        return {"error": f"species {species_jp} not in map"}
    entry = _pokedex.get(str(pid))
    if entry is None:
        return {"error": f"pokedex #{pid} missing"}
    if not isinstance(level, int) or level < 1:
        return {"error": f"invalid level {level}"}
    max_level = len(_berry_energy[str(entry["berryType"])]["energy"])
    if level > max_level:
        return {"error": f"level {level} exceeds data max {max_level}"}

    poke = dict(entry)
    active_subskills = unlocked_subskills(subskills, level)
    skills, has_berry = _skill_list(active_subskills, evolve_count)
    character = _get_nature_character(nature)
    poke["helpSpeed"] = get_new_help_speed(poke["helpSpeed"], level, skills, character)
    poke["foodPer"] = get_new_food_per(skills, character, poke.get("foodPer", 0))
    poke["skillPer"] = get_new_skill_per(skills, character, poke.get("skillPer", 0))
    poke["maxcarry"] = get_new_maxcarry(skills, poke.get("maxcarry", 0))
    if main_skill_level_is_final:
        poke["skilllevel"] = max(1, int(main_skill_lv or 1))
    else:
        poke["skilllevel"] = get_new_skill_level(skills, evolve_count, main_skill_lv)
    skill_effect = _skill_effects.get(str(poke.get("skillType") or 0), {})
    effect_count = len(skill_effect.get("effects", []))
    if effect_count:
        poke["skilllevel"] = min(poke["skilllevel"], effect_count)
    poke["oneDayHelpCount"] = get_one_day_help_count(poke["helpSpeed"], poke["foodPer"], poke["skillPer"])

    # ingredients
    if use_food_ids is not None and len(use_food_ids) >= 1:
        food_ids = list(use_food_ids)[:3]
        if len(food_ids) < 3:
            food_ids += [food_ids[0]] * (3 - len(food_ids))
    else:
        ftype = poke.get("food", {}).get("type", [])
        if len(ftype) >= 3:
            food_ids = ftype[:3]
        elif len(ftype) == 2:
            food_ids = [ftype[0], ftype[1], ftype[0]]
        elif ftype:
            food_ids = (ftype + [ftype[0]] * 3)[:3]
        else:
            return {"error": f"species {species_jp} has no ingredient data"}
    poke["useFoods"] = food_ids

    if level < 30:
        food_ids_use = food_ids[:1]
    elif level < 60:
        food_ids_use = food_ids[:2]
    else:
        food_ids_use = food_ids

    berry_count, berry_energy = _get_one_day_berry_energy(poke, level, is_double_berry, area_bonus)
    food_energy = _get_one_day_food_energy(poke, food_ids_use, area_bonus)
    skill_effects = _get_one_day_skill_effects(poke, level, area_bonus)
    total = berry_energy + food_energy["allEnergy"]
    if skill_effects and skill_effects.get("type") in ("energy", "berrys", "foods"):
        total += skill_effects.get("value", 0)

    return {
        "berry_energy": berry_energy,
        "berry_count": berry_count,
        "food_energy": food_energy["allEnergy"],
        "food_count": sum(food_energy["count"]),
        "food_ids": food_ids_use,
        "total_energy": total,
        "skill_energy": skill_effects.get("value", 0) if skill_effects else 0,
        "help_count": poke["oneDayHelpCount"],
    }


if __name__ == "__main__":
    import sys
    _load()
    # quick smoke test
    r = compute_expected("カメックス", 60, [], None)
    print(r)
