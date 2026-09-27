import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from calel.utils import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "sub" / "config.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_gives_defaults(self):
        self.assertEqual(config.load(self.path), config.Config())

    def test_round_trip(self):
        cfg = config.Config(series="E96", tolerance=1.0, theme="dark", font_size=13)
        config.save(cfg, self.path)
        self.assertEqual(config.load(self.path), cfg)

    def test_bad_and_unknown_values_are_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"series": "E12", "solutions": "many", "bogus": 1,
                                         "impedance": 4700}))
        cfg = config.load(self.path)
        self.assertEqual(cfg.series, "E12")
        self.assertEqual(cfg.solutions, 5)
        self.assertEqual(cfg.impedance, 4700.0)

    def test_corrupt_file(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        self.assertEqual(config.load(self.path), config.Config())

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"CALEL_CONFIG": str(self.path)}):
            self.assertEqual(config.config_path(), self.path)

    def test_to_options(self):
        opts = config.Config(series="E12", prefer_low_values=True).to_options()
        self.assertEqual(opts.series, "E12")
        self.assertTrue(opts.prefer_low_values)


if __name__ == "__main__":
    unittest.main()
