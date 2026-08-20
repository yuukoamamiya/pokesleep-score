import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "score"))

import local_expected as expected
import local_rank as rank


class SubskillUnlockTests(unittest.TestCase):
    def test_current_unlock_levels(self):
        cases = {
            1: 0, 9: 0, 10: 1, 24: 1, 25: 2, 49: 2,
            50: 3, 69: 3, 70: 4, 79: 4, 80: 5, 100: 5,
        }
        for level, count in cases.items():
            with self.subTest(level=level):
                self.assertEqual(expected.unlocked_subskill_count(level), count)

    def test_level_70_ignores_fifth_subskill(self):
        base = ["おてつだいスピードM"] * 4
        without_fifth = expected.compute_expected("ライチュウ", 70, base, "まじめ")
        with_fifth = expected.compute_expected(
            "ライチュウ", 70, base + ["きのみの数S"], "まじめ"
        )
        self.assertEqual(without_fifth["total_energy"], with_fifth["total_energy"])

    def test_level_80_activates_fifth_subskill_when_data_supports_it(self):
        expected._load()
        berry_levels = len(expected._berry_energy["1"]["energy"])
        if berry_levels < 80:
            self.skipTest("bundled data does not support level 80 yet")
        base = ["おてつだいスピードM"] * 4
        without_fifth = expected.compute_expected("ライチュウ", 80, base, "まじめ")
        with_fifth = expected.compute_expected(
            "ライチュウ", 80, base + ["きのみの数S"], "まじめ"
        )
        self.assertGreater(with_fifth["total_energy"], without_fifth["total_energy"])

    def test_standard_evaluation_uses_exact_main_skill_level_five(self):
        result = expected.compute_expected(
            "ライチュウ",
            70,
            ["スキルレベルアップM"],
            "まじめ",
            main_skill_lv=expected.EVALUATION_MAIN_SKILL_LEVEL,
            main_skill_level_is_final=True,
        )
        reference = expected.compute_expected(
            "ライチュウ",
            70,
            [],
            "まじめ",
            main_skill_lv=5,
            main_skill_level_is_final=True,
        )
        self.assertEqual(result["skill_energy"], reference["skill_energy"])


class IvRatingTests(unittest.TestCase):
    def _row(self, main_skill_lv):
        return {
            "final_form": "ライチュウ",
            "main_skill_lv": str(main_skill_lv),
            "subskill1": "おてつだいスピードS",
            "subskill2": "おてつだいスピードM",
            "subskill3": "きのみの数S",
            "subskill4": "おてつだいボーナス",
            "subskill5": "スキルレベルアップM",
            "nature": "いじっぱり",
        }

    def test_seed_investment_does_not_change_iv(self):
        with mock.patch.object(rank, "baseline_for", return_value={"energy": 1, "cfg": {}}):
            low = rank.score_iv_local(self._row(1), 70)
            high = rank.score_iv_local(self._row(7), 70)
        self.assertEqual(low["individual"], high["individual"])
        self.assertEqual(low["pct"], high["pct"])

    def test_skill_specialist_values_trigger_chance(self):
        plain = expected.compute_expected(
            "ニンフィア", 70, [], "まじめ",
            main_skill_lv=5, main_skill_level_is_final=True,
        )
        boosted = expected.compute_expected(
            "ニンフィア", 70, ["スキル確率アップM"], "おとなしい",
            main_skill_lv=5, main_skill_level_is_final=True,
        )
        metric, plain_value = rank.rating_metric("ニンフィア", plain)
        _, boosted_value = rank.rating_metric("ニンフィア", boosted)
        self.assertEqual(metric, "skill_triggers")
        self.assertGreater(boosted_value, plain_value)

    def test_each_specialty_uses_its_core_output(self):
        berry = expected.compute_expected("ライチュウ", 70, [], "まじめ")
        food = expected.compute_expected("カメックス", 70, [], "まじめ")
        self.assertEqual(rank.rating_metric("ライチュウ", berry)[0], "total_energy")
        self.assertEqual(rank.rating_metric("カメックス", food)[0], "food_energy")

    def test_sceptile_is_rated_as_berry_specialist(self):
        result = expected.compute_expected("ジュカイン", 70, [], "まじめ")
        metric, value = rank.rating_metric("ジュカイン", result)
        self.assertEqual(metric, "total_energy")
        self.assertEqual(value, result["total_energy"])

    def test_food_pattern_penalty(self):
        self.assertEqual(rank.ingredient_pattern_multiplier("カメックス", {"ingredient_pattern": "AAA"}), ("AAA", 1.0))
        self.assertEqual(rank.ingredient_pattern_multiplier("カメックス", {"ingredient_pattern": "ABB"}), ("ABB", 1.0))
        self.assertEqual(rank.ingredient_pattern_multiplier("カメックス", {"ingredient_pattern": "ABC"}), ("ABC", 0.70))
        self.assertEqual(rank.ingredient_pattern_multiplier("カメックス", {}), (None, 1.0))

    def test_food_pattern_can_be_derived_from_ingredient_names(self):
        row = {
            "final_form": "カメックス",
            "ingredient1": "モーモーミルク",
            "ingredient2": "リラックスカカオ",
            "ingredient3": "リラックスカカオ",
        }
        self.assertEqual(rank.ingredient_pattern_of(row), "ABB")

    def test_food_pattern_uses_species_defined_abc(self):
        self.assertEqual(expected.food_ids_for_pattern("カメックス", "AAA"), [8, 8, 8])
        self.assertEqual(expected.food_ids_for_pattern("カメックス", "ABB"), [8, 13, 13])
        self.assertEqual(expected.food_ids_for_pattern("カメックス", "ABC"), [8, 13, 7])

    def test_two_food_species_has_four_legal_patterns(self):
        self.assertEqual(
            expected.legal_ingredient_patterns("デンリュウ"),
            ("AAA", "AAB", "ABA", "ABB"),
        )
        with self.assertRaises(ValueError):
            expected.food_ids_for_pattern("デンリュウ", "AAC")

    def test_pattern_changes_real_food_output_before_penalty(self):
        aaa = expected.compute_expected(
            "カメックス", 70, [], "まじめ",
            use_food_ids=expected.food_ids_for_pattern("カメックス", "AAA"),
        )
        abc = expected.compute_expected(
            "カメックス", 70, [], "まじめ",
            use_food_ids=expected.food_ids_for_pattern("カメックス", "ABC"),
        )
        self.assertEqual(aaa["food_ids"], [8, 8, 8])
        self.assertEqual(abc["food_ids"], [8, 13, 7])
        self.assertNotEqual(aaa["food_energy"], abc["food_energy"])

    def test_nonpreferred_food_output_gets_extra_seventy_percent(self):
        raw = expected.compute_expected(
            "カメックス", 70, [], "まじめ",
            main_skill_lv=5,
            main_skill_level_is_final=True,
            use_food_ids=expected.food_ids_for_pattern("カメックス", "ABC"),
        )
        _, _, effective = rank._evaluate_configuration(
            "カメックス", 70, [], "まじめ", "ABC"
        )
        self.assertAlmostEqual(effective, raw["food_energy"] * 0.70)

    def test_food_baseline_only_uses_preferred_patterns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(rank, "BASELINE_FILE", os.path.join(temp_dir, "baseline.json")):
                baseline = rank.baseline_for("カメックス", 10)
        self.assertIn(baseline["cfg"]["ingredient_pattern"], {"AAA", "ABB"})

    def test_sceptile_uses_berry_rank_table(self):
        self.assertEqual(rank.rank_for("ジュカイン", 90)[1], "①きのみ得意")

    def test_baseline_cache_is_versioned(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "baseline.json")
            with mock.patch.object(rank, "BASELINE_FILE", cache_path):
                result = rank.baseline_for("ライチュウ", 10)
                with open(cache_path, encoding="utf-8") as f:
                    cache = json.load(f)
        self.assertGreater(result["energy"], 0)
        self.assertEqual(cache["schema_version"], rank.BASELINE_SCHEMA_VERSION)
        self.assertEqual(cache["algorithm_version"], rank.ALGORITHM_VERSION)
        self.assertIn("ライチュウ|10", cache["entries"])


class InputValidationTests(unittest.TestCase):
    def test_invalid_level_returns_error(self):
        self.assertIn("error", expected.compute_expected("ライチュウ", 0, [], None))

    def test_level_above_bundled_data_returns_error(self):
        self.assertIn("error", expected.compute_expected("ライチュウ", 999, [], None))


if __name__ == "__main__":
    unittest.main()
