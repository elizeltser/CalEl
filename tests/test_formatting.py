import csv
import io
import json
import unittest

from calel.core import calculator as calc
from calel.utils import formatting as fmt


class ParseEng(unittest.TestCase):
    def test_values(self):
        cases = {
            "4.7k": 4700, "4k7": 4700, "2R2": 2.2, "10u": 1e-5, "10µ": 1e-5, "100nF": 1e-7,
            "1.8V": 1.8, "1meg": 1e6, "1M": 1e6, "5m": 5e-3, "1e-6": 1e-6, "10 kHz": 1e4,
            "-3.3": -3.3, "60dB": 60, "  12 ": 12, "1,000": 1000, "47pF": 47e-12,
        }
        for text, expected in cases.items():
            self.assertAlmostEqual(fmt.parse_eng(text), expected, msg=text, delta=abs(expected) * 1e-12)
        self.assertEqual(fmt.parse_eng("10u"), 1e-5)  # no float noise
        self.assertEqual(fmt.parse_eng(3), 3.0)

    def test_invalid(self):
        for text in ("", "abc", "1.2.3", "5x", "k"):
            with self.assertRaises(ValueError, msg=text):
                fmt.parse_eng(text)


class FormatEng(unittest.TestCase):
    def test_values(self):
        cases = [
            ((5600, "Ω"), "5.6kΩ"), ((100, "Ω"), "100Ω"), ((1.02e3, "Ω"), "1.02kΩ"),
            ((1e-8, "F"), "10nF"), ((4.7e-12, "F"), "4.7pF"), ((1e6, "Ω"), "1MΩ"),
            ((999.96, "Ω"), "1kΩ"), ((-1.5e-3, "A"), "-1.5mA"), ((0, "V"), "0V"),
        ]
        for (value, unit), expected in cases:
            self.assertEqual(fmt.format_eng(value, unit), expected)
        self.assertEqual(fmt.format_eng(1.80234, "V", 4), "1.802V")

    def test_round_trip(self):
        for v in (4.7e3, 1.5e-9, 330.0, 2.2e6):
            self.assertAlmostEqual(fmt.parse_eng(fmt.format_eng(v)), v)

    def test_pct(self):
        self.assertEqual(fmt.format_pct(0.0123), "+1.23%")
        self.assertEqual(fmt.format_pct(-0.0005), "-0.050%")
        self.assertEqual(fmt.format_pct(0), "0.00%")
        self.assertEqual(fmt.format_pct(0.065, signed=False), "6.50%")

    def test_classify(self):
        self.assertEqual(fmt.classify(0.001, 5), "good")
        self.assertEqual(fmt.classify(-0.03, 5), "ok")
        self.assertEqual(fmt.classify(0.06, 5), "poor")
        self.assertEqual(fmt.classify(0, 0), "good")


class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = [
            calc.divider(1.8, 5, calc.Options(solutions=3)),
            calc.opamp(100, options=calc.Options(series="E96", solutions=3)),
            calc.opamp(-10, inverting=True, options=calc.Options(solutions=3)),
            calc.rc(10e-6, "rise_1090", calc.Options(solutions=3)),
        ]

    def test_every_format(self):
        for r in self.results:
            for f in fmt.FORMATS:
                text = fmt.render(r, f)
                self.assertTrue(text.strip(), (r.kind, f))

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            fmt.render(self.results[0], "xml")

    def test_table(self):
        text = fmt.render_table(self.results[0])
        self.assertIn("Target: 1.8V from 5V rail", text)
        self.assertIn("Series: E24 (±5% tolerance)", text)
        self.assertIn("R_high", text)
        self.assertNotIn("\033[", text)
        colored = fmt.render_table(self.results[0], fmt.Style(True))
        self.assertIn("\033[", colored)

    def test_inverting_gain_is_negative(self):
        text = fmt.render_table(self.results[2])
        self.assertIn("-10 V/V", text)
        self.assertIn("R_input", text)

    def test_rc_extra_metric_column(self):
        headers = [c.header for c in fmt.columns(self.results[3])]
        self.assertEqual(headers[:5], ["Rank", "R", "C", "f_c", "tau"])
        self.assertIn("t_r(10-90%)", headers)

    def test_json(self):
        doc = json.loads(fmt.render_json(self.results[0]))
        self.assertEqual(doc["calculator"], "divider")
        self.assertEqual(len(doc["solutions"]), 3)
        sol = doc["solutions"][0]
        self.assertEqual(sol["components"][0]["name"], "R_high")
        self.assertIn("tolerance_rss_pct", sol)

    def test_csv(self):
        rows = list(csv.DictReader(io.StringIO(fmt.render_csv(self.results[0]))))
        self.assertEqual(len(rows), 3)
        self.assertIn("R_high_ohm", rows[0])
        self.assertEqual(float(rows[0]["R_high_ohm"]), self.results[0].best.value("R_high"))

    def test_raw(self):
        lines = fmt.render_raw(self.results[0]).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(lines[0].split()), 4)

    def test_markdown(self):
        lines = fmt.render_markdown(self.results[0]).splitlines()
        self.assertTrue(any(line.startswith("| Rank |") for line in lines))

    def test_latex_escaping(self):
        text = fmt.render_latex(self.results[3])
        self.assertIn(r"\begin{tabular}", text)
        self.assertIn(r"\%", text)
        self.assertIn(r"$\Omega$", text)
        self.assertNotIn("Ω", text)
        self.assertNotIn("±", text)

    def test_report_shows_working(self):
        text = fmt.render_report(self.results[0])
        for needle in ("Formula:", "Ideal:", "sensitivity", "worst case", "RSS"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
