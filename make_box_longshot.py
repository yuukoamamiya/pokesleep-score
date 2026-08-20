"""Rebuild the four-column box order from captured detail screens and annotate it."""

from __future__ import annotations

import csv
import io
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from project_config import CAP_DIR, RESULT_DIR


ROOT = Path(__file__).resolve().parent
DAIFUKU_CSV_PATH = RESULT_DIR / "评分总表_大福对照.csv"
PERSONAL_CSV_PATH = RESULT_DIR / "评分总表_个人规则.csv"

COLS = 4
CELL_W = 360
STRIP_H = 54
IMAGE_H = 340
CELL_H = STRIP_H + IMAGE_H
HEADER_H = 250

RANK_STYLE = {
    "増田": ("増田", "#D81B60", "#FFFFFF"),
    "SS": ("SS", "#F5B700", "#2B2100"),
    "A": ("＜S · A", "#E53935", "#FFFFFF"),
    "B": ("＜S · B", "#E53935", "#FFFFFF"),
    "C": ("＜S · C", "#E53935", "#FFFFFF"),
    "D": ("＜S · D", "#E53935", "#FFFFFF"),
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/YuGothB.ttc" if bold else "C:/Windows/Fonts/YuGothM.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def load_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def fit_detail(folder: str) -> Image.Image:
    src = CAP_DIR / folder / "0.png"
    image = Image.open(src).convert("RGB")
    # Portrait, level and name. The crop intentionally omits the lower detail controls.
    crop = image.crop((0, 160, 1080, 1180))
    return crop.resize((CELL_W, IMAGE_H), Image.Resampling.LANCZOS)


def centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str,
                  used_font: ImageFont.ImageFont, fill: str) -> None:
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), text, font=used_font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(((left + right - width) / 2, (top + bottom - height) / 2 - bounds[1]),
              text, font=used_font, fill=fill)


def build(rank_source: str = "daifuku") -> tuple[Path, Path]:
    personal = rank_source == "personal"
    csv_path = PERSONAL_CSV_PATH if personal else DAIFUKU_CSV_PATH
    output_name = "box_个人规则标注长图.png" if personal else "box_大福标注长图.png"
    preview_name = "box_个人规则标注预览.png" if personal else "box_大福标注预览.png"
    output_path = RESULT_DIR / output_name
    preview_path = RESULT_DIR / preview_name
    rows = load_rows(csv_path)
    grid_rows = (len(rows) + COLS - 1) // COLS
    width = COLS * CELL_W
    height = HEADER_H + grid_rows * CELL_H
    out = Image.new("RGB", (width, height), "#F3F5F7")
    draw = ImageDraw.Draw(out)

    draw.rectangle((0, 0, width, HEADER_H), fill="#FFFFFF")
    title = "Pokémon Box · 个人规则标记" if personal else "Pokémon Box · 大福评分标记"
    draw.text((42, 25), title, font=font(46, True), fill="#202124")
    draw.text((42, 91), f"按游戏箱子的四列顺序排列 · 共 {len(rows)} 只", font=font(26), fill="#5F6368")

    legend = [
        ("増田", "#D81B60", "#FFFFFF"),
        ("SS", "#F5B700", "#2B2100"),
        ("＜S · 可放生候选", "#E53935", "#FFFFFF"),
        ("S · 不标记", "#E8EAED", "#3C4043"),
        ("待复核", "#6B7280", "#FFFFFF"),
    ]
    x = 42
    for label, bg, fg in legend:
        bounds = draw.textbbox((0, 0), label, font=font(22, True))
        badge_w = bounds[2] - bounds[0] + 34
        draw.rounded_rectangle((x, 157, x + badge_w, 210), radius=14, fill=bg)
        centered_text(draw, (x, 157, x + badge_w, 210), label, font(22, True), fg)
        x += badge_w + 18

    for index, row in enumerate(rows):
        folder = str(row.get("folder") or f"{index:04d}")
        box_number = int(folder) + 1 if folder.isdigit() else index + 1
        col = index % COLS
        grid_row = index // COLS
        x0 = col * CELL_W
        y0 = HEADER_H + grid_row * CELL_H
        rank_key = "个人修正评级" if personal else "大福评级"
        pct_key = "个人修正百分比" if personal else "大福百分比"
        rank = row.get(rank_key, "").strip()
        pct = row.get(pct_key, "").strip()

        style = RANK_STYLE.get(rank)
        if style:
            label, color, label_fg = style
        elif rank == "S":
            label, color, label_fg = "", "#DADCE0", "#3C4043"
        else:
            label, color, label_fg = "待复核", "#6B7280", "#FFFFFF"

        strip_bg = color if label else "#FFFFFF"
        draw.rectangle((x0, y0, x0 + CELL_W - 1, y0 + STRIP_H), fill=strip_bg)
        draw.text((x0 + 13, y0 + 10), f"#{box_number:03d}", font=font(23, True),
                  fill=label_fg if label else "#5F6368")
        if label:
            suffix = f"  {pct}%" if pct else ""
            bounds = draw.textbbox((0, 0), label + suffix, font=font(25, True))
            text_w = bounds[2] - bounds[0]
            draw.text((x0 + CELL_W - text_w - 13, y0 + 8), label + suffix,
                      font=font(25, True), fill=label_fg)

        detail = fit_detail(folder)
        out.paste(detail, (x0, y0 + STRIP_H))

        border_width = 7 if style or not rank else 2
        border_color = color if style or not rank else "#DADCE0"
        for offset in range(border_width):
            draw.rectangle((x0 + offset, y0 + offset, x0 + CELL_W - 1 - offset,
                            y0 + CELL_H - 1 - offset), outline=border_color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path, optimize=True)
    preview_h = max(1, round(out.height * 720 / out.width))
    out.resize((720, preview_h), Image.Resampling.LANCZOS).save(preview_path, optimize=True)
    return output_path, preview_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rank-source", choices=("daifuku", "personal"), default="daifuku")
    args = parser.parse_args()
    longshot, preview = build(args.rank_source)
    print(longshot)
    print(preview)
