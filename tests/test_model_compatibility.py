import unittest

from utils.model_compatibility import (
    are_production_families_compatible,
    production_group_for_family,
)


class ModelCompatibilityTest(unittest.TestCase):
    def test_large_xs_and_auto_are_compatible(self):
        self.assertEqual(production_group_for_family("中大型XS"), "LARGE")
        self.assertEqual(production_group_for_family("中大型AUTO"), "LARGE")
        self.assertTrue(are_production_families_compatible("中大型XS", "中大型AUTO"))

    def test_small_and_large_are_not_compatible(self):
        self.assertFalse(are_production_families_compatible("中小型XS", "中大型XS"))
        self.assertFalse(are_production_families_compatible("中小型AUTO", "中大型AUTO"))

    def test_legacy_aliases_use_the_same_groups(self):
        self.assertTrue(are_production_families_compatible("大机XS", "大机AUTO"))
        self.assertFalse(are_production_families_compatible("小机XS", "大机XS"))


if __name__ == "__main__":
    unittest.main()
