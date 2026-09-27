import unittest

from calel.core import e_series


class ESeriesTables(unittest.TestCase):
    def test_counts(self):
        for name, count in (("E6", 6), ("E12", 12), ("E24", 24), ("E48", 48), ("E96", 96), ("E192", 192)):
            self.assertEqual(len(e_series.SERIES[name]), count)
            self.assertEqual(list(e_series.SERIES[name]), sorted(e_series.SERIES[name]))

    def test_known_values(self):
        self.assertIn(470, e_series.SERIES["E6"])
        self.assertIn(910, e_series.SERIES["E24"])
        self.assertIn(270, e_series.SERIES["E24"])  # not the formula value 2.6
        self.assertIn(499, e_series.SERIES["E96"])
        self.assertIn(976, e_series.SERIES["E96"])
        self.assertIn(920, e_series.SERIES["E192"])  # IEC exception, not 919
        self.assertNotIn(919, e_series.SERIES["E192"])

    def test_nesting(self):
        for small, big in (("E6", "E12"), ("E12", "E24"), ("E48", "E96"), ("E96", "E192")):
            self.assertTrue(set(e_series.SERIES[small]) <= set(e_series.SERIES[big]), (small, big))

    def test_values_in_range_is_exact(self):
        values = e_series.values_in_range("E12", 1e3, 10e3)
        self.assertEqual(values[0], 1000.0)
        self.assertEqual(values[-1], 10000.0)
        self.assertIn(4700.0, values)
        self.assertIn(4.7e-9, e_series.values_in_range("E6", 1e-9, 10e-9))

    def test_values_in_range_swapped_limits(self):
        self.assertEqual(e_series.values_in_range("E6", 100, 10), e_series.values_in_range("E6", 10, 100))

    def test_values_in_range_rejects_non_positive(self):
        with self.assertRaises(ValueError):
            e_series.values_in_range("E6", 0, 10)

    def test_normalize(self):
        self.assertEqual(e_series.normalize_series("e24"), "E24")
        self.assertEqual(e_series.normalize_series("96"), "E96")
        with self.assertRaises(ValueError):
            e_series.normalize_series("E13")

    def test_mantissa_and_preference(self):
        self.assertEqual(e_series.mantissa_of(4700), 470)
        self.assertEqual(e_series.mantissa_of(1.02e-7), 102)
        self.assertEqual(e_series.coarsest_series(1.2e3), "E12")
        self.assertEqual(e_series.coarsest_series(1.02e3), "E96")
        self.assertEqual(e_series.coarsest_series(1.25e3), "")
        self.assertLess(e_series.preference_score(4.7e3), e_series.preference_score(4.3e3))

    def test_nominal_tolerance(self):
        self.assertEqual(e_series.nominal_tolerance("E24"), 5.0)
        self.assertEqual(e_series.nominal_tolerance("e96"), 1.0)


if __name__ == "__main__":
    unittest.main()
