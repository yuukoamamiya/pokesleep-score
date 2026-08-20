import csv
import os
import re
import subprocess
import sys
import unicodedata

from project_config import PROJECT_ROOT, WORKSPACE_ROOT, CAP_DIR, OCR_CSV

BASE = str(PROJECT_ROOT)
sys.path.insert(0, BASE)
import extract as E

RECOVER = {}


def normalize(s):
    return unicodedata.normalize("NFKC", s).replace("ー", "-").replace(" ", "").lower()


def ocr_tesseract(path):
    r = subprocess.run(["tesseract", path, "stdout", "-l", "jpn", "--psm", "6"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


def crop_name(folder, img="0.png"):
    from PIL import Image
    p = os.path.join(CAP_DIR, folder, img)
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGB")
    w, h = im.size
    crop = im.crop((int(w*0.12), int(h*0.46), int(w*0.78), int(h*0.53)))
    crop = crop.resize((crop.width*3, crop.height*3), Image.LANCZOS)
    out = str(WORKSPACE_ROOT / f"_recover_{folder}.png")
    crop.save(out)
    return out


def main():
    with open(OCR_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    M = E.load_mappings()
    names = list(M["pokedex"].keys())

    for r in rows:
        folder = r["folder"]
        if r.get("species") and r["species"] != "None":
            continue
        best = None
        for img in ("0.png", "2.png"):
            crop = crop_name(folder, img)
            if not crop:
                continue
            txt = ocr_tesseract(crop)
            # find the name after Lv
            m = re.search(r"L[Ｖv]?\.?\s*\d+\s*([\u30a0-\u30ff\u4e00-\u9faf\w\-]+)", txt)
            frag = m.group(1) if m else txt.strip()
            frag = re.sub(r"[^ぁ-んァ-ヶ一-龯a-zA-Z]", "", frag)
            cand = E.close_match(frag, names, cutoff=0.6) if frag else None
            if cand:
                best = cand
                break
        RECOVER[folder] = best
        print(f"{folder}: OCR='{frag if 'frag' in dir() else ''}' -> {best}", flush=True)

    # update box_ocr.csv
    for r in rows:
        folder = r["folder"]
        sp = RECOVER.get(folder)
        if sp:
            r["species"] = sp
            r["final_form"] = M["evolution"].get(sp, sp)
    with open(OCR_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n = sum(1 for v in RECOVER.values() if v)
    print(f"\nrecovered {n}/{len(RECOVER)}")


if __name__ == "__main__":
    main()
