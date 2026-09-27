"""Smoke tests for the tkinter GUI (skipped when no display is available)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    HAVE_DISPLAY = True
except Exception:  # no tkinter or no display
    HAVE_DISPLAY = False


@unittest.skipUnless(HAVE_DISPLAY, "needs a display for tkinter")
class GUITests(unittest.TestCase):
    def setUp(self):
        from calel.gui.app import CalElApp

        self.dir = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"CALEL_CONFIG": str(Path(self.dir.name) / "c.json")})
        self.env.start()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = CalElApp(self.root)

    def tearDown(self):
        self.root.destroy()
        self.env.stop()
        self.dir.cleanup()

    def test_tabs_calculate(self):
        for tab in self.app.tabs:
            tab.calculate()
            self.assertIsNotNone(tab.result, tab.title)
            self.assertEqual(len(tab.tree.get_children()), 5)
            self.assertIn("best", tab.tree.item("1")["tags"])

    def test_invalid_input_is_highlighted(self):
        tab = self.app.tabs[0]
        tab.fields["target"].var.set("abc")
        tab.calculate()
        self.assertTrue(str(tab.fields["target"].widget.cget("style")).startswith("Invalid."))
        self.assertIn("not a number", tab.message.cget("text"))
        tab.fields["target"].var.set("1.8")
        tab.calculate()
        self.assertFalse(str(tab.fields["target"].widget.cget("style")).startswith("Invalid."))

    def test_sort_and_copy(self):
        tab = self.app.tabs[0]
        tab.calculate()
        tab.sort_by("R_high_ohm")
        values = [tab.result.solutions[int(i) - 1].value("R_high") for i in tab.tree.get_children()]
        self.assertEqual(values, sorted(values))
        tab.tree.selection_set("1")
        tab.copy_row()
        self.assertIn("R_high=", self.root.clipboard_get())

    def test_themes_fonts_and_examples(self):
        for theme in ("dark", "high_contrast", "light"):
            self.app.apply_theme(theme, save=False)
        self.app.apply_font_size(14, save=False)
        self.app.load_example(1, {"topology": "inv", "gain": "60", "units": "dB"})
        self.assertEqual(self.app.tabs[1].result.kind, "opamp_inv")


if __name__ == "__main__":
    unittest.main()
