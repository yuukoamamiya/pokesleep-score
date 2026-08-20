"""Shared capture/OCR quality checks used by collection and reporting."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from project_config import CAP_DIR, OCR_CSV, RESULT_DIR


EXPECTED_SIZE = (1080, 1920)
SPECIAL_PARTIAL_SUBSKILLS = {"ミュウ", "ダークライ"}


def atomic_write_json(path: Path, value: Any) -> None:
    """Write resumable state without leaving a half-written JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def validate_capture_files(folder: str | Path) -> list[str]:
    """Return structural image errors for one four-page detail capture."""
    folder_path = Path(folder)
    errors: list[str] = []
    for page in range(4):
        path = folder_path / f"{page}.png"
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"第{page}页缺失")
            continue
        try:
            with Image.open(path) as image:
                if image.size != EXPECTED_SIZE:
                    errors.append(f"第{page}页尺寸异常:{image.width}x{image.height}")
                gray = image.convert("L").resize((64, 64))
                stat = ImageStat.Stat(gray)
                if stat.stddev[0] < 4:
                    errors.append(f"第{page}页近似纯色")
        except (OSError, ValueError) as exc:
            errors.append(f"第{page}页无法读取:{exc}")
    return errors


def validate_parsed(parsed: dict[str, Any], strict_capture: bool = False) -> tuple[list[str], list[str]]:
    """Validate fields produced by ``extract.parse_pokemon`` or a CSV row."""
    errors: list[str] = []
    warnings: list[str] = []
    required = {
        "species": "物种",
        "level": "等级",
        "main_skill": "主技能",
        "nature": "性格",
        "ingredient_ids": "食材",
    }
    for key, label in required.items():
        if not str(parsed.get(key) or "").strip():
            errors.append(f"缺少{label}")

    try:
        level = int(parsed.get("level") or 0)
    except (TypeError, ValueError):
        level = 0
    if parsed.get("level") and not 1 <= level <= 80:
        errors.append(f"等级异常:{parsed.get('level')}")

    ingredient_ids = [part for part in str(parsed.get("ingredient_ids") or "").split("/") if part]
    if ingredient_ids and len(ingredient_ids) != 3:
        errors.append(f"食材槽数量异常:{len(ingredient_ids)}")

    species = str(parsed.get("species") or "")
    subskills = [
        str(parsed.get(f"subskill{i}") or "").strip() for i in range(1, 6)
    ]
    if not any(subskills) and isinstance(parsed.get("subskills"), list):
        subskills = [str(value or "").strip() for value in parsed["subskills"]]
    minimum = 1 if species in SPECIAL_PARTIAL_SUBSKILLS else 5
    count = sum(bool(value) for value in subskills)
    if count < minimum:
        message = f"子技能仅识别{count}/{minimum}"
        (errors if strict_capture and count == 0 else warnings).append(message)

    for field, label, warning_limit in (
        ("ingredient_confidence", "食材置信度", 0.25),
        ("ingredient_margin", "食材候选差距", 0.02),
    ):
        value = parsed.get(field)
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            warnings.append(f"{label}无法解析:{value}")
            continue
        if number < warning_limit:
            warnings.append(f"{label}偏低:{number:.4f}")

    form_error = str(parsed.get("form_error") or "")
    # A main-skill or first-ingredient decision deliberately overrides the
    # portrait matcher. Only unresolved portrait decisions need human review.
    if form_error and str(parsed.get("form_method") or "") == "portrait":
        warnings.append(f"换皮识别:{form_error}")
    return errors, warnings


def read_ocr_rows(path: Path = OCR_CSV) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))
