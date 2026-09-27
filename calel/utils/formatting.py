"""Engineering-notation parsing/formatting and result rendering.

Renderers turn a :class:`calel.core.calculator.Result` into text in one of
:data:`FORMATS`.  The column model (:func:`columns`) is shared by every
format and by the GUI so they always agree.
"""

import csv
import decimal
import io
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

FORMATS = ("table", "raw", "report", "csv", "json", "markdown", "latex")

# --------------------------------------------------------------------------
# Engineering notation
# --------------------------------------------------------------------------

_PREFIXES = {
    "f": -15, "p": -12, "n": -9, "u": -6, "µ": -6, "μ": -6, "m": -3,
    "": 0, "k": 3, "K": 3, "M": 6, "meg": 6, "MEG": 6, "G": 9, "T": 12,
}
_FORMAT_PREFIXES = {-15: "f", -12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T"}
_UNITS = r"(?:Ω|ohms?|Ohms?|R|V|Hz|hz|s|sec|F|dB|db|rad/s|%)?"
_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_ENG_RE = re.compile(
    rf"^\s*({_NUMBER})\s*(meg|MEG|[fpnuµμmkKMGT]?)\s*{_UNITS}\s*$"
)
# RKM / "4k7" notation: digits, a multiplier letter used as the decimal point, digits.
_RKM_RE = re.compile(r"^\s*(\d+)([pnuµμmkKMGRr])(\d+)\s*(?:Ω|F|ohms?)?\s*$")


def parse_eng(text) -> float:
    """Parse a number with an optional SI prefix and unit.

    Accepts ``"4.7k"``, ``"4k7"``, ``"10u"``, ``"100nF"``, ``"1.8V"``,
    ``"2R2"``, ``"1meg"`` and plain floats like ``"1e-6"``.  Note that ``m``
    is milli and ``M`` is mega.
    """
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace(",", "")
    if not s:
        raise ValueError("empty value")
    m = _RKM_RE.match(s)
    if m:
        whole, letter, frac = m.groups()
        exp = 0 if letter in "Rr" else _PREFIXES[letter]
        return _scaled(f"{whole}.{frac}", exp)
    m = _ENG_RE.match(s)
    if not m:
        raise ValueError(f"cannot parse '{text}' as a number (e.g. 4.7k, 100n, 1e-6)")
    number, prefix = m.groups()
    return _scaled(number, _PREFIXES[prefix])


def _scaled(number: str, exp: int) -> float:
    """``float(number) * 10**exp`` without binary rounding noise (10u == 1e-5)."""
    return float(decimal.Decimal(number).scaleb(exp))


def clean(x: float) -> float:
    """Round to 12 significant digits to hide float noise in exported data."""
    return float(f"{x:.12g}") if isinstance(x, float) else x


def format_eng(value: float, unit: str = "", digits: int = 3) -> str:
    """Format ``value`` with an SI prefix, e.g. ``format_eng(5600, "Ω") -> "5.6kΩ"``.

    ``digits`` is the number of significant digits; trailing zeros are
    dropped.
    """
    if value == 0 or not math.isfinite(value):
        return f"{value:g}{unit}"
    sign = "-" if value < 0 else ""
    v = abs(value)
    exp3 = int(math.floor(math.log10(v) / 3)) * 3
    exp3 = max(-15, min(12, exp3))
    mant = v / 10 ** exp3
    decimals = max(0, digits - 1 - int(math.floor(math.log10(mant))))
    text = f"{mant:.{decimals}f}"
    if float(text) >= 1000 and exp3 < 12:  # rounding carried into the next prefix
        exp3 += 3
        mant = v / 10 ** exp3
        decimals = max(0, digits - 1 - int(math.floor(math.log10(mant))))
        text = f"{mant:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{sign}{text}{_FORMAT_PREFIXES[exp3]}{unit}"


def format_pct(fraction: float, signed: bool = True) -> str:
    """Format a relative value (0.0123) as a percentage (``+1.23%``)."""
    pct = fraction * 100
    if pct == 0:
        return "0.00%"
    decimals = 3 if abs(pct) < 0.1 else 2
    return f"{pct:+.{decimals}f}%" if signed else f"{pct:.{decimals}f}%"


def format_metric(value: float, unit: str) -> str:
    """Format a primary metric value in its natural notation."""
    if unit == "V/V":
        return f"{value:.4g}"
    if unit == "dB":
        return f"{value:.2f}dB"
    return format_eng(value, unit, 4)


# --------------------------------------------------------------------------
# Match quality
# --------------------------------------------------------------------------


def classify(error: float, tolerance_pct: float) -> str:
    """``"good"``, ``"ok"`` or ``"poor"`` for a relative nominal error.

    good: within a quarter of the component tolerance; ok: within the
    tolerance; poor: outside it.
    """
    pct = abs(error) * 100
    if pct <= max(tolerance_pct / 4, 1e-9):
        return "good"
    if pct <= tolerance_pct:
        return "ok"
    return "poor"


# --------------------------------------------------------------------------
# Column model
# --------------------------------------------------------------------------


@dataclass
class Column:
    header: str  # human header, e.g. "V_out"
    key: str  # machine key with unit, e.g. "V_out_V"
    raw: Callable  # solution -> number
    text: Callable  # solution -> display string
    numeric: bool = True


def _unit_key(unit: str) -> str:
    return {"Ω": "ohm", "F": "F", "V": "V", "V/V": "VV", "Hz": "Hz", "s": "s", "rad/s": "rad_s"}.get(unit, unit)


def columns(result) -> List[Column]:
    """The table columns for ``result`` (shared by all output formats)."""
    cols = [Column("Rank", "rank", lambda s: s.rank, lambda s: f"{s.rank}.")]
    for i, comp in enumerate(result.solutions[0].components if result.solutions else []):
        cols.append(
            Column(
                comp.name,
                f"{comp.name}_{_unit_key(comp.unit)}",
                lambda s, i=i: s.components[i].value,
                lambda s, i=i: format_eng(s.components[i].value, s.components[i].unit),
            )
        )
    sign = -1 if result.kind == "opamp_inv" else 1
    if result.kind == "rc":
        cols.append(Column("f_c", "f_c_Hz", lambda s: s.metrics["f_c"],
                           lambda s: format_eng(s.metrics["f_c"], "Hz", 4)))
        cols.append(Column("tau", "tau_s", lambda s: s.metrics["tau"],
                           lambda s: format_eng(s.metrics["tau"], "s", 4)))
        if result.metric not in ("f_c", "tau"):
            cols.append(Column(result.metric, f"{result.metric}_{_unit_key(result.unit)}",
                               lambda s: s.achieved,
                               lambda s: format_metric(s.achieved, result.unit)))
    elif result.kind.startswith("opamp"):
        cols.append(Column("Gain(V/V)", "gain_VV", lambda s: sign * s.achieved,
                           lambda s: format_metric(sign * s.achieved, "V/V")))
        cols.append(Column("Gain(dB)", "gain_dB", lambda s: s.metrics["gain_db"],
                           lambda s: format_metric(s.metrics["gain_db"], "dB")))
    else:
        cols.append(Column(result.metric, f"{result.metric}_{_unit_key(result.unit)}",
                           lambda s: s.achieved,
                           lambda s: format_metric(s.achieved, result.unit)))
    cols += [
        Column("Error", "error_pct", lambda s: s.error * 100, lambda s: format_pct(s.error)),
        Column("Tol(WC)", "tol_wc_pct", lambda s: s.tol_wc * 100,
               lambda s: "±" + format_pct(s.tol_wc, signed=False)),
        Column("Tol(RSS)", "tol_rss_pct", lambda s: s.tol_rss * 100,
               lambda s: "±" + format_pct(s.tol_rss, signed=False)),
    ]
    return cols


# --------------------------------------------------------------------------
# Headings
# --------------------------------------------------------------------------

_KIND_NAMES = {
    "divider": "Resistor divider",
    "opamp_non_inv": "Non-inverting amplifier",
    "opamp_inv": "Inverting amplifier",
    "rc": "RC time constant",
}


def title_lines(result) -> List[str]:
    """Human-readable description of the target and series."""
    opts = result.options
    if result.kind == "divider":
        first = (f"Target: {format_metric(result.target, 'V')} from "
                 f"{format_metric(result.inputs['rail_v'], 'V')} rail")
    elif result.kind.startswith("opamp"):
        sign = "-" if result.kind == "opamp_inv" else ""
        db = 20 * math.log10(result.target)
        first = (f"{_KIND_NAMES[result.kind]}: Target Gain = {sign}{result.target:.4g} V/V "
                 f"({db:.2f} dB)")
    else:
        first = f"Target: {result.metric} = {format_metric(result.target, result.unit)}"
        if result.metric != "tau":
            first += f"  (τ = {format_eng(result.inputs['tau'], 's', 4)})"
    lines = [first]
    if result.kind == "rc":
        lines.append(f"Series: R {opts.r_series} (±{opts.r_tol:g}%), "
                     f"C {opts.c_series} (±{opts.c_tol:g}%)")
    else:
        lines.append(f"Series: {opts.r_series} (±{opts.r_tol:g}% tolerance)")
    return lines


# --------------------------------------------------------------------------
# ANSI colour
# --------------------------------------------------------------------------


class Style:
    """Minimal ANSI styling that degrades to plain text when disabled."""

    CODES = {"good": "32", "ok": "33", "poor": "31", "bold": "1", "dim": "2",
             "warn": "33", "error": "1;31", "head": "1;36"}

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def __call__(self, text: str, style: str) -> str:
        if not self.enabled or style not in self.CODES:
            return text
        return f"\033[{self.CODES[style]}m{text}\033[0m"


def color_supported(stream=None, mode: str = "auto") -> bool:
    """Whether to emit ANSI colour for ``mode`` (auto/always/never)."""
    if mode == "always":
        return True
    if mode == "never" or os.environ.get("NO_COLOR"):
        return False
    stream = stream or sys.stdout
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if os.name == "nt":
        return _enable_windows_vt()
    return True


def _enable_windows_vt() -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


# --------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------


def render(result, fmt: str = "table", style: Optional[Style] = None) -> str:
    """Render ``result`` in output format ``fmt`` (one of :data:`FORMATS`)."""
    style = style or Style(False)
    if fmt not in FORMATS:
        raise ValueError(f"unknown format '{fmt}' (choose from {', '.join(FORMATS)})")
    if fmt == "table":
        return render_table(result, style)
    if fmt == "report":
        return render_report(result, style)
    return {
        "raw": render_raw,
        "csv": render_csv,
        "json": render_json,
        "markdown": render_markdown,
        "latex": render_latex,
    }[fmt](result)


def _warnings(result, style: Style) -> List[str]:
    return [style(f"warning: {w}", "warn") for w in result.warnings]


def render_table(result, style: Optional[Style] = None) -> str:
    style = style or Style(False)
    cols = columns(result)
    cells = [[c.text(s) for c in cols] for s in result.solutions]
    widths = [max([len(c.header)] + [len(row[i]) for row in cells]) for i, c in enumerate(cols)]
    err_i = next(i for i, c in enumerate(cols) if c.key == "error_pct")
    out = [style(line, "head") if i == 0 else line for i, line in enumerate(title_lines(result))]
    out.append("")
    out.append("  ".join(c.header.ljust(w) for c, w in zip(cols, widths)).rstrip())
    tol = result.options.r_tol
    for sol, row in zip(result.solutions, cells):
        parts = []
        for i, (text, w) in enumerate(zip(row, widths)):
            padded = text.ljust(w)
            if i == err_i:
                padded = style(padded, classify(sol.error, tol))
            elif i == 0 and sol.rank == 1:
                padded = style(padded, "bold")  # highlight the best match
            parts.append(padded)
        out.append("  ".join(parts).rstrip())
    warnings = _warnings(result, style)
    if warnings:
        out.append("")
        out += warnings
    return "\n".join(out)


def render_raw(result) -> str:
    """One solution per line: component values, achieved value, error (%)."""
    lines = []
    for s in result.solutions:
        nums = [c.value for c in s.components] + [s.achieved, s.error * 100]
        lines.append(" ".join(f"{n:.6g}" for n in nums))
    return "\n".join(lines)


def _as_records(result) -> List[dict]:
    cols = columns(result)
    records = []
    for s in result.solutions:
        rec = {c.key: clean(c.raw(s)) for c in cols}
        rec[f"{result.metric}_min"] = clean(s.spec_min)
        rec[f"{result.metric}_max"] = clean(s.spec_max)
        rec["worst_case_error_pct"] = clean(s.worst_case_error * 100)
        records.append(rec)
    return records


def render_csv(result) -> str:
    records = _as_records(result)
    buf = io.StringIO()
    if records:
        writer = csv.DictWriter(buf, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    return buf.getvalue().rstrip("\n")


def render_json(result) -> str:
    opts = result.options
    doc = {
        "calculator": result.kind,
        "description": title_lines(result),
        "formula": result.formula,
        "inputs": result.inputs,
        "target": {"metric": result.metric, "unit": result.unit, "value": result.target},
        "ideal": result.ideal,
        "options": {
            "series": opts.r_series,
            "tolerance_pct": opts.r_tol,
            "cap_series": opts.c_series if result.kind == "rc" else None,
            "cap_tolerance_pct": opts.c_tol if result.kind == "rc" else None,
            "rank": opts.rank,
            "impedance_ohm": opts.impedance,
            "prefer_low_values": opts.prefer_low_values,
        },
        "solutions": [
            {
                "rank": s.rank,
                "components": [
                    {"name": c.name, "value": c.value, "unit": c.unit,
                     "display": format_eng(c.value, c.unit), "tolerance_pct": c.tolerance}
                    for c in s.components
                ],
                "achieved": s.achieved,
                "error_pct": s.error * 100,
                "range": [s.spec_min, s.spec_max],
                "tolerance_worst_case_pct": s.tol_wc * 100,
                "tolerance_rss_pct": s.tol_rss * 100,
                "worst_case_error_pct": s.worst_case_error * 100,
                "sensitivities": s.sensitivities,
                "metrics": s.metrics,
            }
            for s in result.solutions
        ],
        "warnings": result.warnings,
    }
    return json.dumps(_clean_tree(doc), indent=2, ensure_ascii=False)


def _clean_tree(obj):
    if isinstance(obj, dict):
        return {k: _clean_tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_tree(v) for v in obj]
    return clean(obj)


def render_markdown(result) -> str:
    cols = columns(result)
    out = [f"**{line}**  " for line in title_lines(result)]
    out.append("")
    out.append("| " + " | ".join(c.header for c in cols) + " |")
    out.append("|" + "|".join("---:" if c.numeric else "---" for c in cols) + "|")
    for s in result.solutions:
        out.append("| " + " | ".join(c.text(s) for c in cols) + " |")
    if result.warnings:
        out.append("")
        out += [f"> ⚠ {w}" for w in result.warnings]
    return "\n".join(out)


_LATEX_SUBS = [
    ("\\", r"\textbackslash{}"), ("%", r"\%"), ("_", r"\_"), ("&", r"\&"), ("#", r"\#"),
    ("±", r"$\pm$"), ("Ω", r"$\Omega$"), ("µ", r"$\mu$"), ("τ", r"$\tau$"),
    ("ω", r"$\omega$"), ("π", r"$\pi$"), ("·", r"$\cdot$"),
]


def latex_escape(text: str) -> str:
    for old, new in _LATEX_SUBS:
        text = text.replace(old, new)
    return text


def render_latex(result) -> str:
    cols = columns(result)
    lines = title_lines(result)
    out = [
        "% Generated by CalEl",
        "\\begin{table}[h]",
        "  \\centering",
        f"  \\caption{{{latex_escape(lines[0])}. {latex_escape(lines[1])}}}",
        "  \\begin{tabular}{" + "r" * len(cols) + "}",
        "    \\hline",
        "    " + " & ".join(latex_escape(c.header) for c in cols) + " \\\\",
        "    \\hline",
    ]
    for s in result.solutions:
        out.append("    " + " & ".join(latex_escape(c.text(s)) for c in cols) + " \\\\")
    out += ["    \\hline", "  \\end{tabular}", "\\end{table}"]
    return "\n".join(out)


def render_report(result, style: Optional[Style] = None) -> str:
    """A detailed, step-by-step report that shows the working."""
    from calel.core import e_series
    from calel.core.matcher import RANK_HELP

    style = style or Style(False)
    opts = result.options
    heading = f"CalEl report — {_KIND_NAMES[result.kind]}"
    out = [style(heading, "head"), "=" * len(heading)]
    for line in title_lines(result):
        out.append(line)
    out.append("")
    out.append(f"Formula:    {result.formula}")
    if result.kind == "rc" and result.metric != "tau":
        out.append(f"            τ = {format_eng(result.inputs['tau'], 's', 5)} (required R·C)")
    for name, value in result.ideal.items():
        shown = format_eng(value, "s", 5) if name == "R·C" else f"{value:.6g}"
        out.append(f"Ideal:      {name} = {shown}")
    out.append(f"Ranking:    {opts.rank} — {RANK_HELP[opts.rank]}")
    out.append("Tolerance:  worst case = extreme of all tolerance corners;")
    out.append("            RSS = √Σ(S_i·tol_i)², S_i = ∂ln(f)/∂ln(x_i)")
    unit = result.unit
    sign = -1 if result.kind == "opamp_inv" else 1
    tol = opts.r_tol
    for s in result.solutions:
        out.append("")
        comps = "   ".join(
            f"{c.name} = {format_eng(c.value, c.unit)} "
            f"({e_series.coarsest_series(c.value) or '?'}, ±{c.tolerance:g}%)"
            for c in s.components
        )
        out.append(style(f"#{s.rank}  {comps}", "bold"))
        err = style(format_pct(s.error), classify(s.error, tol))
        out.append(f"    {result.metric:<10} = {format_metric(sign * s.achieved, unit)}  (error {err})")
        lo, hi = sorted((sign * s.spec_min, sign * s.spec_max))
        out.append(
            f"    {'range':<10} = {format_metric(lo, unit)} … {format_metric(hi, unit)}"
            f"  (worst case ±{format_pct(s.tol_wc, False)}, RSS ±{format_pct(s.tol_rss, False)})"
        )
        out.append(f"    {'vs target':<10} = worst-case deviation {format_pct(s.worst_case_error, False)}")
        sens = ", ".join(f"S({n}) = {v:+.3f}" for n, v in s.sensitivities.items())
        out.append(f"    {'sensitivity':<10} {sens}")
        extras = []
        for key, value in s.metrics.items():
            if key == "gain_db":
                extras.append(f"gain = {value:.2f} dB")
            elif key == "I_bias":
                extras.append(f"I = {format_eng(value, 'A')}")
            elif key == "tau":
                extras.append(f"τ = {format_eng(value, 's', 4)}")
            elif key == "f_c":
                extras.append(f"f_c = {format_eng(value, 'Hz', 4)}")
            else:
                extras.append(f"{key} = {format_eng(value, 'Ω')}")
        if extras:
            out.append(f"    {'also':<10} {', '.join(extras)}")
    warnings = _warnings(result, style)
    if warnings:
        out.append("")
        out += warnings
    return "\n".join(out)
