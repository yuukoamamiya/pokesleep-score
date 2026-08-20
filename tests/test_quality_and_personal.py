import tempfile
import unittest
from pathlib import Path

from PIL import Image

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "score"))

import personal_adjustment as personal
import quality
import local_rank


class CaptureQualityTests(unittest.TestCase):
    def test_missing_ocr_csv_is_an_empty_collection(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(quality.read_ocr_rows(Path(temp) / "missing.csv"), [])

    def test_complete_image_set_is_structurally_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for page in range(4):
                image = Image.new("RGB", quality.EXPECTED_SIZE, (40 + page * 20, 120, 200))
                # Prevent the synthetic fixture from being classified as a flat screen.
                image.paste((255, 255, 255), (0, 0, 300, 300))
                image.save(folder / f"{page}.png")
            self.assertEqual(quality.validate_capture_files(folder), [])

    def test_missing_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            errors = quality.validate_capture_files(temp)
        self.assertEqual(len(errors), 4)

    def test_unlock_dialog_like_parse_is_rejected(self):
        errors, _ = quality.validate_parsed({"subskills": []}, strict_capture=True)
        self.assertIn("缺少物种", errors)
        self.assertIn("缺少等级", errors)
        self.assertIn("子技能仅识别0/5", errors)


class PersonalAdjustmentTests(unittest.TestCase):
    def base_row(self):
        return {
            "大福评级": "SS",
            "大福百分比": "75.00",
            "大福得意分类": "⑤",
            "食材分布": "ABC",
        }

    def test_nonpreferred_food_pattern_gets_seventy_percent(self):
        row = personal.adjust_row(self.base_row())
        self.assertEqual(row["个人修正百分比"], "52.50")
        self.assertEqual(row["个人修正评级"], "B")
        self.assertEqual(row["个人建议"], "放生候选")

    def test_abb_food_pattern_keeps_daifuku_result(self):
        source = self.base_row()
        source["食材分布"] = "ABB"
        row = personal.adjust_row(source)
        self.assertEqual(row["个人修正百分比"], "75.00")
        self.assertEqual(row["个人修正评级"], "SS")

    def test_berry_specialist_is_not_food_penalized(self):
        source = self.base_row()
        source["大福得意分类"] = "①"
        row = personal.adjust_row(source)
        self.assertEqual(row["个人食材修正"], "1.00")
        self.assertEqual(row["个人修正评级"], "SS")

    def test_explicit_rank_table(self):
        self.assertEqual(local_rank.rank_for_table(5, 74)[0], "SS")
        self.assertEqual(local_rank.rank_for_table(5, 52.5)[0], "B")


if __name__ == "__main__":
    unittest.main()
