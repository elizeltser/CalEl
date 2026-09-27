"""Calculation engines: resistor divider, op-amp gain networks and RC time constants.

Every engine follows the same recipe:

1. Convert the user's target into an ideal component ratio (dividers,
   op-amp gain) or product (RC).
2. Ask :mod:`calel.core.matcher` for standard-value pairs near that ideal.
3. Evaluate each pair: achieved value, error, and tolerance stack-up
   (worst-case corners and RSS).
4. Rank the pairs and return the best ``options.solutions`` of them.
"""

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from calel.core import e_series, matcher

LN9 = math.log(9)  # 10%-90% rise time = ln(9)·RC ≈ 2.197·RC
LN4 = math.log(4)  # 20%-80% rise time = ln(4)·RC ≈ 1.386·RC

OHM = "Ω"
FARAD = "F"


class CalculationError(ValueError):
    """Invalid input or no achievable solution.

    ``hint`` holds a suggested corrective action for the user.
    """

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


@dataclass
class Options:
    """Search settings shared by all calculators."""

    series: str = "E24"
    tolerance: Optional[float] = None  # resistor tolerance in %, None = series nominal
    solutions: int = 5
    rank: str = "error"
    impedance: float = 10e3  # preferred network resistance (see each engine)
    prefer_low_values: bool = False
    r_min: float = 10.0
    r_max: float = 1e6
    cap_series: Optional[str] = None  # None = same as ``series``
    cap_tolerance: Optional[float] = None  # None = cap series nominal
    c_min: float = 10e-12
    c_max: float = 100e-6

    @property
    def r_series(self) -> str:
        return e_series.normalize_series(self.series)

    @property
    def r_tol(self) -> float:
        if self.tolerance is not None:
            return float(self.tolerance)
        return e_series.nominal_tolerance(self.r_series)

    @property
    def c_series(self) -> str:
        return e_series.normalize_series(self.cap_series or self.series)

    @property
    def c_tol(self) -> float:
        if self.cap_tolerance is not None:
            return float(self.cap_tolerance)
        return e_series.nominal_tolerance(self.c_series)

    def validate(self) -> None:
        e_series.normalize_series(self.series)
        if self.cap_series:
            e_series.normalize_series(self.cap_series)
        if self.solutions < 1:
            raise CalculationError("number of solutions must be at least 1")
        for name in ("tolerance", "cap_tolerance"):
            tol = getattr(self, name)
            if tol is not None and not 0 <= tol < 100:
                raise CalculationError(
                    f"{name.replace('_', ' ')} must be between 0 and 100 %",
                    "typical values are 0.1, 0.5, 1, 5, 10 or 20",
                )
        for name in ("impedance", "r_min", "r_max", "c_min", "c_max"):
            if getattr(self, name) <= 0:
                raise CalculationError(f"{name} must be positive")
        if self.rank not in matcher.RANK_CRITERIA:
            raise CalculationError(
                f"unknown ranking '{self.rank}'",
                f"choose one of: {', '.join(matcher.RANK_CRITERIA)}",
            )


@dataclass
class Component:
    name: str
    value: float
    unit: str
    tolerance: float  # percent


@dataclass
class Solution:
    components: List[Component]
    achieved: float  # primary metric, same units as Result.target
    error: float  # relative: achieved / target - 1
    spec_min: float  # primary metric at the worst tolerance corners
    spec_max: float
    tol_wc: float  # worst-case relative deviation from nominal (fraction)
    tol_rss: float  # root-sum-square relative deviation (fraction)
    worst_case_error: float  # worst-case relative deviation from *target*
    sensitivities: Dict[str, float]  # d(ln metric) / d(ln component)
    preference: int  # lower = more common values
    metrics: Dict[str, float] = field(default_factory=dict)
    rank: int = 0

    def value(self, name: str) -> float:
        for c in self.components:
            if c.name == name:
                return c.value
        raise KeyError(name)


@dataclass
class Result:
    kind: str  # "divider" | "opamp_non_inv" | "opamp_inv" | "rc"
    metric: str  # name of the primary metric, e.g. "V_out"
    unit: str  # unit of the primary metric
    target: float
    formula: str
    inputs: Dict[str, Any]
    options: Options
    solutions: List[Solution]
    ideal: Dict[str, float] = field(default_factory=dict)  # ideal ratio/product
    warnings: List[str] = field(default_factory=list)

    @property
    def best(self) -> Solution:
        return self.solutions[0]


# --------------------------------------------------------------------------
# Tolerance analysis
# --------------------------------------------------------------------------


def tolerance_analysis(
    func: Callable[..., float],
    values: Sequence[float],
    tolerances: Sequence[float],
    names: Sequence[str],
) -> dict:
    """Worst-case and RSS tolerance stack-up of ``func(*values)``.

    Worst case evaluates every tolerance corner (all 2**n sign combinations),
    which is exact for the monotonic networks CalEl handles.  RSS combines
    the relative sensitivities ``S_i = d ln f / d ln x_i`` as
    ``sqrt(sum((S_i * tol_i) ** 2))``, the usual statistical estimate for
    independent, centred component errors.
    """
    nominal = func(*values)
    corners = []
    for signs in itertools.product((-1, 1), repeat=len(values)):
        varied = [v * (1 + s * t / 100) for v, s, t in zip(values, signs, tolerances)]
        corners.append(func(*varied))
    wc = max(abs(c / nominal - 1) for c in corners)

    h = 1e-6
    sens = {}
    for i, name in enumerate(names):
        up = list(values)
        dn = list(values)
        up[i] *= 1 + h
        dn[i] *= 1 - h
        sens[name] = (func(*up) - func(*dn)) / (2 * h * nominal)
    rss = math.sqrt(
        sum((sens[n] * t / 100) ** 2 for n, t in zip(names, tolerances))
    )
    return {
        "nominal": nominal,
        "min": min(corners + [nominal]),
        "max": max(corners + [nominal]),
        "corners": corners,
        "wc": wc,
        "rss": rss,
        "sensitivities": sens,
    }


# --------------------------------------------------------------------------
# Generic pair search
# --------------------------------------------------------------------------


def _evaluate(
    pair,
    names: Sequence[str],
    units: Sequence[str],
    tolerances: Sequence[float],
    func: Callable[[float, float], float],
    target: float,
    extra_metrics: Optional[Callable[[float, float], Dict[str, float]]] = None,
) -> Solution:
    stack = tolerance_analysis(func, pair, tolerances, names)
    achieved = stack["nominal"]
    return Solution(
        components=[
            Component(n, v, u, t) for n, v, u, t in zip(names, pair, units, tolerances)
        ],
        achieved=achieved,
        error=achieved / target - 1,
        spec_min=stack["min"],
        spec_max=stack["max"],
        tol_wc=stack["wc"],
        tol_rss=stack["rss"],
        worst_case_error=max(abs(c / target - 1) for c in stack["corners"]),
        sensitivities=stack["sensitivities"],
        preference=sum(e_series.preference_score(v) for v in pair),
        metrics=extra_metrics(*pair) if extra_metrics else {},
    )


def _finish(result: Result, candidates: List[Solution]) -> Result:
    opts = result.options
    if not candidates:
        raise CalculationError(
            "no standard-value combination reaches the target within the allowed "
            "component range",
            "widen the resistor/capacitor range or relax the target",
        )
    ranked = matcher.rank_solutions(candidates, opts.rank, opts.r_tol)
    result.solutions = ranked[: opts.solutions]
    for i, sol in enumerate(result.solutions, 1):
        sol.rank = i

    best_err = min(abs(s.error) for s in candidates) * 100
    if best_err > opts.r_tol:
        finer = _finer_series(opts.r_series)
        hint = f"; try --series {finer}" if finer else ""
        result.warnings.append(
            f"best nominal error ({best_err:.2f}%) exceeds the component "
            f"tolerance (±{opts.r_tol:g}%){hint}"
        )
    nominal = e_series.nominal_tolerance(opts.r_series)
    if opts.r_tol > nominal:
        result.warnings.append(
            f"{opts.r_series} values are normally sold as ±{nominal:g}% parts; "
            f"±{opts.r_tol:g}% parts in this series may be hard to source"
        )
    return result


def _finer_series(series: str) -> str:
    order = e_series.SERIES_ORDER
    i = order.index(series)
    return order[i + 1] if i + 1 < len(order) else ""


def _values(series: str, lo: float, hi: float, what: str) -> List[float]:
    values = e_series.values_in_range(series, lo, hi)
    if not values:
        raise CalculationError(
            f"no {series} {what} values between {lo:g} and {hi:g}",
            "widen the component range",
        )
    return values


def _resistor_values(opts: Options) -> List[float]:
    return _values(opts.r_series, opts.r_min, opts.r_max, "resistor")


def _check_reachable(ideal: float, lo: float, hi: float, what: str) -> None:
    """Refuse targets that no pair inside the component range can approach."""
    if not lo * (1 - 1e-9) <= ideal <= hi * (1 + 1e-9):
        raise CalculationError(
            f"required {what} of {ideal:.4g} is outside what the component range allows "
            f"({lo:.4g} … {hi:.4g})",
            "widen the resistor/capacitor range (--r_min/--r_max/--c_min/--c_max or Settings)",
        )


def _network_score(opts: Options):
    """Choose between decade-shifted variants of a resistor pair."""
    if opts.prefer_low_values:
        return lambda p: p[0] + p[1]
    return lambda p: abs(math.log10((p[0] + p[1]) / opts.impedance))


# --------------------------------------------------------------------------
# Resistor divider
# --------------------------------------------------------------------------


def divider(target_v: float, rail_v: float, options: Optional[Options] = None) -> Result:
    """Find R_high (rail side) and R_low (ground side) for ``target_v``.

    ``V_out = V_rail · R_low / (R_high + R_low)``.  ``options.impedance``
    is the preferred total resistance R_high + R_low.
    """
    opts = options or Options()
    opts.validate()
    if rail_v == 0:
        raise CalculationError("rail voltage must be non-zero")
    k = target_v / rail_v
    if not 0 < k < 1:
        raise CalculationError(
            f"target {target_v:g} V is not reachable from a {rail_v:g} V rail",
            "a divider output must lie strictly between 0 V and the rail "
            "(same sign as the rail)",
        )
    ratio = (1 - k) / k  # R_high / R_low
    values = _resistor_values(opts)
    _check_reachable(ratio, values[0] / values[-1], values[-1] / values[0], "R_high/R_low")
    pairs = matcher.dedupe(
        matcher.ratio_candidates(values, values, ratio),
        matcher.ratio_key,
        _network_score(opts),
    )

    def vout(rh, rl):
        return rail_v * rl / (rh + rl)

    def extras(rh, rl):
        return {
            "R_total": rh + rl,
            "I_bias": rail_v / (rh + rl),
            "R_thevenin": rh * rl / (rh + rl),
        }

    result = Result(
        kind="divider",
        metric="V_out",
        unit="V",
        target=target_v,
        formula="V_out = V_rail · R_low / (R_high + R_low)",
        inputs={"target_v": target_v, "rail_v": rail_v},
        options=opts,
        solutions=[],
        ideal={"R_high/R_low": ratio},
    )
    tol = opts.r_tol
    cands = [
        _evaluate(
            p, ("R_high", "R_low"), (OHM, OHM), (tol, tol), vout, target_v, extras
        )
        for p in pairs
    ]
    return _finish(result, cands)


# --------------------------------------------------------------------------
# Op-amp feedback networks
# --------------------------------------------------------------------------


def db_to_vv(db: float) -> float:
    return 10 ** (db / 20)


def vv_to_db(vv: float) -> float:
    return 20 * math.log10(abs(vv))


def opamp(
    gain: float,
    inverting: bool = False,
    db: bool = False,
    options: Optional[Options] = None,
) -> Result:
    """Find R_feedback and R_ground/R_input for a target closed-loop gain.

    Non-inverting: ``G = 1 + R_f / R_g``.  Inverting: ``G = -R_f / R_in``.
    ``gain`` is in V/V, or dB when ``db`` is true; for the inverting
    topology the sign is ignored (the magnitude is matched).
    ``options.impedance`` is the preferred R_f + R_g.
    """
    opts = options or Options()
    opts.validate()
    mag = db_to_vv(gain) if db else abs(gain)
    if inverting:
        if mag <= 0:
            raise CalculationError("gain magnitude must be positive")
        ratio = mag
        names = ("R_feedback", "R_input")
        kind = "opamp_inv"
        formula = "G = -R_feedback / R_input"

        def func(rf, rg):
            return rf / rg

    else:
        if not db and gain < 0:
            raise CalculationError(
                "a non-inverting amplifier cannot have negative gain",
                "use --opamp_inv_vv for an inverting stage",
            )
        if mag <= 1 + 1e-12:
            raise CalculationError(
                "non-inverting gain must be greater than 1 V/V (0 dB)",
                "for unity gain use a voltage follower (no resistors needed)",
            )
        ratio = mag - 1
        names = ("R_feedback", "R_ground")
        kind = "opamp_non_inv"
        formula = "G = 1 + R_feedback / R_ground"

        def func(rf, rg):
            return 1 + rf / rg

    values = _resistor_values(opts)
    _check_reachable(ratio, values[0] / values[-1], values[-1] / values[0], f"{names[0]}/{names[1]}")
    pairs = matcher.dedupe(
        matcher.ratio_candidates(values, values, ratio),
        matcher.ratio_key,
        _network_score(opts),
    )

    def extras(rf, rg):
        g = func(rf, rg)
        return {"gain_db": vv_to_db(g), "R_total": rf + rg}

    result = Result(
        kind=kind,
        metric="Gain",
        unit="V/V",
        target=mag,
        formula=formula,
        inputs={"gain": gain, "db": float(db)},
        options=opts,
        solutions=[],
        ideal={f"{names[0]}/{names[1]}": ratio},
    )
    tol = opts.r_tol
    cands = [
        _evaluate(p, names, (OHM, OHM), (tol, tol), func, mag, extras) for p in pairs
    ]
    result = _finish(result, cands)
    r_in = result.best.components[1].value
    if inverting and r_in < 1e3:
        result.warnings.append(
            f"input impedance of the best solution is only {r_in:g} Ω (= R_input); "
            "raise the impedance setting if the source cannot drive it"
        )
    if mag > 1000:
        result.warnings.append(
            f"gain of {mag:g} V/V in one stage needs a GBW above "
            f"{mag:g} × signal bandwidth; consider splitting into two stages"
        )
    return result


# --------------------------------------------------------------------------
# RC time constant / corner frequency
# --------------------------------------------------------------------------

#: target kind -> (metric name, unit, tau -> metric, metric -> tau, description)
RC_TARGETS = {
    "corner_hz": (
        "f_c", "Hz",
        lambda tau: 1 / (2 * math.pi * tau),
        lambda f: 1 / (2 * math.pi * f),
        "f_c = 1 / (2π·R·C)",
    ),
    "corner_rad": (
        "ω_c", "rad/s",
        lambda tau: 1 / tau,
        lambda w: 1 / w,
        "ω_c = 1 / (R·C)",
    ),
    "tau": (
        "tau", "s",
        lambda tau: tau,
        lambda tau: tau,
        "τ = R·C",
    ),
    "rise_1090": (
        "t_r(10-90%)", "s",
        lambda tau: LN9 * tau,
        lambda t: t / LN9,
        "t_r(10-90%) = ln(9)·R·C ≈ 2.197·R·C",
    ),
    "rise_2080": (
        "t_r(20-80%)", "s",
        lambda tau: LN4 * tau,
        lambda t: t / LN4,
        "t_r(20-80%) = ln(4)·R·C ≈ 1.386·R·C",
    ),
}


def rc(target: float, kind: str = "corner_hz", options: Optional[Options] = None) -> Result:
    """Find R and C for an RC time constant expressed as ``kind``.

    ``kind`` is one of :data:`RC_TARGETS`.  ``options.impedance`` is the
    preferred resistance; with ``prefer_low_values`` the smallest capacitor
    that still fits the resistor range is chosen instead.
    """
    opts = options or Options()
    opts.validate()
    if kind not in RC_TARGETS:
        raise CalculationError(
            f"unknown RC target '{kind}'", f"choose one of: {', '.join(RC_TARGETS)}"
        )
    if target <= 0:
        raise CalculationError("RC target must be positive")
    metric, unit, from_tau, to_tau, formula = RC_TARGETS[kind]
    tau = to_tau(target)

    r_values = _resistor_values(opts)
    c_values = _values(opts.c_series, opts.c_min, opts.c_max, "capacitor")
    _check_reachable(tau, r_values[0] * c_values[0], r_values[-1] * c_values[-1], "R·C (s)")
    if opts.prefer_low_values:
        score = lambda p: p[1]  # noqa: E731 - smallest capacitor
    else:
        score = lambda p: abs(math.log10(p[0] / opts.impedance))  # noqa: E731
    pairs = matcher.dedupe(
        matcher.product_candidates(r_values, c_values, tau),
        matcher.product_key,
        score,
    )

    def func(r, c):
        return from_tau(r * c)

    def extras(r, c):
        return {"tau": r * c, "f_c": 1 / (2 * math.pi * r * c)}

    result = Result(
        kind="rc",
        metric=metric,
        unit=unit,
        target=target,
        formula=formula,
        inputs={"target": target, "tau": tau, "kind": kind},
        options=opts,
        solutions=[],
        ideal={"R·C": tau},
    )
    tols = (opts.r_tol, opts.c_tol)
    cands = [
        _evaluate(p, ("R", "C"), (OHM, FARAD), tols, func, target, extras)
        for p in pairs
    ]
    return _finish(result, cands)
