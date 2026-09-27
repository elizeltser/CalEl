import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from calel.cli import parser


class CLITests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        env = {"CALEL_CONFIG": str(Path(self.dir.name) / "none.json"), "NO_COLOR": "1"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = parser.main(list(argv))
            except SystemExit as exc:  # argparse errors / --help
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_divider(self):
        code, out, _ = self.run_cli("--targ_v", "1.8", "--rail_v", "5", "--series", "E24",
                                    "--tolerance", "1", "--solutions", "5")
        self.assertEqual(code, 0)
        self.assertIn("Target: 1.8V from 5V rail", out)
        self.assertIn("Series: E24 (±1% tolerance)", out)
        self.assertEqual(sum(line[:2] in ("1.", "2.", "3.", "4.", "5.") for line in out.splitlines()), 5)

    def test_all_targets(self):
        for argv in (["--opamp_non_inv_vv", "100"], ["--opamp_non_inv_dB", "40"],
                     ["--opamp_inv_vv", "-10"], ["--opamp_inv_dB", "60"],
                     ["--targ_corner_hz", "1k"], ["--targ_corner_rad", "6283"],
                     ["--targ_tau", "1m"], ["--targ_rc", "1m"], ["--targ_rise_1090", "10e-6"],
                     ["--targ_rise_2080", "10u"]):
            code, out, err = self.run_cli(*argv)
            self.assertEqual(code, 0, (argv, err))
            self.assertIn("Rank", out)

    def test_json_output(self):
        code, out, _ = self.run_cli("--opamp_non_inv_vv", "47", "--series", "E96", "-f", "json", "-n", "3")
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(len(doc["solutions"]), 3)
        self.assertEqual(doc["options"]["series"], "E96")

    def test_output_file(self):
        path = Path(self.dir.name) / "out.csv"
        code, out, err = self.run_cli("--targ_corner_hz", "10k", "-f", "csv", "-o", str(path))
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("wrote csv", err)
        self.assertTrue(path.read_text(encoding="utf-8").startswith("rank,R_ohm,C_F"))

    def test_prefer_low_values(self):
        code, out, _ = self.run_cli("--targ_corner_hz", "10000", "--series", "E24",
                                    "--prefer_low_values", "-f", "raw", "-n", "1")
        self.assertEqual(code, 0)
        r, c = map(float, out.split()[:2])
        self.assertLessEqual(c, 20e-12)

    def test_errors_are_friendly(self):
        code, _, err = self.run_cli("--targ_v", "6", "--rail_v", "5")
        self.assertEqual(code, 2)
        self.assertIn("error:", err)
        self.assertIn("hint:", err)
        self.assertNotIn("Traceback", err)

        code, _, err = self.run_cli("--targ_v", "1.8")
        self.assertEqual(code, 2)
        self.assertIn("--rail_v", err)

        code, _, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("no target", err)

    def test_argparse_validation(self):
        code, _, err = self.run_cli("--targ_v", "abc", "--rail_v", "5")
        self.assertEqual(code, 2)
        self.assertIn("cannot parse", err)
        code, _, err = self.run_cli("--targ_v", "1", "--rail_v", "5", "--series", "E7")
        self.assertEqual(code, 2)
        code, _, err = self.run_cli("--targ_v", "1", "--opamp_non_inv_vv", "5")
        self.assertEqual(code, 2)
        self.assertIn("not allowed", err)

    def test_help_has_series_and_examples(self):
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        for needle in ("E-series standards", "E192", "Examples", "calel --targ_v 1.8 --rail_v 5",
                       "Example output"):
            self.assertIn(needle, out)

    def test_list_series(self):
        code, out, _ = self.run_cli("--list_series", "E12")
        self.assertEqual(code, 0)
        self.assertIn("1 1.2 1.5 1.8 2.2 2.7 3.3 3.9 4.7 5.6 6.8 8.2", out)
        code, out, _ = self.run_cli("--list_series")
        self.assertIn("E96", out)
        code, _, err = self.run_cli("--list_series", "E5")
        self.assertEqual(code, 2)

    def test_color_always(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": ""}):
            code, out, _ = self.run_cli("--targ_v", "1.8", "--rail_v", "5", "--color", "always")
        self.assertIn("\033[", out)

    def test_config_defaults_apply(self):
        cfg_path = Path(os.environ["CALEL_CONFIG"])
        cfg_path.write_text(json.dumps({"series": "E96", "solutions": 2}))
        code, out, _ = self.run_cli("--targ_v", "1.8", "--rail_v", "5")
        self.assertIn("E96", out)
        self.assertNotIn("\n3.", out)


if __name__ == "__main__":
    unittest.main()
