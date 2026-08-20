import json
import os
import re
import subprocess
import time
import sys
import difflib
import cv2
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract as E
import quality
from project_config import PROJECT_ROOT, WORKSPACE_ROOT, CAP_DIR as CONFIG_CAP_DIR

ADB = os.environ.get("POKESLEEP_ADB", r"C:\Program Files\Netease\MuMu\nx_main\adb.exe")
SERIAL = os.environ.get("POKESLEEP_ADB_SERIAL", "127.0.0.1:16384")
BASE = str(PROJECT_ROOT)
CAP_DIR = str(CONFIG_CAP_DIR)
PROGRESS = str(WORKSPACE_ROOT / "capture_progress.json")
MANIFEST = str(WORKSPACE_ROOT / "manifest.json")
CAPTURE_QUALITY = str(WORKSPACE_ROOT / "capture_quality.json")
FINE = (540, 1400, 540, 1050, 1000)  # slow swipe -> about one row, strong overlap

DETAIL_BACK = (150, 1830)
SWIPE_DETAIL = (540, 1600, 540, 900, 350)
SWIPE_DETAIL_SMALL = (540, 1500, 540, 950, 300)

OCR_PY = os.path.join(BASE, "score", "ocr.py")
VENV_PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")

LV_RE = re.compile(r"[LlＬ][VＶv]?[\.．]?\s*\d+")
JA_RE = re.compile(r"[ぁ-んァ-ヶ一-龯]")


def adb(*args):
    return subprocess.run(
        [ADB, "-s", SERIAL, "shell", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def ensure_device():
    """Connect the configured MuMu ADB endpoint and verify that it is online."""
    if not os.path.exists(ADB):
        print(f"[preflight] ADB not found: {ADB}", flush=True)
        return False
    try:
        devices = subprocess.run(
            [ADB, "devices"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        if SERIAL not in devices.stdout:
            subprocess.run(
                [ADB, "connect", SERIAL], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15,
            )
            devices = subprocess.run(
                [ADB, "devices"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
            )
        ready = any(
            line.startswith(SERIAL) and "device" in line
            for line in devices.stdout.splitlines()
        )
        if not ready:
            print(f"[preflight] MuMu device is not online: {SERIAL}", flush=True)
        return ready
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[preflight] ADB check failed: {exc}", flush=True)
        return False


def tap(x, y):
    # Unity game responds to touch-with-duration better than plain `input tap`
    adb("input", "swipe", str(x), str(y), str(x), str(y), "80")


def swipe(x1, y1, x2, y2, dur=350):
    adb("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur))


def screencap(path):
    result = subprocess.run(
        [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
        capture_output=True,
    )
    if result.returncode or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ADB screenshot failed: {error or result.returncode}")
    temporary = f"{path}.tmp"
    with open(temporary, "wb") as handle:
        handle.write(result.stdout)
    os.replace(temporary, path)


def ocr(png):
    # Keep the OCR model resident while indexing/capturing hundreds of screens.
    # Starting score/ocr.py for every screenshot reloads the model each time.
    return E.ocr_img(png)


def in_box(items):
    return any(("拡張する" in t["text"]) or ("表示順" in t["text"]) or ("匹/" in t["text"]) for t in items)


def in_menu(items):
    txt = " ".join(t["text"] for t in items)
    return ("チーム編成" in txt) and ("ポケモンボックス" in txt)


def in_detail(items):
    return any(("お気に入り" in t["text"]) or ("とくいなもの" in t["text"]) or ("タイプ" == t["text"].strip()) for t in items)


JUNK = {"拡張する", "表示順", "登録日", "もどる", "OFF", "ポケモンボックス", "仲間になっているポケモンの一覧です"}

DIALOG_CONFIRM = {"OK", "確認", "もらう", "閉じる"}
DIALOG_TEXT = {"時間の証", "リボン", "時間で", "証", "バッジ", "勲章", "達成"}


def is_dialog(items):
    # a confirm button located in the dialog button zone (center-lower), not the bottom-left もどる
    for t in items:
        if t["text"].strip() in DIALOG_CONFIRM:
            cx = (t["x0"] + t["x1"]) // 2
            cy = (t["y0"] + t["y1"]) // 2
            if 280 < cx < 800 and 950 < cy < 1550:
                return True
    # fallback: milestone text present anywhere
    txt = " ".join(t["text"] for t in items)
    if any(k in txt for k in DIALOG_TEXT):
        for t in items:
            if t["text"].strip() in DIALOG_CONFIRM:
                return True
    return False


def dismiss_dialog(items):
    """If a milestone/dialog is present, tap its confirm button. Returns True if dismissed."""
    for t in items:
        if t["text"].strip() in DIALOG_CONFIRM:
            tap((t["x0"] + t["x1"]) // 2, (t["y0"] + t["y1"]) // 2)
            return True
    return False


def detect_cards(items):
    lvs = [it for it in items if LV_RE.search(it["text"]) and 200 < it["y0"] < 1790]
    if not lvs:
        return []
    lvs.sort(key=lambda it: (it["y0"], it["x0"]))
    rows = []
    for lv in lvs:
        placed = False
        for r in rows:
            if abs(r[0]["y0"] - lv["y0"]) < 50:
                r.append(lv)
                placed = True
                break
        if not placed:
            rows.append([lv])
    cards = []
    for row in rows:
        row.sort(key=lambda it: it["x0"])
        for lv in row:
            cx = (lv["x0"] + lv["x1"]) // 2
            below = [it for it in items
                     if 100 < it["y0"] - lv["y1"] < 420
                     and abs(it["x0"] - lv["x0"]) < 130
                     and JA_RE.search(it["text"])
                     and it["text"].strip() not in JUNK]
            # In the four-column layout every complete card has its name below
            # the sprite. A level at the bottom without a following name is a
            # clipped next row and must not be indexed or tapped.
            if below:
                name = min(below, key=lambda it: it["y0"])
                tap_y = (lv["y1"] + name["y0"]) // 2
                name_text = name["text"]
            elif lv["y0"] < 1400:
                # Preserve the grid position when only the name OCR failed.
                # Levels below this cutoff belong to a clipped next row.
                tap_y = lv["y1"] + 150
                name_text = ""
            else:
                continue
            tap_y = min(tap_y, 1700)
            tap_y = max(tap_y, 150)
            cards.append({"x": cx, "y": tap_y, "name": name_text})
    # `rows` and each row are already ordered.  Do not sort by the exact tap Y:
    # OCR boxes in one visual row can differ by a pixel and would swap columns.
    return cards


def load_progress():
    if os.path.exists(PROGRESS):
        try:
            with open(PROGRESS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            print("[capture] progress file is invalid; starting empty", flush=True)
    return {"collected": []}


def save_progress(p):
    quality.atomic_write_json(Path(PROGRESS), p)


_CAPTURE_MAPPINGS = None


def validate_capture(idx):
    """Validate a four-page capture before its box position is committed."""
    global _CAPTURE_MAPPINGS
    folder = f"{idx:04d}"
    errors = quality.validate_capture_files(os.path.join(CAP_DIR, folder))
    parsed = None
    try:
        if _CAPTURE_MAPPINGS is None:
            _CAPTURE_MAPPINGS = E.load_mappings()
        parsed = E.parse_pokemon(folder, _CAPTURE_MAPPINGS)
        parsed_errors, warnings = quality.validate_parsed(parsed, strict_capture=True)
        errors.extend(parsed_errors)
    except Exception as exc:
        warnings = []
        errors.append(f"采集验收OCR失败:{exc}")
    report_path = Path(CAPTURE_QUALITY)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    except (OSError, ValueError):
        report = {}
    report[folder] = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "species": (parsed or {}).get("species"),
        "level": (parsed or {}).get("level"),
    }
    quality.atomic_write_json(report_path, report)
    return not errors, errors, warnings


def tap_card_retry(card):
    """Tap a card, dismissing milestone dialogs, verifying the detail opened."""
    for dy in (0, 40, -40, 80, -80, 120, -120):
        tap(card["x"], card["y"] + dy)
        time.sleep(1.9)
        tmp = str(WORKSPACE_ROOT / "_dtap.png")
        screencap(tmp)
        items = ocr(tmp)
        if is_dialog(items):
            print("[capture] milestone dialog, dismissing", flush=True)
            dismiss_dialog(items)
            time.sleep(1.5)
            screencap(tmp)
            items = ocr(tmp)
        if in_detail(items) or "お気に入り" in " ".join(t["text"] for t in items):
            return True
    return False


def capture_one(idx):
    d = os.path.join(CAP_DIR, f"{idx:04d}")
    os.makedirs(d, exist_ok=True)
    # dismiss any milestone dialog before capturing
    for _ in range(2):
        ctmp0 = str(WORKSPACE_ROOT / "_pre_check.png")
        screencap(ctmp0)
        citems0 = ocr(ctmp0)
        if is_dialog(citems0):
            print("[capture] dialog during capture, dismissing", flush=True)
            dismiss_dialog(citems0)
            time.sleep(1.5)
        else:
            break
    screencap(os.path.join(d, "0.png"))
    time.sleep(0.4)
    swipe(*SWIPE_DETAIL_SMALL)
    time.sleep(1.1)
    screencap(os.path.join(d, "1.png"))
    time.sleep(0.4)
    swipe(*SWIPE_DETAIL)
    time.sleep(1.1)
    screencap(os.path.join(d, "2.png"))
    time.sleep(0.4)
    swipe(*SWIPE_DETAIL)
    time.sleep(1.1)
    screencap(os.path.join(d, "3.png"))
    # scroll back to top of detail
    for _ in range(3):
        swipe(540, 500, 540, 1700, 300)
        time.sleep(0.6)
    # only press back if we are still on the detail
    ctmp = str(WORKSPACE_ROOT / "_dbg_check.png")
    screencap(ctmp)
    citems = ocr(ctmp)
    if in_detail(citems):
        tap(*DETAIL_BACK)
        time.sleep(1.8)
    else:
        time.sleep(1.2)


def goto_box():
    """Navigate to the box from whatever screen the game is on, then scroll to top."""
    for attempt in range(12):
        tmp = str(WORKSPACE_ROOT / "_nav.png")
        screencap(tmp)
        items = ocr(tmp)
        if in_box(items):
            break
        txt = " ".join(t["text"] for t in items)
        # on detail -> back
        if in_detail(items) or "もどる" in txt:
            tap(*DETAIL_BACK)
            time.sleep(2)
            continue
        # on pokemon menu -> tap ポケモンボックス
        if "ポケモンボックス" in txt or "チーム編成" in txt:
            box_btn = next((t for t in items if "ポケモンボックス" in t["text"] and t["y0"] > 1300), None)
            if box_btn:
                tap((box_btn["x0"] + box_btn["x1"]) // 2, (box_btn["y0"] + box_btn["y1"]) // 2)
                time.sleep(3)
                continue
        # on home / pokemon menu -> tap ポケモン (bottom-left)
        if "メニュー" in txt or "カビゴン" in txt or "ポケモン" in txt:
            poke = next((t for t in items if "ポケモン" in t["text"] and t["y0"] > 1750), None)
            if poke:
                tap((poke["x0"] + poke["x1"]) // 2, (poke["y0"] + poke["y1"]) // 2)
                time.sleep(3)
                continue
            # fallback: bottom-left pokemon button
            tap(110, 1875)
            time.sleep(3)
            continue
        # unknown -> tap back and retry
        adb("input", "keyevent", "4")
        time.sleep(2)
    # scroll the box to the very top (resume-safe: deterministic list order + pos-skip)
    for _ in range(26):
        swipe(540, 400, 540, 1700, 250)
        time.sleep(0.9)
    return True


def reenter_box():
    """Fast recovery to the box from a nearby screen (menu/detail). Falls back to goto_box."""
    for _ in range(3):
        tmp = str(WORKSPACE_ROOT / "_renav.png")
        screencap(tmp)
        items = ocr(tmp)
        if in_box(items):
            return True
        txt = " ".join(t["text"] for t in items)
        if in_menu(items):
            box_btn = next((t for t in items if "ポケモンボックス" in t["text"] and t["y0"] > 1300), None)
            if box_btn:
                tap((box_btn["x0"] + box_btn["x1"]) // 2, (box_btn["y0"] + box_btn["y1"]) // 2)
                time.sleep(3)
                continue
        if in_detail(items) or "もどる" in txt:
            tap(*DETAIL_BACK)
            time.sleep(2)
            continue
        # unknown: full navigation
        goto_box()
        return True
    return goto_box()


MIN_SHIFT = 100
MAX_SHIFT = 2200  # allow up to ~3 missed screens (shift = k*scroll) before rematching
CARD_H_EST = 400   # Pokémon box row height (px), refined per sweep from OCR
COLS = 4           # current 1080px box grid columns
INDEX_SWEEPS = int(os.environ.get("POKESLEEP_INDEX_SWEEPS", "3"))


def name_similar(a, b, cutoff=0.8):
    na = E.normalize(a)
    nb = E.normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= cutoff


def box_population(items):
    """Read the occupied count from the box header, e.g. 330/360 -> 330."""
    for item in items:
        m = re.search(r"(\d+)\s*/\s*(\d+)", item["text"])
        if m:
            return int(m.group(1))
    return None


def scroll_to_top():
    for _ in range(26):
        swipe(540, 400, 540, 1700, 250)
        time.sleep(0.7)


def estimate_geometry(screens):
    """Estimate box card height (px) and per-FINE-swipe scroll px from OCR data."""
    gaps = []
    for screen in screens:
        rows = []
        for c in sorted(screen, key=lambda c: c["y"]):
            if not rows or c["y"] - rows[-1] > 80:
                rows.append(c["y"])
        gaps.extend(rows[i + 1] - rows[i] for i in range(len(rows) - 1))
    card_h = sorted(gaps)[len(gaps) // 2] if gaps else CARD_H_EST
    shifts = []
    for a, b in zip(screens, screens[1:]):
        for cb in b:
            for ca in a:
                if abs(ca["x"] - cb["x"]) < 120 and name_similar(ca["name"], cb["name"]) and ca["y"] > cb["y"]:
                    shifts.append(ca["y"] - cb["y"])
    scr = sorted(shifts)[len(shifts) // 2] if shifts else int(card_h * 1.5)
    return max(card_h, 60), max(scr, 40)


def bottom_blank(png):
    """The real list end leaves a large completely blank area above the footer."""
    image = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
    if image is None or image.shape[0] < 1700 or image.shape[1] < 1020:
        return False
    band = image[1420:1700, 40:1020]
    return float((band < 235).mean()) < 0.005


def align_cursor(cr, manifest, cursor):
    """Re-anchor the top-of-screen manifest index to this screen's cards."""
    top = cr[0]
    best, bestscore = cursor, -1
    for c0 in range(max(0, cursor - 3), cursor + 4):
        if c0 >= len(manifest):
            continue
        if not name_similar(top["name"], manifest[c0]["name"]):
            continue
        score = sum(1 for i, card in enumerate(cr[:3])
                    if c0 + i < len(manifest) and name_similar(card["name"], manifest[c0 + i]["name"]))
        if score > bestscore:
            bestscore, best = score, c0
    return best


def sweep_screens(on_screen=None):
    """One independent top→bottom fine-scroll sweep. Returns list of screens,
    each a list of card dicts {"name","x","y"} sorted by (y, x).
    If on_screen(cr) is given, it's called on each screen right after OCR
    (before advancing), letting callers tap cards live at the right position."""
    screens = []
    last_fp = ""
    same = 0
    guard = 0
    while True:
        tmp = str(WORKSPACE_ROOT / "_swp.png")
        screencap(tmp)
        items = ocr(tmp)
        if not in_box(items):
            reenter_box()
            continue
        cards = detect_cards(items)
        if not cards:
            guard += 1
            if guard > 25:
                break
            swipe(*FINE)
            time.sleep(2)
            continue
        guard = 0
        # At the bottom, OCR box coordinates can jitter by a few pixels even
        # though the list did not move. Names/columns remain stable and are the
        # correct end-of-list fingerprint.
        fp = "|".join(f"{card_column(c)}:{E.normalize(c['name'])}" for c in cards)
        if fp == last_fp:
            same += 1
            if same >= 3:
                if bottom_blank(tmp):
                    break
                # MuMu occasionally drops touch input. A stationary non-bottom
                # screen gets one stronger retry instead of ending the sweep.
                swipe(540, 1500, 540, 900, 800)
                time.sleep(2)
                same = 0
                continue
            # Do not add a stationary retry as another logical screen.
            swipe(*FINE)
            time.sleep(2)
            continue
        else:
            same = 0
        last_fp = fp
        # detect_cards already returns row-major order with a row tolerance.
        # Exact Y sorting can interleave columns when OCR differs by 1 px.
        cr = [{"name": c["name"], "x": c["x"], "y": c["y"]} for c in cards]
        screens.append(cr)
        if len(screens) >= 180:
            print("[sweep] safety limit reached", flush=True)
            break
        if len(screens) % 10 == 0:
            print(f"[sweep] {len(screens)} screens, {sum(len(s) for s in screens)} visible cards", flush=True)
        if on_screen is not None:
            if on_screen(cr) is False:
                return screens
        swipe(*FINE)
        time.sleep(2)
    return screens


def hround(x):
    from decimal import Decimal, ROUND_HALF_UP
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def screen_rows(cards):
    """Group detected cards into visual rows while preserving their columns."""
    rows = []
    for card in sorted(cards, key=lambda c: c["y"]):
        if not rows or abs(card["y"] - rows[-1][0]["y"]) >= 80:
            rows.append([card])
        else:
            rows[-1].append(card)
    for row in rows:
        row.sort(key=lambda c: c["x"])
    return rows


def card_column(card):
    return max(0, min(COLS - 1, int(card["x"] * COLS / 1080)))


def row_match_score(a, b):
    """Count matching species in the same columns of two visual rows."""
    aa = {card_column(c): c["name"] for c in a}
    bb = {card_column(c): c["name"] for c in b}
    return sum(name_similar(aa[col], bb[col]) for col in aa.keys() & bb.keys())


def anchored_indices(screens):
    """Map cards to absolute indices by merging adjacent complete visual rows.

    The swipe is shorter than the visible card area, so a new screen either
    overlaps the preceding screen's last rows or starts with the immediately
    following row. This avoids cumulative pixel drift over the full box.
    """
    out = []
    known_rows = []
    previous = None
    previous_start = 0
    for cr in screens:
        rows = screen_rows(cr)
        if not rows:
            continue
        y0 = sum(c["y"] for c in rows[0]) / len(rows[0])
        offsets = [hround(((sum(c["y"] for c in row) / len(row)) - y0) / CARD_H_EST)
                   for row in rows]
        start_row = 0
        if previous is not None:
            prev_rows, prev_offsets = previous
            prev_by_global = {previous_start + off: row for row, off in zip(prev_rows, prev_offsets)}
            prev_max = max(prev_by_global)
            candidates = []
            for candidate in range(previous_start, prev_max + 2):
                diffs = []
                name_score = 0
                for row, off in zip(rows, offsets):
                    old = prev_by_global.get(candidate + off)
                    if old is None:
                        continue
                    old_y = sum(c["y"] for c in old) / len(old)
                    new_y = sum(c["y"] for c in row) / len(row)
                    diffs.append(old_y - new_y)
                    name_score += row_match_score(old, row)
                if diffs and 100 <= sum(diffs) / len(diffs) <= 850 and max(diffs) - min(diffs) < 100:
                    candidates.append((len(diffs), name_score, -candidate, candidate))
            start_row = max(candidates)[3] if candidates else prev_max + 1
        for row, offset in zip(rows, offsets):
            absolute_row = start_row + offset
            for card in row:
                out.append((absolute_row * COLS + card_column(card), card["name"]))
            if absolute_row >= len(known_rows):
                known_rows.append(row)
        previous = (rows, offsets)
        previous_start = start_row
    return out


def build_manifest():
    """Independent anchored sweeps merged by absolute box index (majority vote).
    Deterministic geometry makes the index of each individual stable across sweeps,
    so OCR misses don't shift it. Writes manifest.json."""
    from collections import Counter
    if not goto_box():
        print("[index] FAILED to navigate to box", flush=True)
        return
    top_png = str(WORKSPACE_ROOT / "_index_top.png")
    screencap(top_png)
    expected = box_population(ocr(top_png))
    if not expected:
        print("[index] FAILED to read box population from header", flush=True)
        return
    print(f"[index] box contains {expected} individuals", flush=True)
    votes = {}
    for r in range(INDEX_SWEEPS):
        scroll_to_top()
        entries = anchored_indices(sweep_screens())
        if not entries:
            continue
        for idx, name in entries:
            votes.setdefault(idx, Counter())[name] += 1
        print(f"[index] sweep {r+1}: {len(entries)} cards mapped to {len(votes)} indices", flush=True)
        if r >= 1 and sum(len(c) for c in votes.values()) >= 2 * len(entries):
            pass
    mapped = set(votes)
    required = set(range(expected))
    missing = sorted(required - mapped)
    extra = sorted(mapped - required)
    if missing or extra:
        print(f"[index] VALIDATION FAILED: missing={missing} extra={extra}", flush=True)
        print("[index] manifest.json was not written; detail capture will not start", flush=True)
        return
    m = expected
    manifest = []
    for i in range(m):
        c = votes.get(i)
        manifest.append({"seq": i, "name": c.most_common(1)[0][0] if c else ""})
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[index] wrote {MANIFEST}: {len(manifest)} individuals", flush=True)
    return manifest


def capture_manifest():
    """Collect screenshots by box position (anchored cursor), NOT fingerprint.
    The manifest fixes seq == box position, so the same individual always maps to
    the same folder number. Taps each card live during a fine-scroll sweep, then
    repeats sweeps until one captures nothing new."""
    manifest = []
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)
    if not manifest:
        print("[capture] no manifest.json - run --index first", flush=True)
        return
    expected = len(manifest)
    os.makedirs(CAP_DIR, exist_ok=True)
    prog = load_progress()
    collected = set(prog.get("collected", []))
    print(f"[capture] expected {expected} individuals; already collected {len(collected)}", flush=True)

    if not goto_box():
        print("[capture] FAILED to navigate to box", flush=True)
        return
    round_no = 0
    capture_limit = int(os.environ.get("POKESLEEP_CAPTURE_LIMIT", "0"))
    while True:
        round_no += 1
        scroll_to_top()
        new_this_round = 0
        live_screens = []

        def handle_screen(cr):
            nonlocal new_this_round
            if not cr:
                return
            live_screens.append(cr)
            current_mapping = anchored_indices(live_screens)[-len(cr):]
            for card, (mi, _) in zip(cr, current_mapping):
                if mi >= len(manifest):
                    continue
                if mi in collected:
                    continue
                captured = False
                for capture_attempt in range(1, 3):
                    ok = tap_card_retry(card)
                    if not ok:
                        print(f"[capture] could not open detail seq {mi} ({card['name']}); skip", flush=True)
                        reenter_box()
                        break
                    capture_one(mi)
                    valid, errors, warnings = validate_capture(mi)
                    if valid:
                        captured = True
                        if warnings:
                            print(f"[capture] #{mi:04d} QA warning: {'; '.join(warnings)}", flush=True)
                        break
                    print(
                        f"[capture] #{mi:04d} invalid capture attempt {capture_attempt}/2: "
                        f"{'; '.join(errors)}",
                        flush=True,
                    )
                    reenter_box()
                if not captured:
                    # Do not mark the position complete merely because four PNG
                    # files exist. A later sweep can retry it after a dialog or
                    # transient page failure has cleared.
                    continue
                collected.add(mi)
                prog["collected"] = sorted(collected)
                save_progress(prog)
                new_this_round += 1
                print(f"[capture] #{mi:04d} {card['name']} (total {len(collected)})", flush=True)
                inb = False
                for _ in range(2):
                    time.sleep(1.6)
                    btmp = str(WORKSPACE_ROOT / "_box_check.png")
                    screencap(btmp)
                    bitems = ocr(btmp)
                    if in_box(bitems):
                        inb = True
                        break
                if not inb:
                    print("[capture] not in box after capture, re-entering", flush=True)
                    reenter_box()
                if capture_limit and new_this_round >= capture_limit:
                    return False

        screens = sweep_screens(on_screen=handle_screen)
        if not screens:
            print("[capture] sweep returned no screens, aborting round", flush=True)
            break
        print(f"[capture] round {round_no}: collected {len(collected)} (new {new_this_round})", flush=True)
        if capture_limit and new_this_round >= capture_limit:
            print(f"[capture] sample limit reached ({capture_limit})", flush=True)
            break
        if len(collected) >= expected:
            break
        if new_this_round == 0:
            break
        if round_no >= 6:
            print("[capture] max rounds reached", flush=True)
            break

    prog["done"] = len(collected) >= expected
    save_progress(prog)
    print(f"[capture] DONE collected {len(collected)} unique", flush=True)
    missing = [m for m in manifest if m["seq"] not in collected]
    if missing:
        print(f"[capture] WARNING: manifest had {expected}, {len(missing)} not captured:", flush=True)
        for m in missing:
            print(f"   #{m['seq']:04d} {m['name']}", flush=True)


if __name__ == "__main__":
    import sys as _s
    if not ensure_device():
        raise SystemExit(2)
    mode = _s.argv[1] if len(_s.argv) > 1 else None
    if mode == "--index":
        build_manifest()
    elif mode == "--verify":
        capture_manifest()
    else:
        build_manifest()
        capture_manifest()
