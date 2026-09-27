"""tkinter GUI for CalEl.

Three calculator tabs (resistor divider, op-amp feedback, RC filter) share a
common base class that handles input validation, debounced real-time
recalculation, the sortable/colour-coded results table, charts and the
summary cards.  :class:`CalElApp` owns the window: menus, status bar,
themes, font scaling, settings, help, export, printing and sessions.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

from calel import __version__
from calel.core import calculator, e_series
from calel.core.matcher import RANK_CRITERIA, RANK_HELP
from calel.utils import config as config_mod
from calel.utils import formatting
from calel.utils.formatting import classify, format_eng, format_metric, format_pct, parse_eng

DEBOUNCE_MS = 300
SERIES_CHOICES = list(e_series.SERIES_ORDER)
TOLERANCE_PRESETS = ["Series default", "0.1", "0.5", "1", "2", "5", "10", "20"]
RAIL_PRESETS = ["1.8", "2.5", "3.3", "5", "9", "12", "15", "24", "48"]
E_SERIES_URL = "https://en.wikipedia.org/wiki/E_series_of_preferred_numbers"
EXPORT_TYPES = [
    ("CSV", "*.csv"), ("JSON", "*.json"), ("Markdown", "*.md"),
    ("LaTeX", "*.tex"), ("Text report", "*.txt"),
]
EXPORT_FORMATS = {".csv": "csv", ".json": "json", ".md": "markdown", ".tex": "latex", ".txt": "report"}

THEMES = {
    "light": dict(
        bg="#f3f3f3", fg="#1b1b1b", field="#ffffff", border="#b8b8b8", alt="#e6e6e6",
        select="#cce0ff", select_fg="#000000", accent="#1f6feb", target="#d1242f",
        good="#d7f0d7", ok="#fff1bf", poor="#f6d0d0", invalid="#f6c4c4",
        error_fg="#b3261e", grid="#c4c4c4", muted="#666666",
    ),
    "dark": dict(
        bg="#1e1f22", fg="#e6e6e6", field="#2b2d31", border="#44474d", alt="#2b2d31",
        select="#35507a", select_fg="#ffffff", accent="#58a6ff", target="#ff7b72",
        good="#1f3d2a", ok="#4a4020", poor="#4d2323", invalid="#6b2a2a",
        error_fg="#ff8a80", grid="#3a3c40", muted="#9a9a9a",
    ),
    "high_contrast": dict(
        bg="#000000", fg="#ffffff", field="#000000", border="#ffffff", alt="#1a1a1a",
        select="#ffff00", select_fg="#000000", accent="#00ffff", target="#ffff00",
        good="#005000", ok="#6b5c00", poor="#8b0000", invalid="#8b0000",
        error_fg="#ff6666", grid="#808080", muted="#dddddd",
    ),
}
THEME_LABELS = {"light": "Light", "dark": "Dark", "high_contrast": "High contrast"}


# --------------------------------------------------------------------------
# Small widgets
# --------------------------------------------------------------------------


class Tooltip:
    """Hover tooltip for any widget."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 500):
        self.widget, self.text, self.delay = widget, text, delay
        self._after = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self):
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tip, text=self.text, justify="left", wraplength=360,
            background="#ffffe0", foreground="#000000", relief="solid", borderwidth=1,
            font="TkTooltipFont", padx=6, pady=3,
        ).pack()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


class ErrorChart(tk.Canvas):
    """Horizontal bar chart of nominal error with tolerance whiskers."""

    def __init__(self, master, app: "CalElApp"):
        super().__init__(master, height=180, highlightthickness=0)
        self.app = app
        self.result: Optional[calculator.Result] = None
        self.selected = 1
        self.bind("<Configure>", lambda e: self.redraw())

    def plot(self, result, selected: int = 1):
        self.result, self.selected = result, selected
        self.redraw()

    def redraw(self):
        t = self.app.colors
        self.delete("all")
        self.configure(background=t["field"])
        w, h = self.winfo_width(), self.winfo_height()
        r = self.result
        if not r or not r.solutions or w < 60 or h < 60:
            self.create_text(w / 2, h / 2, text="No results", fill=t["muted"])
            return
        tol = r.options.r_tol
        spans = [abs(s.error) * 100 for s in r.solutions]
        for s in r.solutions:
            spans += [abs(s.spec_min / r.target - 1) * 100, abs(s.spec_max / r.target - 1) * 100]
        xmax = max(spans + [tol]) * 1.1 or 1
        left, right, top, bottom = 44, 16, 12, 26
        pw, ph = w - left - right, h - top - bottom

        def x(pct):
            return left + (pct + xmax) / (2 * xmax) * pw

        # component tolerance band and axes
        self.create_rectangle(x(-tol), top, x(tol), top + ph, fill=t["alt"], outline="")
        for pct in _nice_ticks(xmax, max(3, pw // 45)):
            self.create_line(x(pct), top, x(pct), top + ph, fill=t["grid"])
            self.create_text(x(pct), top + ph + 4, text=f"{pct:+g}%" if pct else "0", anchor="n",
                             fill=t["muted"], font="TkSmallCaptionFont")
        self.create_line(x(0), top, x(0), top + ph, fill=t["fg"])
        n = len(r.solutions)
        row = ph / n
        for i, s in enumerate(r.solutions):
            yc = top + row * (i + 0.5)
            bar = max(3, min(18, row * 0.5))
            color = {"good": "#2da44e", "ok": "#d4a72c", "poor": "#cf222e"}[classify(s.error, tol)]
            lo = (min(s.spec_min, s.spec_max) / r.target - 1) * 100
            hi = (max(s.spec_min, s.spec_max) / r.target - 1) * 100
            self.create_line(x(lo), yc, x(hi), yc, fill=t["muted"], width=1)
            for end in (lo, hi):
                self.create_line(x(end), yc - bar / 2, x(end), yc + bar / 2, fill=t["muted"])
            self.create_rectangle(x(0), yc - bar / 2, x(s.error * 100), yc + bar / 2,
                                  fill=color, outline=t["accent"] if s.rank == self.selected else color,
                                  width=2 if s.rank == self.selected else 1)
            self.create_text(left - 6, yc, text=f"#{s.rank}", anchor="e", fill=t["fg"],
                             font="TkSmallCaptionFont")


def _nice_ticks(limit: float, max_ticks: int) -> List[float]:
    """Symmetric 1-2-5 ticks within ±limit, at most ``max_ticks`` of them."""
    raw = 2 * limit / max_ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    n = int(limit // step)
    return [round(i * step, 10) for i in range(-n, n + 1)]


class ResponsePlot(tk.Canvas):
    """Bode magnitude plot of a first-order RC low-pass (target vs chosen)."""

    def __init__(self, master, app: "CalElApp"):
        super().__init__(master, height=180, highlightthickness=0)
        self.app = app
        self.result: Optional[calculator.Result] = None
        self.solution: Optional[calculator.Solution] = None
        self.bind("<Configure>", lambda e: self.redraw())

    def plot(self, result, solution):
        self.result, self.solution = result, solution
        self.redraw()

    def redraw(self):
        t = self.app.colors
        self.delete("all")
        self.configure(background=t["field"])
        w, h = self.winfo_width(), self.winfo_height()
        if not self.result or not self.solution or w < 80 or h < 60:
            self.create_text(w / 2, h / 2, text="No results", fill=t["muted"])
            return
        fc_t = 1 / (2 * math.pi * self.result.inputs["tau"])
        f_lo, f_hi = fc_t / 100, fc_t * 100
        db_lo, db_hi = -42.0, 3.0
        left, right, top, bottom = 44, 16, 12, 26
        pw, ph = w - left - right, h - top - bottom

        def px(f):
            return left + (math.log10(f / f_lo) / math.log10(f_hi / f_lo)) * pw

        def py(db):
            return top + (db_hi - db) / (db_hi - db_lo) * ph

        for decade in range(5):
            f = f_lo * 10 ** decade
            self.create_line(px(f), top, px(f), top + ph, fill=t["grid"])
            self.create_text(px(f), top + ph + 4, text=format_eng(f, "Hz"), anchor="n",
                             fill=t["muted"], font="TkSmallCaptionFont")
        for db in (0, -10, -20, -30, -40):
            self.create_line(left, py(db), left + pw, py(db), fill=t["grid"])
            self.create_text(left - 4, py(db), text=f"{db}", anchor="e", fill=t["muted"],
                             font="TkSmallCaptionFont")
        self.create_line(left, py(-3), left + pw, py(-3), fill=t["muted"], dash=(2, 3))
        self.create_text(left + pw - 2, py(-3) - 2, text="-3 dB", anchor="se", fill=t["muted"],
                         font="TkSmallCaptionFont")

        def curve(fc, **kw):
            pts = []
            for i in range(121):
                f = f_lo * (f_hi / f_lo) ** (i / 120)
                pts += [px(f), py(-10 * math.log10(1 + (f / fc) ** 2))]
            self.create_line(*pts, **kw)

        r, c = self.solution.value("R"), self.solution.value("C")
        tr, tc = self.result.options.r_tol / 100, self.result.options.c_tol / 100
        fc = 1 / (2 * math.pi * r * c)
        for fx in (1 / (2 * math.pi * r * (1 + tr) * c * (1 + tc)),
                   1 / (2 * math.pi * r * (1 - tr) * c * (1 - tc))):
            curve(fx, fill=t["muted"], width=1)
        curve(fc_t, fill=t["target"], width=2, dash=(6, 4))
        curve(fc, fill=t["accent"], width=2)
        self.create_line(px(fc_t), top, px(fc_t), top + ph, fill=t["target"], dash=(2, 3))
        # legend in the empty lower-left corner (a low-pass is flat there)
        legend = [
            (t["target"], f"target f_c = {format_eng(fc_t, 'Hz', 4)} (dashed)"),
            (t["accent"], f"#{self.solution.rank}: f_c = {format_eng(fc, 'Hz', 4)}"),
            (t["muted"], "grey: tolerance extremes"),
        ]
        line_h = tkfont.nametofont("TkSmallCaptionFont").metrics("linespace") + 2
        for i, (color, text) in enumerate(legend):
            self.create_text(left + 6, top + ph - 4 - (len(legend) - 1 - i) * line_h,
                             anchor="sw", fill=color, text=text, font="TkSmallCaptionFont")


# --------------------------------------------------------------------------
# Calculator tabs
# --------------------------------------------------------------------------


class Field:
    """One validated input: a Tk variable, its widget and a parser."""

    def __init__(self, key, label, var, widget, parse, hint, primary=False):
        self.key, self.label, self.var, self.widget = key, label, var, widget
        self.parse, self.hint, self.primary = parse, hint, primary
        self.base_style = widget.cget("style") or widget.winfo_class()


def _positive(label: str, example: str) -> Callable[[str], float]:
    def parse(text: str) -> float:
        try:
            value = parse_eng(text)
        except ValueError:
            raise ValueError(f"{label}: '{text}' is not a number — try something like {example}") from None
        if value <= 0:
            raise ValueError(f"{label} must be greater than zero")
        return value
    return parse


def _number(label: str, example: str) -> Callable[[str], float]:
    def parse(text: str) -> float:
        try:
            return parse_eng(text)
        except ValueError:
            raise ValueError(f"{label}: '{text}' is not a number — try something like {example}") from None
    return parse


def _tolerance(label: str) -> Callable[[str], Optional[float]]:
    def parse(text: str) -> Optional[float]:
        text = text.strip().lstrip("±").rstrip("%").strip()
        if not text or text.lower().startswith("series"):
            return None
        try:
            value = parse_eng(text)
        except ValueError:
            raise ValueError(f"{label}: '{text}' is not a percentage — pick a preset such as 1 or 5") from None
        if not 0 <= value < 100:
            raise ValueError(f"{label} must be between 0 and 100 %")
        return value
    return parse


class CalculatorTab(ttk.Frame):
    """Shared layout and behaviour for the three calculators."""

    title = ""
    has_response_plot = False

    def __init__(self, master, app: "CalElApp"):
        super().__init__(master, padding=6)
        self.app = app
        self.fields: Dict[str, Field] = {}
        self.extra_vars: Dict[str, tk.Variable] = {}
        self.result: Optional[calculator.Result] = None
        self._after = None
        self._sort = (None, False)
        self._rows: List[calculator.Solution] = []
        self._build()
        self.reset_defaults()
        for f in self.fields.values():
            f.var.trace_add("write", lambda *_: self.schedule())
        for v in self.extra_vars.values():
            v.trace_add("write", lambda *_: self.schedule())

    # ----- layout -------------------------------------------------------
    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=(4, 4, 10, 4))
        paned.add(left, weight=0)
        self.inputs = ttk.LabelFrame(left, text="Target", padding=8)
        self.inputs.pack(fill="x")
        self.inputs.columnconfigure(1, weight=1)
        self.build_inputs(self.inputs)

        common = ttk.LabelFrame(left, text="Components", padding=8)
        common.pack(fill="x", pady=(8, 0))
        common.columnconfigure(1, weight=1)
        self._build_common(common)

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(8, 0))
        calc = ttk.Button(buttons, text="Calculate  ⏎", command=self.calculate)
        calc.pack(side="left", fill="x", expand=True)
        Tooltip(calc, "Recalculate now (Enter). Results also update automatically as you type.")
        reset = ttk.Button(buttons, text="Reset", command=self.reset_defaults)
        reset.pack(side="left", padx=(6, 0))
        Tooltip(reset, "Restore this tab's inputs to your default settings.")

        self.message = ttk.Label(left, text="", wraplength=260, justify="left",
                                 style="Error.TLabel")
        self.message.pack(fill="x", pady=(8, 0))

        right = ttk.PanedWindow(paned, orient="vertical")
        paned.add(right, weight=1)

        table_frame = ttk.Frame(right)
        right.add(table_frame, weight=3)
        self.heading = ttk.Label(table_frame, text="", style="Heading.TLabel")
        self.heading.pack(fill="x", pady=(0, 4))
        tree_holder = ttk.Frame(table_frame)
        tree_holder.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_holder, show="headings", selectmode="browse", height=8)
        ysb = ttk.Scrollbar(tree_holder, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(tree_holder, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        tree_holder.columnconfigure(0, weight=1)
        tree_holder.rowconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Button-3>", self._popup)
        self.tree.bind("<Control-c>", lambda e: self.copy_row())
        Tooltip(self.tree, "Click a column heading to sort. Right-click (or Ctrl+C) to copy.\n"
                           "Green: error within ¼ of the tolerance · yellow: within the "
                           "tolerance · red: outside it. Bold row = best match.")
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copy row", command=self.copy_row, accelerator="Ctrl+C")
        self.menu.add_command(label="Copy component values", command=self.copy_values)
        self.menu.add_separator()
        self.menu.add_command(label="Copy table (Markdown)", command=lambda: self.copy_all("markdown"))
        self.menu.add_command(label="Copy table (CSV)", command=lambda: self.copy_all("csv"))
        self.menu.add_command(label="Copy detailed report", command=lambda: self.copy_all("report"))
        self.app.register_menu(self.menu)

        viz = ttk.Frame(right)
        right.add(viz, weight=2)
        self.cards = ttk.Frame(viz)
        self.cards.pack(fill="x", pady=(6, 4))
        self.charts = ttk.Notebook(viz)
        self.charts.pack(fill="both", expand=True)
        self.error_chart = ErrorChart(self.charts, self.app)
        self.charts.add(self.error_chart, text="Error & tolerance")
        self.response = None
        if self.has_response_plot:
            self.response = ResponsePlot(self.charts, self.app)
            self.charts.add(self.response, text="Gain vs frequency")
            self.charts.select(self.response)

    def _build_common(self, frame):
        self.add_field(frame, "series", "Series", "combo", _series_parser,
                       "E-series for resistors. Finer series (E96, E192) match more closely "
                       "but cost more.", values=SERIES_CHOICES, readonly=True)
        self.add_field(frame, "tolerance", "Tolerance %", "combo", _tolerance("Tolerance"),
                       "Resistor tolerance used for the stack-up. 'Series default' uses the "
                       "series' nominal tolerance (E24 = 5 %, E96 = 1 % …).",
                       values=TOLERANCE_PRESETS)
        self.build_extra_common(frame)
        row = frame.grid_size()[1]
        ttk.Label(frame, text="Solutions").grid(row=row, column=0, sticky="w", pady=2)
        self.extra_vars["solutions"] = tk.IntVar(value=5)
        holder = ttk.Frame(frame)
        holder.grid(row=row, column=1, sticky="ew", pady=2)
        scale = ttk.Scale(holder, from_=1, to=20, orient="horizontal",
                          command=lambda v: self.extra_vars["solutions"].set(int(float(v))))
        scale.pack(side="left", fill="x", expand=True)
        self._solutions_scale = scale
        ttk.Label(holder, textvariable=self.extra_vars["solutions"], width=3).pack(side="left")
        Tooltip(scale, "How many alternative solutions to list (1–20).")

        self.add_field(frame, "rank", "Rank by", "combo", _rank_parser,
                       "\n".join(f"{k}: {v}" for k, v in RANK_HELP.items()),
                       values=list(RANK_CRITERIA), readonly=True)
        self.add_field(frame, "impedance", "Impedance Ω", "entry", _positive("Impedance", "10k"),
                       self.impedance_hint)
        self.extra_vars["prefer_low"] = tk.BooleanVar(value=False)
        row = frame.grid_size()[1]
        chk = ttk.Checkbutton(frame, text="Prefer low values", variable=self.extra_vars["prefer_low"])
        chk.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        Tooltip(chk, self.prefer_low_hint)

    impedance_hint = "Preferred total network resistance; decides between 10k/5.6k and 100k/56k."
    prefer_low_hint = "Choose the lowest-value variant of each ratio instead of the one nearest the impedance."

    def add_field(self, frame, key, label, kind, parse, hint, values=None, readonly=False,
                  primary=False, spin=None):
        row = frame.grid_size()[1]
        lbl = ttk.Label(frame, text=label)
        lbl.grid(row=row, column=0, sticky="w", pady=2, padx=(0, 6))
        var = tk.StringVar()
        if kind == "combo":
            widget = ttk.Combobox(frame, textvariable=var, values=values or [], width=14,
                                  state="readonly" if readonly else "normal")
        elif kind == "spin":
            lo, hi, step = spin
            widget = ttk.Spinbox(frame, textvariable=var, from_=lo, to=hi, increment=step, width=14)
        else:
            widget = ttk.Entry(frame, textvariable=var, width=16)
        widget.grid(row=row, column=1, sticky="ew", pady=2)
        field = Field(key, label, var, widget, parse, hint, primary)
        self.fields[key] = field
        Tooltip(widget, hint)
        Tooltip(lbl, hint)
        widget.bind("<FocusIn>", lambda e: self.app.set_hint(hint), add="+")
        widget.bind("<FocusOut>", lambda e: self.app.set_hint(""), add="+")
        return field

    # ----- subclass hooks -----------------------------------------------
    def build_inputs(self, frame):
        raise NotImplementedError

    def build_extra_common(self, frame):
        pass

    def compute(self, values: dict, opts: calculator.Options) -> calculator.Result:
        raise NotImplementedError

    def tab_defaults(self) -> dict:
        return {}

    # ----- state ----------------------------------------------------------
    def reset_defaults(self):
        cfg = self.app.config
        state = {
            "series": cfg.series,
            "tolerance": "Series default" if cfg.tolerance is None else f"{cfg.tolerance:g}",
            "solutions": cfg.solutions,
            "rank": cfg.rank,
            "impedance": format_eng(cfg.impedance),
            "prefer_low": cfg.prefer_low_values,
        }
        state.update(self.tab_defaults())
        self.set_state(state)

    def get_state(self) -> dict:
        state = {k: f.var.get() for k, f in self.fields.items()}
        state.update({k: v.get() for k, v in self.extra_vars.items()})
        return state

    def set_state(self, state: dict):
        for key, value in state.items():
            if key in self.fields:
                self.fields[key].var.set(str(value))
            elif key in self.extra_vars:
                var = self.extra_vars[key]
                if isinstance(var, tk.BooleanVar):
                    var.set(bool(value))
                elif isinstance(var, tk.IntVar):
                    var.set(int(value))
                else:
                    var.set(value)
        if "solutions" in state:
            self._solutions_scale.set(int(state["solutions"]))
        self.schedule()

    # ----- calculation ---------------------------------------------------
    def schedule(self):
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(DEBOUNCE_MS, self.calculate)
        self.app.set_status("Waiting for input…")

    def _mark(self, field: Field, invalid: bool):
        base = field.base_style
        field.widget.configure(style=f"Invalid.{base}" if invalid else base)

    def calculate(self):
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        values, errors = {}, []
        for f in self.fields.values():
            try:
                values[f.key] = f.parse(f.var.get())
                self._mark(f, False)
            except ValueError as exc:
                self._mark(f, True)
                errors.append(str(exc))
        if errors:
            self._show_error(errors[0], "Fix the highlighted field(s); results update automatically.")
            return
        opts = calculator.Options(
            series=values["series"],
            tolerance=values["tolerance"],
            solutions=int(self.extra_vars["solutions"].get()),
            rank=values["rank"],
            impedance=values["impedance"],
            prefer_low_values=bool(self.extra_vars["prefer_low"].get()),
            r_min=self.app.config.r_min,
            r_max=self.app.config.r_max,
            c_min=self.app.config.c_min,
            c_max=self.app.config.c_max,
        )
        self.app.set_status("Calculating…")
        self.update_idletasks()
        start = time.perf_counter()
        try:
            result = self.compute(values, opts)
        except calculator.CalculationError as exc:
            for f in self.fields.values():
                if f.primary:
                    self._mark(f, True)
            self._show_error(str(exc), exc.hint)
            return
        except ValueError as exc:
            self._show_error(str(exc), "")
            return
        elapsed = (time.perf_counter() - start) * 1000
        self.result = result
        self._sort = (None, False)
        self._rows = list(result.solutions)
        self.message.configure(
            text="\n".join(f"⚠ {w}" for w in result.warnings), style="Warn.TLabel")
        self.heading.configure(text="\n".join(formatting.title_lines(result)))
        self._fill_tree(select_rank=1)
        n = len(result.solutions)
        self.app.set_status(f"✓ {n} solution{'s' * (n != 1)} in {elapsed:.1f} ms")

    def _show_error(self, message: str, hint: str):
        text = f"✖ {message}"
        if hint:
            text += f"\n→ {hint}"
        self.message.configure(text=text, style="Error.TLabel")
        self.app.set_status("Error: " + message, error=True)

    # ----- table ---------------------------------------------------------
    def _fill_tree(self, select_rank: Optional[int] = None):
        r = self.result
        tree = self.tree
        tree.delete(*tree.get_children())
        if not r:
            return
        self._cols = formatting.columns(r)
        tree["columns"] = [c.key for c in self._cols]
        font = tkfont.nametofont("TkDefaultFont")
        for c in self._cols:
            arrow = ""
            if self._sort[0] == c.key:
                arrow = " ▼" if self._sort[1] else " ▲"
            tree.heading(c.key, text=c.header + arrow, command=lambda k=c.key: self.sort_by(k))
            sample = max([c.header + "  ▲"] + [c.text(s) for s in self._rows], key=len)
            width = font.measure(sample) + 18
            tree.column(c.key, width=width, minwidth=width, anchor="e", stretch=False)
        tol = r.options.r_tol
        for s in self._rows:
            tags = [classify(s.error, tol)]
            if s.rank == 1:
                tags.append("best")
            tree.insert("", "end", iid=str(s.rank), values=[c.text(s) for c in self._cols],
                        tags=tags)
        if select_rank is not None and tree.exists(str(select_rank)):
            tree.selection_set(str(select_rank))
            tree.see(str(select_rank))

    def sort_by(self, key: str):
        col = next(c for c in self._cols if c.key == key)
        reverse = not self._sort[1] if self._sort[0] == key else False
        self._sort = (key, reverse)
        if key == "error_pct":
            self._rows.sort(key=lambda s: abs(s.error), reverse=reverse)
        else:
            self._rows.sort(key=col.raw, reverse=reverse)
        sel = self.selected()
        self._fill_tree(select_rank=sel.rank if sel else None)

    def selected(self) -> Optional[calculator.Solution]:
        if not self.result:
            return None
        sel = self.tree.selection()
        rank = int(sel[0]) if sel else 1
        for s in self.result.solutions:
            if s.rank == rank:
                return s
        return None

    def _on_select(self):
        sol = self.selected()
        if not sol or not self.result:
            return
        self._fill_cards(sol)
        self.error_chart.plot(self.result, sol.rank)
        if self.response:
            self.response.plot(self.result, sol)

    def _fill_cards(self, sol: calculator.Solution):
        for child in self.cards.winfo_children():
            child.destroy()
        r = self.result
        sign = -1 if r.kind == "opamp_inv" else 1

        def card(title, big, small, tip):
            frame = ttk.LabelFrame(self.cards, text=title, padding=(8, 2))
            frame.pack(side="left", fill="y", padx=(0, 6))
            ttk.Label(frame, text=big, style="Card.TLabel").pack(anchor="w")
            ttk.Label(frame, text=small, style="Muted.TLabel").pack(anchor="w")
            Tooltip(frame, tip)

        for c in sol.components:
            card(c.name, format_eng(c.value, c.unit),
                 f"{e_series.coarsest_series(c.value)} · ±{c.tolerance:g}%",
                 "Component value; the series shown is the coarsest one that contains it.")
        card(f"{r.metric} (#{sol.rank})", format_metric(sign * sol.achieved, r.unit),
             f"error {format_pct(sol.error)}", "Nominal value achieved with these parts.")
        lo, hi = sorted((sign * sol.spec_min, sign * sol.spec_max))
        card("Tolerance stack", f"±{format_pct(sol.tol_wc, False)}",
             f"RSS ±{format_pct(sol.tol_rss, False)} · {format_metric(lo, r.unit)} … "
             f"{format_metric(hi, r.unit)}",
             "Worst case: every part at its tolerance limit at once.\n"
             "RSS: statistical root-sum-square of independent part errors.")

    # ----- clipboard ------------------------------------------------------
    def _popup(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def copy_row(self):
        sol = self.selected()
        if sol:
            text = ", ".join(f"{c.header}={c.text(sol)}" for c in self._cols[1:])
            self.app.copy(text, "row")

    def copy_values(self):
        sol = self.selected()
        if sol:
            self.app.copy("\t".join(format_eng(c.value, c.unit) for c in sol.components), "values")

    def copy_all(self, fmt: str):
        if self.result:
            self.app.copy(formatting.render(self.result, fmt), fmt)


def _series_parser(text: str) -> str:
    try:
        return e_series.normalize_series(text)
    except ValueError:
        raise ValueError(f"Series: choose one of {', '.join(SERIES_CHOICES)}") from None


def _rank_parser(text: str) -> str:
    if text not in RANK_CRITERIA:
        raise ValueError(f"Rank by: choose one of {', '.join(RANK_CRITERIA)}")
    return text


class DividerTab(CalculatorTab):
    title = "Resistor Divider"
    impedance_hint = ("Preferred total resistance R_high + R_low. Higher = less bias current, "
                      "lower = stiffer output.")
    prefer_low_hint = "Use the lowest resistances that give each ratio (stiffest, most current)."

    def build_inputs(self, frame):
        self.add_field(frame, "target", "Output voltage V", "spin", _number("Output voltage", "1.8"),
                       "Desired divider output voltage (e.g. 1.8, 1.8V, 900m).",
                       primary=True, spin=(-1000, 1000, 0.1))
        self.add_field(frame, "rail", "Rail voltage V", "combo", _number("Rail voltage", "5"),
                       "Supply voltage feeding the divider. Pick a preset or type any value.",
                       values=RAIL_PRESETS, primary=True)
        ttk.Label(frame, text="V_out = V_rail · R_low / (R_high + R_low)",
                  style="Muted.TLabel").grid(columnspan=2, sticky="w", pady=(4, 0))

    def tab_defaults(self):
        return {"target": "1.8", "rail": "5"}

    def compute(self, values, opts):
        return calculator.divider(values["target"], values["rail"], opts)


class OpAmpTab(CalculatorTab):
    title = "Op-Amp Feedback"
    impedance_hint = "Preferred R_feedback + R_ground/R_input (the load on the op-amp output)."
    prefer_low_hint = "Use the lowest resistances for each ratio (lowest noise, highest current)."

    def build_inputs(self, frame):
        self.extra_vars["topology"] = tk.StringVar(value="non_inv")
        row = ttk.Frame(frame)
        row.grid(columnspan=2, sticky="w", pady=(0, 4))
        for text, val in (("Non-inverting", "non_inv"), ("Inverting", "inv")):
            rb = ttk.Radiobutton(row, text=text, value=val, variable=self.extra_vars["topology"])
            rb.pack(side="left", padx=(0, 10))
            Tooltip(rb, "Non-inverting: G = 1 + Rf/Rg (G > 1).\nInverting: G = −Rf/Rin.")
        self.add_field(frame, "gain", "Gain", "spin", _number("Gain", "100"),
                       "Target closed-loop gain. Units are chosen below; the inverting sign "
                       "is implied.", primary=True, spin=(-1e6, 1e6, 1))
        self.add_field(frame, "units", "Units", "combo", _units_parser,
                       "Gain units: V/V (linear) or dB (20·log10).", values=["V/V", "dB"],
                       readonly=True)
        self.formula = ttk.Label(frame, text="", style="Muted.TLabel")
        self.formula.grid(columnspan=2, sticky="w", pady=(4, 0))

    def tab_defaults(self):
        return {"gain": "100", "units": "V/V", "topology": "non_inv"}

    def compute(self, values, opts):
        inverting = self.extra_vars["topology"].get() == "inv"
        self.formula.configure(text="G = −R_feedback / R_input" if inverting
                               else "G = 1 + R_feedback / R_ground")
        return calculator.opamp(values["gain"], inverting, values["units"] == "dB", opts)


def _units_parser(text: str) -> str:
    if text not in ("V/V", "dB"):
        raise ValueError("Units: choose V/V or dB")
    return text


RC_KINDS = {
    "Corner frequency (Hz)": "corner_hz",
    "Corner frequency (rad/s)": "corner_rad",
    "Time constant τ = RC (s)": "tau",
    "Rise time 10–90 % (s)": "rise_1090",
    "Rise time 20–80 % (s)": "rise_2080",
}


class RCTab(CalculatorTab):
    title = "RC Filter"
    has_response_plot = True
    impedance_hint = "Preferred resistance R; the capacitor is chosen to match."
    prefer_low_hint = "Choose the smallest capacitor (physically smallest part) for each R·C."

    def build_inputs(self, frame):
        self.add_field(frame, "kind", "Specify as", "combo", _kind_parser,
                       "How the time constant is given:\n"
                       "f_c = 1/(2πRC) · ω_c = 1/RC · τ = RC\n"
                       "t_r(10–90%) = ln9·RC ≈ 2.2RC · t_r(20–80%) = ln4·RC ≈ 1.4RC",
                       values=list(RC_KINDS), readonly=True)
        self.add_field(frame, "value", "Value", "entry", _positive("Value", "1k, 10u or 159e-6"),
                       "Target value in the units above; SI prefixes allowed (10k, 4.7u, 100n).",
                       primary=True)

    def build_extra_common(self, frame):
        self.add_field(frame, "cap_series", "Cap series", "combo", _cap_series_parser,
                       "E-series for capacitors (ceramics are commonly E6/E12).",
                       values=["Same as R"] + SERIES_CHOICES, readonly=True)
        self.add_field(frame, "cap_tolerance", "Cap tolerance %", "combo",
                       _tolerance("Cap tolerance"),
                       "Capacitor tolerance for the stack-up; 'Series default' uses the cap "
                       "series' nominal tolerance.", values=TOLERANCE_PRESETS)

    def tab_defaults(self):
        cfg = self.app.config
        return {
            "kind": "Corner frequency (Hz)",
            "value": "1k",
            "cap_series": cfg.cap_series or "Same as R",
            "cap_tolerance": "Series default" if cfg.cap_tolerance is None
            else f"{cfg.cap_tolerance:g}",
        }

    def compute(self, values, opts):
        opts.cap_series = values["cap_series"]
        opts.cap_tolerance = values["cap_tolerance"]
        return calculator.rc(values["value"], values["kind"], opts)


def _kind_parser(text: str) -> str:
    if text not in RC_KINDS:
        raise ValueError("Specify as: pick an option from the list")
    return RC_KINDS[text]


def _cap_series_parser(text: str) -> Optional[str]:
    return None if text.startswith("Same") else _series_parser(text)


# --------------------------------------------------------------------------
# Dialogs
# --------------------------------------------------------------------------


class SettingsDialog(tk.Toplevel):
    """Default series/tolerance/ranking and component range preferences."""

    def __init__(self, app: "CalElApp"):
        super().__init__(app.root)
        self.app = app
        self.title("CalEl settings")
        self.transient(app.root)
        self.configure(background=app.colors["bg"])
        cfg = app.config
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self.vars: Dict[str, tk.Variable] = {}
        rows = [
            ("series", "Default series", cfg.series, SERIES_CHOICES,
             "Series every tab starts with."),
            ("tolerance", "Default tolerance %",
             "Series default" if cfg.tolerance is None else f"{cfg.tolerance:g}",
             TOLERANCE_PRESETS, "Resistor tolerance used unless changed per tab."),
            ("cap_series", "Default cap series", cfg.cap_series or "Same as R",
             ["Same as R"] + SERIES_CHOICES, "Capacitor series for the RC tab."),
            ("solutions", "Solutions", str(cfg.solutions), None, "Number of solutions to list."),
            ("rank", "Ranking", cfg.rank, list(RANK_CRITERIA),
             "'preferred' favours common values (E6/E12) among in-tolerance matches."),
            ("impedance", "Impedance Ω", format_eng(cfg.impedance), None,
             "Preferred network resistance."),
            ("r_min", "Min resistor Ω", format_eng(cfg.r_min), None, "Smallest resistor considered."),
            ("r_max", "Max resistor Ω", format_eng(cfg.r_max), None, "Largest resistor considered."),
            ("c_min", "Min capacitor F", format_eng(cfg.c_min), None, "Smallest capacitor considered."),
            ("c_max", "Max capacitor F", format_eng(cfg.c_max), None, "Largest capacitor considered."),
        ]
        for i, (key, label, value, choices, tip) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=2, padx=(0, 8))
            var = tk.StringVar(value=value)
            if choices:
                w = ttk.Combobox(body, textvariable=var, values=choices, width=16,
                                 state="readonly" if key not in ("tolerance",) else "normal")
            else:
                w = ttk.Entry(body, textvariable=var, width=18)
            w.grid(row=i, column=1, sticky="ew", pady=2)
            Tooltip(w, tip)
            self.vars[key] = var
        self.vars["prefer_low"] = tk.BooleanVar(value=cfg.prefer_low_values)
        ttk.Checkbutton(body, text="Prefer low values", variable=self.vars["prefer_low"]).grid(
            row=len(rows), column=0, columnspan=2, sticky="w", pady=4)
        self.error = ttk.Label(body, text="", style="Error.TLabel", wraplength=300)
        self.error.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w")
        btns = ttk.Frame(body)
        btns.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Save", command=self.save).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self.save())
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass  # modality is a nicety; the dialog still works without a grab

    def save(self):
        cfg = self.app.config
        v = {k: var.get() for k, var in self.vars.items()}
        try:
            new = dict(
                series=_series_parser(v["series"]),
                tolerance=_tolerance("Default tolerance")(v["tolerance"]),
                cap_series=_cap_series_parser(v["cap_series"]),
                solutions=int(v["solutions"]),
                rank=_rank_parser(v["rank"]),
                impedance=_positive("Impedance", "10k")(v["impedance"]),
                r_min=_positive("Min resistor", "10")(v["r_min"]),
                r_max=_positive("Max resistor", "1M")(v["r_max"]),
                c_min=_positive("Min capacitor", "10p")(v["c_min"]),
                c_max=_positive("Max capacitor", "100u")(v["c_max"]),
                prefer_low_values=bool(v["prefer_low"]),
            )
            if not 1 <= new["solutions"] <= 50:
                raise ValueError("Solutions must be between 1 and 50")
            if new["r_min"] >= new["r_max"] or new["c_min"] >= new["c_max"]:
                raise ValueError("Minimum values must be smaller than maximum values")
        except ValueError as exc:
            self.error.configure(text=f"✖ {exc}")
            return
        for key, value in new.items():
            setattr(cfg, key, value)
        self.app.save_config()
        if messagebox.askyesno("Apply defaults", "Apply the new defaults to all tabs now?",
                               parent=self):
            for tab in self.app.tabs:
                tab.reset_defaults()
        else:
            for tab in self.app.tabs:
                tab.schedule()
        self.destroy()


HELP_OVERVIEW = f"""CalEl {__version__} — universal passive component calculator

CalEl finds standard E-series resistor and capacitor values for a target
specification and ranks several alternatives. Every tab recalculates as you
type; press Enter to recalculate immediately.

Tabs
  Resistor Divider   R_high and R_low for a target output voltage
  Op-Amp Feedback    R_feedback and R_ground/R_input for a target gain
  RC Filter          R and C for a corner frequency, time constant or rise time

Results table
  Click a heading to sort. Colours: green = error within ¼ of the tolerance,
  yellow = within the tolerance, red = outside it. The bold row is the best
  match. Right-click a row to copy it.

Numbers accept SI prefixes: 4.7k, 4k7, 100n, 10u, 1meg ('m' = milli, 'M' = mega).
"""

HELP_TOLERANCE = """Tolerance stack-up

Real parts deviate from their nominal value by up to their tolerance. The
achieved spec therefore varies too; CalEl reports two estimates:

Worst case (WC)
  Every component sits at the tolerance limit that hurts most, at the same
  time. CalEl evaluates all corners (each part at +tol and −tol), so the
  range shown is guaranteed for parts within tolerance.

Root-sum-square (RSS)
  A statistical estimate assuming independent, centred errors:
      RSS = √( Σ (S_i · tol_i)² )
  where S_i = ∂ln(f)/∂ln(x_i) is the relative sensitivity of the spec f
  to component x_i. RSS is typically ~70 % of the worst case for two parts.

Sensitivities
  Divider:        S = ±(1 − V_out/V_rail) → a divider close to the rail is
                  less sensitive to tolerance than one near ground.
  Non-inverting:  S = ±(G − 1)/G
  Inverting, RC:  S = ±1

"vs target" in the report adds the nominal error to the stack-up: the
largest deviation from what you asked for.
"""

HELP_SHORTCUTS = """Keyboard shortcuts

  Enter             Calculate now
  Ctrl+1 / 2 / 3    Switch calculator tab (Ctrl+Tab also works)
  Ctrl+S            Export results (CSV, JSON, Markdown, LaTeX, report)
  Ctrl+Shift+S      Save session (all inputs)
  Ctrl+O            Open session
  Ctrl+P            Print report
  Ctrl+C            Copy selected row (in the table)
  Ctrl+Shift+C      Copy table as Markdown
  Ctrl+= / Ctrl+-   Larger / smaller font      Ctrl+0  Reset font size
  Ctrl+D            Cycle theme (light → dark → high contrast)
  Ctrl+,            Settings
  F1                Help
  Ctrl+Q            Quit
"""

TUTORIALS = [
    (0, "Divider: 5 V → 1.8 V (E24)",
     "1. Enter the output and rail voltages.\n2. Keep E24 and 'Series default' tolerance.\n"
     "3. Look at Tol(WC): even a perfect ratio moves ±6.5 % with 5 % parts.",
     {"target": "1.8", "rail": "5", "series": "E24", "tolerance": "Series default"}),
    (0, "Divider: 12 V → 3.3 V, precision (E96 1 %)",
     "Finer series give near-exact ratios; the tolerance stack now dominates the error.",
     {"target": "3.3", "rail": "12", "series": "E96", "tolerance": "1"}),
    (1, "Non-inverting amplifier, G = 47 V/V (E96)",
     "G = 1 + Rf/Rg so the ideal ratio is 46. Compare the error column with the ±2 % stack.",
     {"topology": "non_inv", "gain": "47", "units": "V/V", "series": "E96"}),
    (1, "Inverting amplifier, 60 dB",
     "60 dB = 1000 V/V. Watch the warning about the input impedance (= R_input) and raise the "
     "impedance field to fix it.",
     {"topology": "inv", "gain": "60", "units": "dB", "series": "E24", "impedance": "1meg"}),
    (2, "RC low-pass at 10 kHz, smallest capacitor",
     "'Prefer low values' picks the smallest C for each ratio. Check the Gain vs frequency plot.",
     {"kind": "Corner frequency (Hz)", "value": "10k", "series": "E24", "prefer_low": True}),
    (2, "RC for a 10 µs rise time (10–90 %)",
     "t_r = ln(9)·RC ≈ 2.2·RC, so τ ≈ 4.55 µs.",
     {"kind": "Rise time 10–90 % (s)", "value": "10u", "series": "E12"}),
]


class HelpWindow(tk.Toplevel):
    def __init__(self, app: "CalElApp"):
        super().__init__(app.root)
        self.app = app
        self.title("CalEl help")
        self.geometry("720x560")
        self.configure(background=app.colors["bg"])
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        nb.add(self._text(nb, HELP_OVERVIEW), text="Overview")
        nb.add(self._series_page(nb), text="E-series")
        nb.add(self._text(nb, HELP_TOLERANCE), text="Tolerance stack-up")
        nb.add(self._tutorials(nb), text="Tutorials")
        nb.add(self._text(nb, HELP_SHORTCUTS), text="Shortcuts")
        self.bind("<Escape>", lambda e: self.destroy())

    def _text(self, master, content: str) -> tk.Text:
        t = self.app.colors
        text = tk.Text(master, wrap="word", padx=12, pady=10, relief="flat",
                       background=t["field"], foreground=t["fg"], font="TkFixedFont")
        text.insert("1.0", content)
        text.configure(state="disabled")
        return text

    def _series_page(self, master):
        frame = ttk.Frame(master, padding=8)
        lines = ["E-series of preferred numbers (IEC 60063)", "",
                 "Each series divides a decade into N geometric steps (ratio 10^(1/N)) so",
                 "that adjacent values overlap at the series tolerance. Values repeat in",
                 "every decade: 4.7 → 4.7 Ω, 47 Ω, 470 Ω, 4.7 kΩ …", ""]
        for name in SERIES_CHOICES:
            lines.append(f"{name:<5} {len(e_series.SERIES[name]):>3} values  "
                         f"±{e_series.NOMINAL_TOLERANCE[name]:g}%  {e_series.USE_CASE[name]}")
        lines += ["", "E6 values : " + "  ".join(f"{v:g}" for v in e_series.decade_values("E6")),
                  "E12 values: " + "  ".join(f"{v:g}" for v in e_series.decade_values("E12")),
                  "E24 values: " + "  ".join(f"{v:g}" for v in e_series.decade_values("E24")),
                  "", "Every E6 value is in E12, and every E12 value is in E24; likewise",
                  "E48 ⊂ E96 ⊂ E192. E24 and E96 share only a few values (1.0, 1.1, 1.3, 1.5 …)."]
        self._text(frame, "\n".join(lines)).pack(fill="both", expand=True)
        ttk.Button(frame, text="Open E-series reference (Wikipedia) ↗",
                   command=lambda: webbrowser.open(E_SERIES_URL)).pack(anchor="w", pady=(6, 0))
        return frame

    def _tutorials(self, master):
        outer = ttk.Frame(master, padding=8)
        ttk.Label(outer, text="Load an example into its calculator and follow the notes.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        for tab_index, title, notes, state in TUTORIALS:
            box = ttk.LabelFrame(outer, text=title, padding=6)
            box.pack(fill="x", pady=3)
            ttk.Label(box, text=notes, wraplength=560, justify="left").pack(side="left", fill="x",
                                                                          expand=True)
            ttk.Button(box, text="Try it",
                       command=lambda i=tab_index, s=state: self.app.load_example(i, s)).pack(
                side="right", padx=(8, 0))
        return outer


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------


class CalElApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = config_mod.load()
        self.colors = THEMES.get(self.config.theme, THEMES["light"])
        self.style = ttk.Style(root)
        self.native_theme = self.style.theme_use()
        if sys.platform.startswith("linux") or self.native_theme == "default":
            self.native_theme = "clam"
        self._menus: List[tk.Menu] = []
        self.root.title("CalEl — passive component calculator")
        self.root.geometry("1180x720")
        self.root.minsize(860, 560)

        self._build_menu()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.enable_traversal()
        self._build_statusbar()
        self.apply_font_size(self.config.font_size, save=False)
        self.tabs: List[CalculatorTab] = []
        for cls in (DividerTab, OpAmpTab, RCTab):
            tab = cls(self.notebook, self)
            self.notebook.add(tab, text=cls.title, underline=0)
            self.tabs.append(tab)
        self.apply_theme(self.config.theme, save=False)
        self._bind_keys()
        self._enable_drop()

    # ----- menus & keys --------------------------------------------------
    def register_menu(self, menu: tk.Menu):
        self._menus.append(menu)
        self._color_menu(menu)

    def _build_menu(self):
        bar = tk.Menu(self.root)
        self.register_menu(bar)
        m = tk.Menu(bar, tearoff=0)
        self.register_menu(m)
        m.add_command(label="Export results…", command=self.export, accelerator="Ctrl+S")
        m.add_command(label="Print report…", command=self.print_report, accelerator="Ctrl+P")
        m.add_separator()
        m.add_command(label="Open session…", command=self.open_session, accelerator="Ctrl+O")
        m.add_command(label="Save session…", command=self.save_session, accelerator="Ctrl+Shift+S")
        m.add_separator()
        m.add_command(label="Quit", command=self.root.destroy, accelerator="Ctrl+Q")
        bar.add_cascade(label="File", menu=m, underline=0)

        m = tk.Menu(bar, tearoff=0)
        self.register_menu(m)
        m.add_command(label="Copy selected row", command=lambda: self.current().copy_row())
        m.add_command(label="Copy table (Markdown)", command=lambda: self.current().copy_all("markdown"),
                      accelerator="Ctrl+Shift+C")
        m.add_command(label="Copy detailed report", command=lambda: self.current().copy_all("report"))
        m.add_separator()
        m.add_command(label="Settings…", command=lambda: SettingsDialog(self), accelerator="Ctrl+,")
        bar.add_cascade(label="Edit", menu=m, underline=0)

        m = tk.Menu(bar, tearoff=0)
        self.register_menu(m)
        self.theme_var = tk.StringVar(value=self.config.theme)
        for key, label in THEME_LABELS.items():
            m.add_radiobutton(label=label, value=key, variable=self.theme_var,
                              command=lambda k=key: self.apply_theme(k))
        m.add_command(label="Cycle theme", command=self.cycle_theme, accelerator="Ctrl+D")
        m.add_separator()
        m.add_command(label="Larger font", command=lambda: self.apply_font_size(self.config.font_size + 1),
                      accelerator="Ctrl+=")
        m.add_command(label="Smaller font", command=lambda: self.apply_font_size(self.config.font_size - 1),
                      accelerator="Ctrl+-")
        m.add_command(label="Reset font size", command=lambda: self.apply_font_size(10),
                      accelerator="Ctrl+0")
        bar.add_cascade(label="View", menu=m, underline=0)

        m = tk.Menu(bar, tearoff=0)
        self.register_menu(m)
        m.add_command(label="Help & tutorials", command=lambda: HelpWindow(self), accelerator="F1")
        m.add_command(label="E-series reference ↗", command=lambda: webbrowser.open(E_SERIES_URL))
        m.add_command(label="About CalEl", command=lambda: messagebox.showinfo(
            "About CalEl", f"CalEl {__version__}\nUniversal passive component calculator.\n"
                           "Pure Python, no dependencies.", parent=self.root))
        bar.add_cascade(label="Help", menu=m, underline=0)
        self.root.configure(menu=bar)

    def _bind_keys(self):
        r = self.root
        r.bind("<Return>", lambda e: self.current().calculate())
        r.bind("<KP_Enter>", lambda e: self.current().calculate())
        r.bind("<Control-s>", lambda e: self.export())
        r.bind("<Control-S>", lambda e: self.save_session())
        r.bind("<Control-o>", lambda e: self.open_session())
        r.bind("<Control-p>", lambda e: self.print_report())
        r.bind("<Control-q>", lambda e: r.destroy())
        r.bind("<Control-C>", lambda e: self.current().copy_all("markdown"))
        r.bind("<Control-d>", lambda e: self.cycle_theme())
        r.bind("<Control-comma>", lambda e: SettingsDialog(self))
        for key in ("<Control-equal>", "<Control-plus>", "<Control-KP_Add>"):
            r.bind(key, lambda e: self.apply_font_size(self.config.font_size + 1))
        for key in ("<Control-minus>", "<Control-KP_Subtract>"):
            r.bind(key, lambda e: self.apply_font_size(self.config.font_size - 1))
        r.bind("<Control-0>", lambda e: self.apply_font_size(10))
        r.bind("<F1>", lambda e: HelpWindow(self))
        for i in range(3):
            r.bind(f"<Control-Key-{i + 1}>", lambda e, i=i: self.notebook.select(i))

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, style="Status.TFrame", padding=(8, 2))
        bar.pack(side="bottom", fill="x")
        self.status = ttk.Label(bar, text="Ready", style="Status.TLabel")
        self.status.pack(side="left")
        self.hint = ttk.Label(bar, text="", style="StatusHint.TLabel", anchor="e")
        self.hint.pack(side="right", fill="x", expand=True)

    def current(self) -> CalculatorTab:
        return self.tabs[self.notebook.index(self.notebook.select())]

    def set_status(self, text: str, error: bool = False):
        self.status.configure(text=text, style="StatusError.TLabel" if error else "Status.TLabel")

    def set_hint(self, text: str):
        self.hint.configure(text=text.split("\n")[0])

    # ----- appearance ------------------------------------------------------
    def apply_theme(self, name: str, save: bool = True):
        name = name if name in THEMES else "light"
        self.colors = t = THEMES[name]
        s = self.style
        if name == "light" and self.native_theme != "clam":
            s.theme_use(self.native_theme)
        else:
            s.theme_use("clam")
            s.configure(".", background=t["bg"], foreground=t["fg"], fieldbackground=t["field"],
                        bordercolor=t["border"], lightcolor=t["bg"], darkcolor=t["bg"],
                        troughcolor=t["alt"], selectbackground=t["select"],
                        selectforeground=t["select_fg"], insertcolor=t["fg"],
                        arrowcolor=t["fg"], focuscolor=t["accent"])
            s.map(".", background=[("disabled", t["bg"]), ("active", t["alt"])],
                  foreground=[("disabled", t["muted"])])
            s.configure("TNotebook", background=t["bg"])
            s.configure("TNotebook.Tab", background=t["alt"], foreground=t["fg"], padding=(10, 4))
            s.map("TNotebook.Tab", background=[("selected", t["bg"])],
                  foreground=[("selected", t["fg"])])
            s.map("TCombobox", fieldbackground=[("readonly", t["field"])],
                  foreground=[("readonly", t["fg"])],
                  selectbackground=[("readonly", t["field"])],
                  selectforeground=[("readonly", t["fg"])])
            s.configure("TButton", background=t["alt"], padding=(10, 4))
            s.map("TButton", background=[("active", t["select"]), ("pressed", t["select"])],
                  foreground=[("active", t["select_fg"]), ("pressed", t["select_fg"])])
            s.configure("Treeview.Heading", background=t["alt"], foreground=t["fg"])
            s.map("Treeview.Heading", background=[("active", t["select"])])
            s.configure("TLabelframe.Label", background=t["bg"], foreground=t["fg"])
        for opt, val in (("background", t["field"]), ("foreground", t["fg"]),
                         ("selectBackground", t["select"]), ("selectForeground", t["select_fg"])):
            self.root.option_add(f"*TCombobox*Listbox.{opt}", val)
        s.configure("Treeview", background=t["field"], fieldbackground=t["field"],
                    foreground=t["fg"])
        s.map("Treeview", background=[("selected", t["select"])],
              foreground=[("selected", t["select_fg"])])
        for kind in ("TEntry", "TCombobox", "TSpinbox"):
            s.configure(f"Invalid.{kind}", fieldbackground=t["invalid"], foreground=t["fg"])
            s.map(f"Invalid.{kind}", fieldbackground=[("readonly", t["invalid"])])
        s.configure("Error.TLabel", foreground=t["error_fg"])
        s.configure("Warn.TLabel", foreground="#b08800" if name == "light" else "#e3b341")
        s.configure("Muted.TLabel", foreground=t["muted"])
        s.configure("Heading.TLabel", font=self.heading_font)
        s.configure("Card.TLabel", font=self.card_font)
        s.configure("Status.TFrame", background=t["alt"])
        s.configure("Status.TLabel", background=t["alt"], foreground=t["fg"])
        s.configure("StatusError.TLabel", background=t["alt"], foreground=t["error_fg"])
        s.configure("StatusHint.TLabel", background=t["alt"], foreground=t["muted"])
        self.root.configure(background=t["bg"])
        for menu in self._menus:
            self._color_menu(menu)
        for tab in getattr(self, "tabs", []):
            tab.tree.tag_configure("good", background=t["good"], foreground=t["fg"])
            tab.tree.tag_configure("ok", background=t["ok"], foreground=t["fg"])
            tab.tree.tag_configure("poor", background=t["poor"], foreground=t["fg"])
            tab.tree.tag_configure("best", font=self.bold_font)
            tab.error_chart.redraw()
            if tab.response:
                tab.response.redraw()
        self.theme_var.set(name)
        if save:
            self.config.theme = name
            self.save_config()

    def _color_menu(self, menu: tk.Menu):
        t = self.colors
        try:
            menu.configure(background=t["field"], foreground=t["fg"],
                           activebackground=t["select"], activeforeground=t["select_fg"])
        except tk.TclError:
            pass  # native menus (macOS) cannot be recoloured

    def cycle_theme(self):
        order = list(THEMES)
        self.apply_theme(order[(order.index(self.config.theme) + 1) % len(order)])

    def apply_font_size(self, size: int, save: bool = True):
        size = max(7, min(28, int(size)))
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                     "TkCaptionFont", "TkTooltipFont", "TkFixedFont", "TkIconFont"):
            try:
                tkfont.nametofont(name).configure(size=size)
            except tk.TclError:
                pass
        tkfont.nametofont("TkSmallCaptionFont").configure(size=max(7, size - 1))
        base = tkfont.nametofont("TkDefaultFont").actual()
        if not hasattr(self, "bold_font"):
            self.bold_font = tkfont.Font(self.root, **base)
            self.heading_font = tkfont.Font(self.root, **base)
            self.card_font = tkfont.Font(self.root, **base)
        self.bold_font.configure(family=base["family"], size=size, weight="bold")
        self.heading_font.configure(family=base["family"], size=size + 1, weight="bold")
        self.card_font.configure(family=base["family"], size=int(size * 1.5), weight="bold")
        linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        self.style.configure("Treeview", rowheight=int(linespace * 1.5))
        self.config.font_size = size
        for tab in getattr(self, "tabs", []):
            if tab.result:
                tab._fill_tree(select_rank=tab.selected().rank if tab.selected() else 1)
        if save:
            self.save_config()

    def save_config(self):
        try:
            config_mod.save(self.config)
        except OSError as exc:
            self.set_status(f"Could not save settings: {exc.strerror}", error=True)

    # ----- clipboard, export, print --------------------------------------
    def copy(self, text: str, what: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status(f"Copied {what} to clipboard")

    def _need_result(self) -> Optional[calculator.Result]:
        result = self.current().result
        if not result:
            messagebox.showwarning("No results", "Calculate a result first.", parent=self.root)
        return result

    def export(self):
        result = self._need_result()
        if not result:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export results", defaultextension=".csv",
            filetypes=EXPORT_TYPES, initialfile=f"calel_{result.kind}.csv")
        if not path:
            return
        fmt = EXPORT_FORMATS.get(os.path.splitext(path)[1].lower(), "report")
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(formatting.render(result, fmt) + "\n")
        except OSError as exc:
            messagebox.showerror("Export failed", f"Could not write the file:\n{exc.strerror}",
                                 parent=self.root)
            return
        self.set_status(f"Exported {fmt} to {path}")

    def print_report(self):
        result = self._need_result()
        if not result:
            return
        text = formatting.render_report(result)
        fd, path = tempfile.mkstemp(prefix="calel_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        try:
            if os.name == "nt":
                os.startfile(path, "print")  # type: ignore[attr-defined]
            else:
                cmd = shutil.which("lp") or shutil.which("lpr")
                if not cmd:
                    raise OSError("no 'lp' or 'lpr' command found")
                subprocess.run([cmd, path], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", b"") or str(exc)
            if isinstance(detail, bytes):
                detail = detail.decode(errors="replace")
            if messagebox.askyesno(
                "Printing unavailable",
                f"Could not send the report to a printer ({detail.strip()}).\n\n"
                "Save it as a text file instead?", parent=self.root):
                self.export()
            return
        self.set_status("Report sent to the printer")

    # ----- sessions --------------------------------------------------------
    def save_session(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save session", defaultextension=".json",
            filetypes=[("CalEl session", "*.json")], initialfile="calel_session.json")
        if not path:
            return
        data = {
            "calel_session": 1,
            "active_tab": self.notebook.index(self.notebook.select()),
            "tabs": {tab.title: tab.get_state() for tab in self.tabs},
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            messagebox.showerror("Save failed", exc.strerror or str(exc), parent=self.root)
            return
        self.set_status(f"Session saved to {path}")

    def open_session(self, path: Optional[str] = None):
        path = path or filedialog.askopenfilename(
            parent=self.root, title="Open session", filetypes=[("CalEl session", "*.json"),
                                                               ("All files", "*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "tabs" not in data:
                raise ValueError("not a CalEl session file")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot open session", f"{os.path.basename(path)}: {exc}",
                                 parent=self.root)
            return
        for tab in self.tabs:
            state = data["tabs"].get(tab.title)
            if isinstance(state, dict):
                tab.set_state(state)
        idx = data.get("active_tab", 0)
        if isinstance(idx, int) and 0 <= idx < len(self.tabs):
            self.notebook.select(idx)
        self.set_status(f"Opened session {os.path.basename(path)}")

    def _enable_drop(self):
        """Drag-and-drop session files, when the optional tkdnd extension exists."""
        try:
            self.root.tk.call("package", "require", "tkdnd")
            self.root.tk.call("tkdnd::drop_target", "register", self.root._w, "DND_Files")
        except tk.TclError:
            return

        def on_drop(data):
            files = self.root.tk.splitlist(data)
            if files:
                self.open_session(files[0])
            return "copy"

        cmd = self.root.register(on_drop)
        self.root.tk.call("bind", self.root._w, "<<Drop:DND_Files>>", cmd + " %D")

    def load_example(self, tab_index: int, state: dict):
        tab = self.tabs[tab_index]
        tab.reset_defaults()
        tab.set_state(state)
        self.notebook.select(tab_index)
        self.root.lift()
        tab.calculate()


def _enable_dpi_awareness():
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _enable_dpi_awareness()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"error: cannot start the GUI ({exc}); is a display available?", file=sys.stderr)
        return 1
    root.tk.call("tk", "appname", "calel")
    app = CalElApp(root)
    app.set_status("Ready — edit any field; results update automatically")
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
