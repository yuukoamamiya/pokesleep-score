import sys
from rapidocr import RapidOCR
from rapidocr.utils.typings import LangRec, OCRVersion, ModelType

ENGINE = None


def get_engine():
    global ENGINE
    if ENGINE is None:
        ENGINE = RapidOCR(params={
            "Rec.lang_type": LangRec.JAPAN,
            "Rec.ocr_version": OCRVersion.PPOCRV4,
            "Rec.model_type": ModelType.MOBILE,
        })
    return ENGINE


def ocr(path):
    res = get_engine()(path)
    out = []
    boxes = res.boxes if res.boxes is not None else None
    txts = res.txts if res.txts is not None else None
    if boxes is None:
        return out
    for b, t in zip(boxes, txts):
        x0, y0 = int(b[0][0]), int(b[0][1])
        x1, y1 = int(b[2][0]), int(b[2][1])
        out.append({"box": [x0, y0, x1, y1], "text": t})
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        for it in ocr(p):
            b, t = it["box"], it["text"]
            print(f"({b[0]},{b[1]})-({b[2]},{b[3]})  {t}")
