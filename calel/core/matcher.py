"""Standard-value matching and solution ranking.

The search strategy is the same for every calculator: for each value ``b``
in one component's candidate list, compute the ideal partner ``a`` that
hits the target exactly, then take the standard values just below and just
above it.  That yields every pair worth considering in O(n log n).

Pairs that differ only by a decade shift (10k/5.6k vs 100k/56k) produce the
same ratio (or product) and are collapsed into one, keeping the variant
whose impedance level best fits the user's preference.
"""

import bisect
import math
from typing import Callable, Dict, Hashable, Iterable, List, Sequence, Tuple

RANK_CRITERIA = ("error", "worst_case", "preferred")

RANK_HELP = {
    "error": "closest nominal match first",
    "worst_case": "smallest worst-case deviation (nominal error + tolerance stack)",
    "preferred": "most common values (E6 > E12 > E24 ...) among in-tolerance matches",
}

Pair = Tuple[float, float]


def nearest(values: Sequence[float], x: float) -> List[float]:
    """The standard values immediately below and above ``x``.

    ``values`` must be sorted.  Returns one value when ``x`` lies outside the
    list or hits a value exactly, otherwise two.
    """
    if not values:
        return []
    i = bisect.bisect_left(values, x)
    if i < len(values) and math.isclose(values[i], x, rel_tol=1e-12):
        return [values[i]]
    out = []
    if i > 0:
        out.append(values[i - 1])
    if i < len(values):
        out.append(values[i])
    return out


def closest(values: Sequence[float], x: float) -> float:
    """The single standard value closest to ``x`` on a logarithmic scale."""
    options = nearest(values, x)
    if not options:
        raise ValueError("no values to choose from")
    return min(options, key=lambda v: abs(math.log(v / x)))


def ratio_candidates(
    a_values: Sequence[float], b_values: Sequence[float], ratio: float
) -> List[Pair]:
    """Pairs ``(a, b)`` with ``a / b`` close to ``ratio``."""
    pairs = []
    for b in b_values:
        for a in nearest(a_values, ratio * b):
            pairs.append((a, b))
    return pairs


def product_candidates(
    a_values: Sequence[float], b_values: Sequence[float], product: float
) -> List[Pair]:
    """Pairs ``(a, b)`` with ``a * b`` close to ``product``."""
    pairs = []
    for b in b_values:
        for a in nearest(a_values, product / b):
            pairs.append((a, b))
    return pairs


def ratio_key(pair: Pair) -> Hashable:
    return round(math.log10(pair[0] / pair[1]), 9)


def product_key(pair: Pair) -> Hashable:
    return round(math.log10(pair[0] * pair[1]), 9)


def dedupe(
    pairs: Iterable[Pair],
    key: Callable[[Pair], Hashable],
    score: Callable[[Pair], float],
) -> List[Pair]:
    """Keep one pair per ``key`` — the one with the lowest ``score``."""
    best: Dict[Hashable, Pair] = {}
    for pair in pairs:
        k = key(pair)
        if k not in best or score(pair) < score(best[k]):
            best[k] = pair
    return list(best.values())


def rank_solutions(solutions: list, criterion: str, tolerance_pct: float) -> list:
    """Sort solutions by ``criterion`` (see :data:`RANK_CRITERIA`).

    Solutions are duck-typed: they need ``error``, ``tol_wc``,
    ``worst_case_error`` and ``preference`` attributes.
    """
    if criterion not in RANK_CRITERIA:
        raise ValueError(
            f"unknown ranking '{criterion}' (choose from {', '.join(RANK_CRITERIA)})"
        )
    by_error = sorted(
        solutions, key=lambda s: (abs(s.error), s.tol_wc, s.preference)
    )
    if criterion == "error":
        return by_error
    if criterion == "worst_case":
        return sorted(
            solutions,
            key=lambda s: (s.worst_case_error, abs(s.error), s.preference),
        )
    # "preferred": common values first, but only among matches that are
    # already within the component tolerance; everything else follows.
    limit = tolerance_pct / 100
    good = [s for s in by_error if abs(s.error) <= limit]
    rest = [s for s in by_error if abs(s.error) > limit]
    good.sort(key=lambda s: (s.preference, abs(s.error)))
    return good + rest
