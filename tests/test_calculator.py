import math
import unittest

from calel.core import calculator as calc
from calel.core import e_series


def in_series(value, series):
    return e_series.mantissa_of(value) in e_series.SERIES[series]


class ToleranceAnalysis(unittest.TestCase):
    def test_product(self):
        stack = calc.tolerance_analysis(lambda a, b: a * b, [2.0, 3.0], [1.0, 1.0], ["a", "b"])
        self.assertAlmostEqual(stack["nominal"], 6.0)
        self.assertAlmostEqual(stack["wc"], 1.01 ** 2 - 1)
        self.assertAlmostEqual(stack["rss"], math.sqrt(2) * 0.01, places=8)
        self.assertAlmostEqual(stack["sensitivities"]["a"], 1.0, places=6)
        self.assertAlmostEqual(stack["max"], 6 * 1.01 ** 2)
        self.assertAlmostEqual(stack["min"], 6 * 0.99 ** 2)

    def test_zero_tolerance(self):
        stack = calc.tolerance_analysis(lambda a, b: a / b, [2.0, 3.0], [0.0, 0.0], ["a", "b"])
        self.assertEqual(stack["wc"], 0)
        self.assertEqual(stack["rss"], 0)


class Divider(unittest.TestCase):
    def test_basic(self):
        r = calc.divider(1.8, 5, calc.Options(series="E24", solutions=5))
        self.assertEqual(len(r.solutions), 5)
        self.assertEqual([s.rank for s in r.solutions], [1, 2, 3, 4, 5])
        for s in r.solutions:
            rh, rl = s.value("R_high"), s.value("R_low")
            self.assertTrue(in_series(rh, "E24") and in_series(rl, "E24"))
            self.assertAlmostEqual(s.achieved, 5 * rl / (rh + rl))
            self.assertAlmostEqual(s.error, s.achieved / 1.8 - 1)
        errors = [abs(s.error) for s in r.solutions]
        self.assertEqual(errors, sorted(errors))
        self.assertLess(errors[0], 0.005)

    def test_tolerance_matches_analytic_rss(self):
        r = calc.divider(1.8, 5, calc.Options(series="E24", tolerance=1))
        s = r.best
        k = s.achieved / 5
        self.assertAlmostEqual(s.tol_rss, (1 - k) * math.sqrt(2) * 0.01, places=6)
        self.assertLess(s.spec_min, s.achieved)
        self.assertGreater(s.spec_max, s.achieved)

    def test_no_decade_duplicates(self):
        r = calc.divider(2.5, 5, calc.Options(series="E12", solutions=10))
        ratios = [round(s.value("R_high") / s.value("R_low"), 9) for s in r.solutions]
        self.assertEqual(len(ratios), len(set(ratios)))
        self.assertEqual(r.best.error, 0)
        self.assertEqual(r.best.value("R_high"), r.best.value("R_low"))
        # of 1k/1k, 4.7k/4.7k, 10k/10k ... the total nearest 10 kΩ wins
        self.assertEqual(r.best.value("R_high"), 4.7e3)

    def test_impedance_and_prefer_low(self):
        hi = calc.divider(2.5, 5, calc.Options(series="E12", impedance=200e3)).best
        self.assertEqual(hi.value("R_high"), 100e3)
        low = calc.divider(2.5, 5, calc.Options(series="E12", prefer_low_values=True, r_min=100)).best
        self.assertEqual(low.value("R_high"), 100)

    def test_negative_rail(self):
        r = calc.divider(-1.8, -5)
        self.assertLess(r.best.achieved, 0)
        self.assertLess(abs(r.best.error), 0.005)

    def test_invalid(self):
        for target, rail in ((6, 5), (0, 5), (-1, 5), (1, 0)):
            with self.assertRaises(calc.CalculationError):
                calc.divider(target, rail)

    def test_warns_when_series_too_coarse(self):
        r = calc.divider(3.3, 12, calc.Options(series="E6", tolerance=1))
        self.assertTrue(any("exceeds" in w for w in r.warnings))
        self.assertTrue(any("E12" in w for w in r.warnings))


class OpAmp(unittest.TestCase):
    def test_non_inverting_exact(self):
        r = calc.opamp(11, options=calc.Options(series="E24"))
        self.assertEqual(r.kind, "opamp_non_inv")
        self.assertEqual(r.best.error, 0)
        self.assertEqual(r.best.value("R_feedback") / r.best.value("R_ground"), 10)
        self.assertAlmostEqual(r.best.metrics["gain_db"], 20 * math.log10(11))

    def test_non_inverting_db(self):
        r = calc.opamp(20, db=True)
        self.assertAlmostEqual(r.target, 10)

    def test_inverting(self):
        r = calc.opamp(-10, inverting=True)
        self.assertEqual(r.kind, "opamp_inv")
        self.assertEqual(r.target, 10)
        self.assertEqual(r.best.error, 0)
        self.assertEqual(r.best.components[1].name, "R_input")
        # inverting sensitivities are exactly ±1
        self.assertAlmostEqual(r.best.sensitivities["R_feedback"], 1, places=6)
        self.assertAlmostEqual(r.best.sensitivities["R_input"], -1, places=6)

    def test_non_inverting_sensitivity(self):
        r = calc.opamp(11, options=calc.Options(series="E24"))
        self.assertAlmostEqual(r.best.sensitivities["R_feedback"], 10 / 11, places=6)

    def test_inverting_low_input_impedance_warning(self):
        r = calc.opamp(60, inverting=True, db=True)
        self.assertTrue(any("input impedance" in w for w in r.warnings))

    def test_invalid(self):
        with self.assertRaises(calc.CalculationError):
            calc.opamp(1)
        with self.assertRaises(calc.CalculationError):
            calc.opamp(-5)
        with self.assertRaises(calc.CalculationError):
            calc.opamp(-3, db=True)


class RC(unittest.TestCase):
    def test_corner(self):
        r = calc.rc(1000, "corner_hz", calc.Options(series="E12"))
        for s in r.solutions:
            rr, cc = s.value("R"), s.value("C")
            self.assertAlmostEqual(s.achieved, 1 / (2 * math.pi * rr * cc))
            self.assertAlmostEqual(s.metrics["tau"], rr * cc)
        self.assertLess(abs(r.best.error), 0.05)

    def test_target_kinds(self):
        tau = 4.7e-6
        cases = {
            "tau": tau,
            "corner_rad": 1 / tau,
            "corner_hz": 1 / (2 * math.pi * tau),
            "rise_1090": math.log(9) * tau,
            "rise_2080": math.log(4) * tau,
        }
        for kind, target in cases.items():
            r = calc.rc(target, kind, calc.Options(series="E6"))
            self.assertAlmostEqual(r.inputs["tau"], tau, msg=kind)
            self.assertAlmostEqual(r.best.error, 0, places=9, msg=kind)
            self.assertAlmostEqual(r.best.metrics["tau"], tau, msg=kind)

    def test_rise_time_approximation(self):
        self.assertAlmostEqual(calc.LN9, 2.197, places=3)
        self.assertAlmostEqual(calc.LN4, 1.386, places=3)

    def test_impedance_and_prefer_low(self):
        r = calc.rc(1e-3, "tau", calc.Options(series="E6", impedance=1e3))
        self.assertEqual(r.best.value("R"), 1e3)
        low = calc.rc(1e-3, "tau", calc.Options(series="E6", prefer_low_values=True))
        self.assertEqual(low.best.value("R"), 1e6)  # largest R -> smallest C
        self.assertAlmostEqual(low.best.value("C"), 1e-9)

    def test_separate_cap_series_and_tolerance(self):
        opts = calc.Options(series="E96", tolerance=1, cap_series="E6", cap_tolerance=10)
        r = calc.rc(1000, "corner_hz", opts)
        c = r.best.components[1]
        self.assertTrue(in_series(c.value, "E6"))
        self.assertEqual(c.tolerance, 10)
        self.assertAlmostEqual(r.best.tol_wc, 1 / (0.99 * 0.90) - 1, places=9)

    def test_invalid(self):
        with self.assertRaises(calc.CalculationError):
            calc.rc(-1)
        with self.assertRaises(calc.CalculationError):
            calc.rc(1, "phase")
        with self.assertRaises(calc.CalculationError):
            calc.rc(1e-15, "tau")  # needs < 10 Ω · 10 pF


class Options(unittest.TestCase):
    def test_defaults(self):
        o = calc.Options()
        self.assertEqual(o.r_tol, 5.0)
        self.assertEqual(o.c_series, "E24")
        self.assertEqual(calc.Options(series="E96").r_tol, 1.0)

    def test_validation(self):
        for kwargs in ({"series": "E7"}, {"solutions": 0}, {"tolerance": 150},
                       {"rank": "cheap"}, {"impedance": 0}):
            with self.assertRaises(ValueError, msg=kwargs):
                calc.Options(**kwargs).validate()

    def test_solution_count(self):
        self.assertEqual(len(calc.divider(1.8, 5, calc.Options(solutions=2)).solutions), 2)

    def test_preferred_ranking_favours_common_values(self):
        r = calc.divider(1.8, 5, calc.Options(series="E24", rank="preferred", solutions=3))
        prefs = [s.preference for s in r.solutions if abs(s.error) <= 0.05]
        self.assertEqual(prefs, sorted(prefs))


if __name__ == "__main__":
    unittest.main()
