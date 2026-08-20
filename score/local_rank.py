"""Local 個体値 rating: enumerate possible subskills, natures and ingredient
patterns, take the best specialty output as the 100% baseline, then rate an
individual against the configured Lv70 tables.

Fully local — no daifuku website involved.
"""
import itertools
import hashlib
import json
import os
from pathlib import Path

from local_expected import (
    compute_expected,
    normalize_species,
    unlocked_subskill_count,
    EVALUATION_MAIN_SKILL_LEVEL,
    food_ids_for_pattern,
    legal_ingredient_patterns,
    species_food_types,
    food_name_to_id,
    _load,
    NATURE_MAP,
    SUBSKILL_MAP,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "score", "data")
WORKSPACE = Path(os.environ.get("POKESLEEP_WORKSPACE", Path(BASE) / "workspace")).expanduser().resolve()
BASELINE_FILE = str(WORKSPACE / "cache" / "baseline.json")

# Sub-skills that can change the modeled Lv.70 ceiling.  Inventory skills are
# irrelevant to this continuous-collection model, and skill-level-up skills do
# not change output because every candidate is standardized at main skill Lv.5.
MODELED_SUBSKILL_LABELS = {"hs", "hm", "hg", "fs", "fm", "ss", "sm", "berry"}
PROD_SUBS = [s for s, label in SUBSKILL_MAP.items() if label in MODELED_SUBSKILL_LABELS]

BASELINE_SCHEMA_VERSION = 2
ALGORITHM_VERSION = "iv-specialty-v6-real-food-pattern"

# Species whose practical role differs from pokeSleepCalc's broad pokeType.
SPECIALTY_OVERRIDES = {
    "ジュカイン": "berry",
}

PREFERRED_FOOD_PATTERNS = {"AAA", "ABB"}
NON_PREFERRED_FOOD_MULTIPLIER = 0.70

# daifuku Lv70 分档表: (得意编号, 名称, [(増田下界, SS下界, S下界, A下界, B下界, C下界)])
RANK_TABLES = {
    # ①きのみ得意
    1: ("①きのみ得意", [95.0, 85.0, 72.0, 60.0, 45.0, 40.0]),
    # ②食材型きのみ得意
    2: ("②食材型きのみ得意", [105.0, 95.0, 82.0, 70.0, 55.0, 50.0]),
    # ③スキル型きのみ得意
    3: ("③スキル型きのみ得意", [105.0, 95.0, 82.0, 70.0, 55.0, 50.0]),
    # ④きのみ型食材得意
    4: ("④きのみ型食材得意", [92.0, 81.0, 65.0, 59.0, 54.0, 48.0]),
    # ⑤食材得意
    5: ("⑤食材得意", [84.0, 74.0, 60.0, 54.0, 50.0, 45.0]),
    # ⑥スキル型食材得意
    6: ("⑥スキル型食材得意", [92.0, 81.0, 65.0, 59.0, 54.0, 48.0]),
    # ⑦きのみ型スキル得意
    7: ("⑦きのみ型スキル得意", [92.4, 81.4, 66.0, 59.4, 55.0, 50.0]),
    # ⑧食材型スキル得意
    8: ("⑧食材型スキル得意", [84.0, 74.0, 60.0, 54.0, 50.0, 45.0]),
    # ⑨スキル得意
    9: ("⑨スキル得意", [84.0, 74.0, 60.0, 54.0, 50.0, 45.0]),
}
RANK_ORDER = ("増田", "SS", "S", "A", "B", "C", "D")

# pokeSleepCalc pokeType -> daifuku 得意编号
POKETYPE_TO_TABLE = {1: 1, 2: 5, 3: 9, 4: 5}


def _pokedex():
    _load()
    from local_expected import _pokedex as pd
    return pd


def _species_map():
    _load()
    from local_expected import _species_map as sm
    return sm


def rating_metric(species, result):
    """Return the specialty output used to compare individuals of a species.

    Direct total energy is a poor IV metric for support-skill specialists: many
    support effects intentionally have no energy conversion in pokeSleepCalc,
    which previously made skill-trigger sub-skills look worthless.  Compare the
    Pokémon's own specialty output instead.
    """
    role = SPECIALTY_OVERRIDES.get(normalize_species(species))
    poke_type = poke_type_of(species)
    if role == "berry" or poke_type == 1:
        return "total_energy", float(result.get("total_energy", 0))
    if poke_type == 2:
        return "food_energy", float(result.get("food_energy", 0))
    if poke_type == 3:
        return "skill_triggers", float(result.get("help_count", {}).get("skill", 0))
    return "total_energy", float(result.get("total_energy", 0))


def _pattern_from_values(values):
    values = [str(v).strip() for v in values]
    if len(values) < 3:
        return None
    if all(value.upper() in ("A", "B", "C") for value in values[:3]):
        return "".join(value.upper() for value in values[:3])
    return None


def ingredient_pattern_of(row):
    """Read a normalized AAA/ABB/etc. pattern from current or future CSV rows."""
    for key in ("ingredient_pattern", "food_pattern", "食材分布"):
        value = str(row.get(key) or "").strip().upper()
        if len(value) == 3 and all(ch in "ABC" for ch in value):
            return value
    for prefix in ("ingredient", "food", "食材"):
        values = [row.get(f"{prefix}{i}") or "" for i in range(1, 4)]
        pattern = _pattern_from_values(values)
        if pattern:
            return pattern
        species = row.get("final_form") or row.get("species") or ""
        canonical = species_food_types_for_pattern(species)
        ids = [food_name_to_id(str(value).strip()) for value in values]
        if canonical and all(fid is not None and fid in canonical for fid in ids):
            return "".join(chr(ord("A") + canonical.index(fid)) for fid in ids)
    return None


def species_food_types_for_pattern(species):
    return species_food_types(species)


def ingredient_pattern_multiplier(species, row):
    if poke_type_of(species) != 2:
        return None, 1.0
    pattern = ingredient_pattern_of(row)
    if pattern is None or pattern in PREFERRED_FOOD_PATTERNS:
        return pattern, 1.0
    return pattern, NON_PREFERRED_FOOD_MULTIPLIER


def _candidate_patterns(species, known_pattern=None):
    legal = legal_ingredient_patterns(species)
    if known_pattern:
        return (known_pattern,) if known_pattern in legal else ()
    role = SPECIALTY_OVERRIDES.get(normalize_species(species))
    poke_type = poke_type_of(species)
    if poke_type == 2:
        return tuple(p for p in legal if p in PREFERRED_FOOD_PATTERNS)
    if role == "berry" or poke_type == 1:
        return legal
    return (None,)


def _evaluate_configuration(species, level, subs, nature, pattern=None):
    use_food_ids = food_ids_for_pattern(species, pattern) if pattern else None
    result = compute_expected(
        species,
        level,
        subs,
        nature,
        main_skill_lv=EVALUATION_MAIN_SKILL_LEVEL,
        main_skill_level_is_final=True,
        use_food_ids=use_food_ids,
    )
    if "error" in result:
        return result, None, 0.0
    metric, value = rating_metric(species, result)
    multiplier = 1.0
    if poke_type_of(species) == 2 and pattern and pattern not in PREFERRED_FOOD_PATTERNS:
        multiplier = NON_PREFERRED_FOOD_MULTIPLIER
    return result, metric, value * multiplier


def _data_fingerprint():
    """Fingerprint inputs that materially affect baseline energy."""
    digest = hashlib.sha256()
    for name in ("pokedex.json", "berryEnergy.json", "foodEnergy.json", "skillEffects.json", "species_map.json"):
        with open(os.path.join(DATA, name), "rb") as f:
            digest.update(f.read())
    return digest.hexdigest()[:16]


def _load_baseline_cache():
    empty = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "data_fingerprint": _data_fingerprint(),
        "entries": {},
    }
    if not os.path.exists(BASELINE_FILE):
        return empty
    try:
        with open(BASELINE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        return empty
    if (
        cache.get("schema_version") != BASELINE_SCHEMA_VERSION
        or cache.get("algorithm_version") != ALGORITHM_VERSION
        or cache.get("data_fingerprint") != empty["data_fingerprint"]
        or not isinstance(cache.get("entries"), dict)
    ):
        return empty
    return cache


def baseline_for(species, level, force_recompute=False):
    """Enumerate the modeled ceiling at ``level`` and cache the best result."""
    species = normalize_species(species)
    cache = _load_baseline_cache()
    entries = cache["entries"]
    key = f"{species}|{level}"
    if key in entries and not force_recompute:
        return entries[key]
    enum_slots = unlocked_subskill_count(level)
    best = 0.0
    best_cfg = None
    patterns = _candidate_patterns(species)
    if not patterns:
        patterns = (None,)
    for subs in itertools.combinations(PROD_SUBS, enum_slots):
        subs = list(subs)
        for nature in NATURE_MAP:
            for pattern in patterns:
                r, metric, t = _evaluate_configuration(species, level, subs, nature, pattern)
                if t > best:
                    best = t
                    best_cfg = {"subs": subs, "nature": nature, "ingredient_pattern": pattern}
    entries[key] = {"energy": best, "metric": metric, "cfg": best_cfg}
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    return entries[key]


def poke_type_of(species):
    pid = _species_map().get(normalize_species(species))
    if pid is None:
        return None
    entry = _pokedex().get(str(pid))
    return entry.get("pokeType") if entry else None


def rank_for(species, pct):
    """Map percentage to rank using the species' 得意 table."""
    role = SPECIALTY_OVERRIDES.get(normalize_species(species))
    pt = poke_type_of(species)
    tbl_no = 1 if role == "berry" else POKETYPE_TO_TABLE.get(pt, 5)
    name, thresholds = RANK_TABLES[tbl_no]
    order = ("増田", "SS", "S", "A", "B", "C")
    for i, rank in enumerate(order):
        if pct >= thresholds[i]:
            return rank, name
    return "D", name


def rank_for_table(table_no, pct):
    """Map a percentage to a rank using an explicit Daifuku category."""
    if table_no not in RANK_TABLES:
        raise ValueError(f"unknown rank table: {table_no}")
    name, thresholds = RANK_TABLES[table_no]
    for index, rank in enumerate(("増田", "SS", "S", "A", "B", "C")):
        if float(pct) >= thresholds[index]:
            return rank, name
    return "D", name


def score_iv_local(row, level=70):
    """Local 個体値 rating. row: dict like box_ocr.csv rows.
    Returns {"status","rank","pct","tokui","baseline","individual"}."""
    species = row.get("final_form") or ""
    if not species:
        return {"status": "物种OCR识别失败"}
    subs = [row.get(f"subskill{i}") or "" for i in range(1, 6)]
    nature = row.get("nature") or ""
    baseline = baseline_for(species, level)
    bl = baseline["energy"]
    if not bl:
        return {"status": "ERR_BASELINE"}
    pattern = ingredient_pattern_of(row)
    patterns = _candidate_patterns(species, pattern)
    if pattern and not patterns:
        return {"status": f"ERR_INGREDIENT_PATTERN:{pattern}"}
    if not patterns:
        patterns = (None,)
    best_individual = None
    for calculation_pattern in patterns:
        candidate, candidate_metric, effective_value = _evaluate_configuration(
            species, level, subs, nature, calculation_pattern
        )
        if "error" in candidate:
            return {"status": candidate["error"]}
        if best_individual is None or effective_value > best_individual[0]:
            best_individual = (effective_value, candidate, candidate_metric, calculation_pattern)
    individual, ind, metric, calculation_pattern = best_individual
    pattern_multiplier = (
        NON_PREFERRED_FOOD_MULTIPLIER
        if poke_type_of(species) == 2 and calculation_pattern
        and calculation_pattern not in PREFERRED_FOOD_PATTERNS
        else 1.0
    )
    pct = individual / bl * 100
    rank, tokui = rank_for(species, pct)
    return {
        "status": "OK", "rank": rank, "pct": f"{pct:.2f}",
        "tokui": tokui, "metric": metric, "baseline": bl, "individual": individual,
        "individual_total_energy": ind["total_energy"],
        "ingredient_pattern": pattern,
        "calculation_pattern": calculation_pattern,
        "ingredient_multiplier": pattern_multiplier,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, BASE)
    from project_config import OCR_CSV
    _load()
    import csv
    rows = list(csv.DictReader(open(OCR_CSV, encoding="utf-8-sig")))
    for r in rows[:6]:
        print(r["folder"], r["final_form"], score_iv_local(r, 70))
