"""Command-line interface for CalEl."""

import argparse
import sys
from typing import List, Optional

from calel import __version__
from calel.core import calculator, e_series
from calel.core.matcher import RANK_CRITERIA, RANK_HELP
from calel.utils import config as config_mod
from calel.utils import formatting
from calel.utils.formatting import Style, parse_eng

DESCRIPTION = """\
CalEl finds the closest standard (E-series) component values for resistor
dividers, op-amp gain networks and RC time constants, ranks several
solutions and shows the tolerance stack-up of each."""


def _series_table() -> str:
    lines = ["  Series  Count  Tolerance  Use case"]
    for name in e_series.SERIES_ORDER:
        lines.append(
            f"  {name:<6}  {len(e_series.SERIES[name]):>5}  "
            f"{'±' + format(e_series.NOMINAL_TOLERANCE[name], 'g') + '%':>9}  "
            f"{e_series.USE_CASE[name]}"
        )
    return "\n".join(lines)


EPILOG = f"""\
E-series standards (IEC 60063)
  Each series spaces N values per decade geometrically so that neighbouring
  values overlap at the series tolerance, e.g. E12: 1.0 1.2 1.5 1.8 2.2 2.7
  3.3 3.9 4.7 5.6 6.8 8.2 (×10^n).  Finer series = closer matches, pricier parts.
{_series_table()}

Numbers accept SI prefixes and units: 4.7k, 4k7, 100n, 10u, 1.8V, 1meg, 1e-6
('m' = milli, 'M' = mega).  Negative values with prefixes need '=':
--opamp_inv_vv=-2k.

Examples
  calel --targ_v 1.8 --rail_v 5                   5 V -> 1.8 V divider (E24)
  calel --targ_v 1.8 --rail_v 5 --series E96 --tolerance 1 --solutions 3
  calel --opamp_non_inv_vv 100 --series E96       non-inverting, G = 100 V/V
  calel --opamp_inv_dB 60                         inverting, |G| = 60 dB
  calel --targ_corner_hz 1k --series E12          RC corner at 1 kHz
  calel --targ_rise_1090 10u                      10-90 % rise time of 10 µs
  calel --targ_corner_hz 10k --prefer_low_values  smallest capacitor
  calel --targ_v 3.3 --rail_v 12 -f report        show the full working
  calel --opamp_non_inv_vv 11 -f csv -o gain.csv  export for a spreadsheet
  calel --list_series E24                         print the E24 values
  calel --gui                                     launch the graphical interface

Example output (calel --targ_v 1.8 --rail_v 5 --solutions 3)
  Target: 1.8V from 5V rail
  Series: E24 (±5% tolerance)

  Rank  R_high  R_low   V_out   Error   Tol(WC)  Tol(RSS)
  1.    11kΩ    6.2kΩ   1.802V  +0.13%  ±6.49%   ±4.52%
  2.    3.9kΩ   2.2kΩ   1.803V  +0.18%  ±6.48%   ±4.52%
  3.    9.1kΩ   5.1kΩ   1.796V  -0.24%  ±6.50%   ±4.53%

Tolerance stack-up
  Tol(WC)  worst case: every component simultaneously at its tolerance limit.
  Tol(RSS) root-sum-square: statistical estimate for independent errors.

Config file: {config_mod.config_path()}  (override with CALEL_CONFIG)
"""


def _number(text: str) -> float:
    try:
        return parse_eng(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _series(text: str) -> str:
    try:
        return e_series.normalize_series(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def build_parser(cfg: Optional[config_mod.Config] = None) -> argparse.ArgumentParser:
    cfg = cfg or config_mod.Config()
    p = argparse.ArgumentParser(
        prog="calel",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"calel {__version__}")

    tgt = p.add_argument_group("targets (choose one)")
    mx = tgt.add_mutually_exclusive_group()
    mx.add_argument("--targ_v", type=_number, metavar="V",
                    help="resistor divider output voltage (needs --rail_v)")
    mx.add_argument("--opamp_non_inv_vv", type=_number, metavar="G",
                    help="non-inverting gain in V/V: G = 1 + Rf/Rg")
    mx.add_argument("--opamp_non_inv_dB", type=_number, metavar="dB",
                    help="non-inverting gain in dB")
    mx.add_argument("--opamp_inv_vv", type=_number, metavar="G",
                    help="inverting gain in V/V (sign ignored): G = -Rf/Rin")
    mx.add_argument("--opamp_inv_dB", type=_number, metavar="dB",
                    help="inverting gain magnitude in dB")
    mx.add_argument("--targ_corner_hz", type=_number, metavar="Hz",
                    help="RC corner frequency: f_c = 1/(2πRC)")
    mx.add_argument("--targ_corner_rad", type=_number, metavar="rad/s",
                    help="RC corner angular frequency: ω_c = 1/(RC)")
    mx.add_argument("--targ_tau", "--targ_rc", dest="targ_tau", type=_number, metavar="s",
                    help="RC time constant / impedance product τ = RC in seconds")
    mx.add_argument("--targ_rise_1090", type=_number, metavar="s",
                    help="10%%-90%% rise time: t_r = ln(9)·RC ≈ 2.2·RC")
    mx.add_argument("--targ_rise_2080", type=_number, metavar="s",
                    help="20%%-80%% rise time: t_r = ln(4)·RC ≈ 1.4·RC")
    tgt.add_argument("--rail_v", type=_number, metavar="V",
                     help="supply/rail voltage for --targ_v")

    srch = p.add_argument_group("component selection")
    srch.add_argument("--series", type=_series, default=cfg.series,
                      help=f"E-series for resistors (and capacitors unless --cap_series) "
                           f"[{', '.join(e_series.SERIES_ORDER)}; default %(default)s]")
    srch.add_argument("--tolerance", type=_number, default=cfg.tolerance, metavar="PCT",
                      help="resistor tolerance in %% (default: the series' nominal tolerance)")
    srch.add_argument("--cap_series", type=_series, default=cfg.cap_series,
                      help="E-series for capacitors (default: --series)")
    srch.add_argument("--cap_tolerance", type=_number, default=cfg.cap_tolerance, metavar="PCT",
                      help="capacitor tolerance in %% (default: the cap series' nominal)")
    srch.add_argument("--solutions", "-n", type=int, default=cfg.solutions, metavar="N",
                      help="number of solutions to list (default %(default)s)")
    srch.add_argument("--rank", choices=RANK_CRITERIA, default=cfg.rank,
                      help="ranking: " + "; ".join(f"{k} = {v}" for k, v in RANK_HELP.items())
                           + " (default %(default)s)")
    srch.add_argument("--impedance", type=_number, default=cfg.impedance, metavar="OHMS",
                      help="preferred network resistance: R_high+R_low, Rf+Rg, or R for RC "
                           "(default %(default)gΩ)")
    srch.add_argument("--prefer_low_values", action="store_true", default=cfg.prefer_low_values,
                      help="prefer the smallest components: lowest resistances for dividers "
                           "and op-amps, smallest capacitor for RC")
    srch.add_argument("--r_min", type=_number, default=cfg.r_min, metavar="OHMS",
                      help="smallest resistor to consider (default %(default)gΩ)")
    srch.add_argument("--r_max", type=_number, default=cfg.r_max, metavar="OHMS",
                      help="largest resistor to consider (default %(default)gΩ)")
    srch.add_argument("--c_min", type=_number, default=cfg.c_min, metavar="F",
                      help="smallest capacitor to consider (default %(default)gF)")
    srch.add_argument("--c_max", type=_number, default=cfg.c_max, metavar="F",
                      help="largest capacitor to consider (default %(default)gF)")

    out = p.add_argument_group("output")
    out.add_argument("--format", "-f", choices=formatting.FORMATS, default=cfg.format,
                     help="output format (default %(default)s)")
    out.add_argument("--output", "-o", metavar="FILE",
                     help="write the result to FILE instead of stdout")
    out.add_argument("--color", choices=("auto", "always", "never"), default=cfg.color,
                     help="colour terminal output (default %(default)s; honours NO_COLOR)")

    misc = p.add_argument_group("other")
    misc.add_argument("--list_series", nargs="?", const="all", metavar="SERIES",
                      help="list the E-series, or every value of one series, and exit")
    misc.add_argument("--gui", action="store_true", help="launch the graphical interface")
    return p


def _options(args) -> calculator.Options:
    return calculator.Options(
        series=args.series,
        tolerance=args.tolerance,
        solutions=args.solutions,
        rank=args.rank,
        impedance=args.impedance,
        prefer_low_values=args.prefer_low_values,
        r_min=args.r_min,
        r_max=args.r_max,
        cap_series=args.cap_series,
        cap_tolerance=args.cap_tolerance,
        c_min=args.c_min,
        c_max=args.c_max,
    )


def run(args) -> calculator.Result:
    """Dispatch parsed arguments to the matching calculator."""
    opts = _options(args)
    if args.targ_v is not None:
        if args.rail_v is None:
            raise calculator.CalculationError(
                "--targ_v needs a rail voltage", "add --rail_v, e.g. --rail_v 5"
            )
        return calculator.divider(args.targ_v, args.rail_v, opts)
    if args.opamp_non_inv_vv is not None:
        return calculator.opamp(args.opamp_non_inv_vv, False, False, opts)
    if args.opamp_non_inv_dB is not None:
        return calculator.opamp(args.opamp_non_inv_dB, False, True, opts)
    if args.opamp_inv_vv is not None:
        return calculator.opamp(args.opamp_inv_vv, True, False, opts)
    if args.opamp_inv_dB is not None:
        return calculator.opamp(args.opamp_inv_dB, True, True, opts)
    rc_targets = {
        "targ_corner_hz": "corner_hz",
        "targ_corner_rad": "corner_rad",
        "targ_tau": "tau",
        "targ_rise_1090": "rise_1090",
        "targ_rise_2080": "rise_2080",
    }
    for attr, kind in rc_targets.items():
        value = getattr(args, attr)
        if value is not None:
            return calculator.rc(value, kind, opts)
    raise calculator.CalculationError(
        "no target given", "try --targ_v/--rail_v, --opamp_non_inv_vv or --targ_corner_hz"
    )


def list_series(which: str) -> str:
    if which == "all":
        return "E-series standards (IEC 60063)\n" + _series_table()
    name = e_series.normalize_series(which)
    values = " ".join(f"{v:.2f}".rstrip("0").rstrip(".") if name in ("E6", "E12", "E24")
                      else f"{v:.2f}" for v in e_series.decade_values(name))
    return (f"{name}: {len(e_series.SERIES[name])} values per decade, "
            f"nominal ±{e_series.NOMINAL_TOLERANCE[name]:g}% (multiply by 10^n)\n{values}")


def main(argv: Optional[List[str]] = None) -> int:
    cfg = config_mod.load()
    parser = build_parser(cfg)
    args = parser.parse_args(argv)
    err_style = Style(formatting.color_supported(sys.stderr, args.color))

    def fail(message: str, hint: str = "") -> int:
        print(err_style(f"error: {message}", "error"), file=sys.stderr)
        if hint:
            print(err_style(f"hint: {hint}", "warn"), file=sys.stderr)
        return 2

    if args.gui:
        from calel.gui.app import main as gui_main

        return gui_main()
    if args.list_series:
        try:
            print(list_series(args.list_series))
        except ValueError as exc:
            return fail(str(exc))
        return 0
    if all(getattr(args, a) is None for a in (
        "targ_v", "opamp_non_inv_vv", "opamp_non_inv_dB", "opamp_inv_vv", "opamp_inv_dB",
        "targ_corner_hz", "targ_corner_rad", "targ_tau", "targ_rise_1090", "targ_rise_2080",
    )):
        parser.print_usage(sys.stderr)
        return fail("no target given", "run 'calel --help' for targets and examples")

    try:
        result = run(args)
    except calculator.CalculationError as exc:
        return fail(str(exc), exc.hint)
    except ValueError as exc:
        return fail(str(exc))

    if args.output:
        text = formatting.render(result, args.format)
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            return fail(f"cannot write {args.output}: {exc.strerror}")
        print(f"wrote {args.format} output to {args.output}", file=sys.stderr)
        for w in result.warnings:
            print(err_style(f"warning: {w}", "warn"), file=sys.stderr)
        return 0
    style = Style(formatting.color_supported(sys.stdout, args.color))
    print(formatting.render(result, args.format, style))
    return 0


if __name__ == "__main__":
    sys.exit(main())
