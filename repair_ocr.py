"""Repair derived OCR fields without re-running OCR for every screenshot."""

import csv
import os

import extract


FIELDS = [
    "folder", "base_species", "species", "level", "final_form", "main_skill",
    "main_skill_lv", "subskill1", "subskill2", "subskill3", "subskill4",
    "subskill5", "nature", "ingredient_pattern", "ingredient_ids",
    "ingredient_confidence", "ingredient_margin", "ingredient_error",
    "form_confidence", "form_margin", "form_error", "form_method",
]


def merge_parsed(row, parsed):
    subs = (parsed.get("subskills") or []) + [""] * 5
    values = {
        "base_species": parsed.get("base_species"),
        "species": parsed.get("species"),
        "level": parsed.get("level"),
        "final_form": parsed.get("final_form"),
        "main_skill": parsed.get("main_skill"),
        "main_skill_lv": parsed.get("main_skill_lv"),
        "nature": parsed.get("nature"),
        "ingredient_pattern": parsed.get("ingredient_pattern"),
        "ingredient_ids": parsed.get("ingredient_ids"),
        "ingredient_confidence": parsed.get("ingredient_confidence"),
        "ingredient_margin": parsed.get("ingredient_margin"),
        "ingredient_error": parsed.get("ingredient_error"),
        "form_confidence": parsed.get("form_confidence"),
        "form_margin": parsed.get("form_margin"),
        "form_error": parsed.get("form_error"),
        "form_method": parsed.get("form_method"),
    }
    values.update({f"subskill{i + 1}": subs[i] for i in range(5)})
    for key, value in values.items():
        row[key] = "" if value is None else value


def main():
    with open(extract.OUT, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    mappings = extract.load_mappings()

    reparsed = 0
    food_refreshed = 0
    for row in rows:
        folder = row["folder"]
        # The one fully obscured capture cannot be recovered from its images.
        bad_level = bool(row.get("level")) and int(row["level"]) > 80
        if (not row.get("species") or bad_level) and folder != "0081":
            merge_parsed(row, extract.parse_pokemon(folder, mappings))
            reparsed += 1
            continue
        if not row.get("species"):
            continue
        if not row.get("nature"):
            row["nature"] = extract.recognize_nature_fallback(
                os.path.join(extract.CAP, folder, "3.png"), mappings["natures"]
            ) or ""
        subskill_count = sum(bool(row.get(f"subskill{i}")) for i in range(1, 6))
        if subskill_count == 4 and extract.recognize_slot5_berry_fallback(
            os.path.join(extract.CAP, folder, "3.png")
        ):
            row["subskill5"] = "きのみの数S"
        if not row.get("ingredient_ids"):
            food_image = os.path.join(extract.CAP, folder, "1.png")
            ingredient = extract.recognize_ingredient_pattern(food_image, row["species"])
            row["ingredient_pattern"] = ingredient.get("pattern") or ""
            row["ingredient_ids"] = "/".join(str(v) for v in ingredient.get("ids") or [])
            row["ingredient_confidence"] = ingredient.get("confidence") or ""
            row["ingredient_margin"] = ingredient.get("margin") or ""
            row["ingredient_error"] = ingredient.get("error") or ""
            food_refreshed += 1

    with open(extract.OUT, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"reparsed={reparsed}, food_refreshed={food_refreshed}, rows={len(rows)}")


if __name__ == "__main__":
    main()
