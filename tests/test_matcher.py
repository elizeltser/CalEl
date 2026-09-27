import unittest
from types import SimpleNamespace as NS

from calel.core import matcher


class Nearest(unittest.TestCase):
    values = [1.0, 2.2, 4.7, 10.0]

    def test_between(self):
        self.assertEqual(matcher.nearest(self.values, 3.0), [2.2, 4.7])

    def test_exact(self):
        self.assertEqual(matcher.nearest(self.values, 4.7), [4.7])

    def test_outside(self):
        self.assertEqual(matcher.nearest(self.values, 0.1), [1.0])
        self.assertEqual(matcher.nearest(self.values, 99), [10.0])
        self.assertEqual(matcher.nearest([], 1), [])

    def test_closest_is_logarithmic(self):
        # 3.2 is linearly nearer 2.2 than 4.7 is... but log-wise nearer 2.2 too;
        # 3.3 is log-nearer 4.7 (ratio 1.42) than 2.2 (ratio 1.5).
        self.assertEqual(matcher.closest(self.values, 3.3), 4.7)
        self.assertEqual(matcher.closest(self.values, 3.1), 2.2)


class Candidates(unittest.TestCase):
    def test_ratio_candidates_contain_exact(self):
        vals = [1.0, 2.0, 5.0, 10.0]
        pairs = matcher.ratio_candidates(vals, vals, 2.5)
        self.assertIn((5.0, 2.0), pairs)

    def test_product_candidates_contain_exact(self):
        pairs = matcher.product_candidates([1.0, 2.0, 5.0], [1.0, 3.0], 6.0)
        self.assertIn((2.0, 3.0), pairs)

    def test_dedupe_keeps_best_score(self):
        pairs = [(10.0, 5.0), (100.0, 50.0), (1.0, 0.5)]
        kept = matcher.dedupe(pairs, matcher.ratio_key, lambda p: abs(p[0] - 100))
        self.assertEqual(kept, [(100.0, 50.0)])


class Ranking(unittest.TestCase):
    def sols(self):
        return [
            NS(name="a", error=0.001, tol_wc=0.05, worst_case_error=0.051, preference=6),
            NS(name="b", error=-0.0005, tol_wc=0.06, worst_case_error=0.0605, preference=4),
            NS(name="c", error=0.02, tol_wc=0.01, worst_case_error=0.03, preference=0),
            NS(name="d", error=0.004, tol_wc=0.05, worst_case_error=0.054, preference=0),
        ]

    def names(self, criterion, tol=1.0):
        return [s.name for s in matcher.rank_solutions(self.sols(), criterion, tol)]

    def test_error(self):
        self.assertEqual(self.names("error"), ["b", "a", "d", "c"])

    def test_worst_case(self):
        self.assertEqual(self.names("worst_case"), ["c", "a", "d", "b"])

    def test_preferred_only_within_tolerance(self):
        # c has preference 0 but a 2 % error (> 1 % tolerance), so it goes last.
        self.assertEqual(self.names("preferred"), ["d", "b", "a", "c"])

    def test_unknown(self):
        with self.assertRaises(ValueError):
            matcher.rank_solutions([], "cheapest", 1)


if __name__ == "__main__":
    unittest.main()
