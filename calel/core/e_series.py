"""IEC 60063 E-series preferred number tables.

Mantissas are stored as integers in hundredths (``470`` == 4.70) so decade
scaling never accumulates floating point noise.  All tables are hardcoded;
no external data files are needed.
"""

import math
from typing import Dict, List, Tuple

_E6 = (100, 150, 220, 330, 470, 680)
_E12 = (100, 120, 150, 180, 220, 270, 330, 390, 470, 560, 680, 820)
_E24 = (
    100, 110, 120, 130, 150, 160, 180, 200, 220, 240, 270, 300,
    330, 360, 390, 430, 470, 510, 560, 620, 680, 750, 820, 910,
)
_E48 = (
    100, 105, 110, 115, 121, 127, 133, 140, 147, 154, 162, 169,
    178, 187, 196, 205, 215, 226, 237, 249, 261, 274, 287, 301,
    316, 332, 348, 365, 383, 402, 422, 442, 464, 487, 511, 536,
    562, 590, 619, 649, 681, 715, 750, 787, 825, 866, 909, 953,
)
_E96 = (
    100, 102, 105, 107, 110, 113, 115, 118, 121, 124, 127, 130,
    133, 137, 140, 143, 147, 150, 154, 158, 162, 165, 169, 174,
    178, 182, 187, 191, 196, 200, 205, 210, 215, 221, 226, 232,
    237, 243, 249, 255, 261, 267, 274, 280, 287, 294, 301, 309,
    316, 324, 332, 340, 348, 357, 365, 374, 383, 392, 402, 412,
    422, 432, 442, 453, 464, 475, 487, 499, 511, 523, 536, 549,
    562, 576, 590, 604, 619, 634, 649, 665, 681, 698, 715, 732,
    750, 768, 787, 806, 825, 845, 866, 887, 909, 931, 953, 976,
)
_E192 = (
    100, 101, 102, 104, 105, 106, 107, 109, 110, 111, 113, 114,
    115, 117, 118, 120, 121, 123, 124, 126, 127, 129, 130, 132,
    133, 135, 137, 138, 140, 142, 143, 145, 147, 149, 150, 152,
    154, 156, 158, 160, 162, 164, 165, 167, 169, 172, 174, 176,
    178, 180, 182, 184, 187, 189, 191, 193, 196, 198, 200, 203,
    205, 208, 210, 213, 215, 218, 221, 223, 226, 229, 232, 234,
    237, 240, 243, 246, 249, 252, 255, 258, 261, 264, 267, 271,
    274, 277, 280, 284, 287, 291, 294, 298, 301, 305, 309, 312,
    316, 320, 324, 328, 332, 336, 340, 344, 348, 352, 357, 361,
    365, 370, 374, 379, 383, 388, 392, 397, 402, 407, 412, 417,
    422, 427, 432, 437, 442, 448, 453, 459, 464, 470, 475, 481,
    487, 493, 499, 505, 511, 517, 523, 530, 536, 542, 549, 556,
    562, 569, 576, 583, 590, 597, 604, 612, 619, 626, 634, 642,
    649, 657, 665, 673, 681, 690, 698, 706, 715, 723, 732, 741,
    750, 759, 768, 777, 787, 796, 806, 816, 825, 835, 845, 856,
    866, 876, 887, 898, 909, 920, 931, 942, 953, 965, 976, 988,
)

#: Mantissa tables, keyed by series name.
SERIES: Dict[str, Tuple[int, ...]] = {
    "E6": _E6,
    "E12": _E12,
    "E24": _E24,
    "E48": _E48,
    "E96": _E96,
    "E192": _E192,
}

#: Nominal component tolerance (percent) each series is designed for.
NOMINAL_TOLERANCE: Dict[str, float] = {
    "E6": 20.0,
    "E12": 10.0,
    "E24": 5.0,
    "E48": 2.0,
    "E96": 1.0,
    "E192": 0.5,
}

#: Short description of where each series is typically used.
USE_CASE: Dict[str, str] = {
    "E6": "Rough filtering, non-critical bias",
    "E12": "General purpose, cost-sensitive",
    "E24": "Standard production, feedback networks",
    "E48": "Semi-precision networks",
    "E96": "Precision analog, low-tolerance apps",
    "E192": "High-precision instruments",
}

#: Series ordered from coarsest to finest.
SERIES_ORDER: List[str] = ["E6", "E12", "E24", "E48", "E96", "E192"]


def normalize_series(name: str) -> str:
    """Return the canonical series name (``"e24"`` -> ``"E24"``)."""
    key = str(name).strip().upper()
    if not key.startswith("E"):
        key = "E" + key
    if key not in SERIES:
        raise ValueError(
            f"unknown E-series '{name}' (choose from {', '.join(SERIES_ORDER)})"
        )
    return key


def nominal_tolerance(series: str) -> float:
    """Nominal tolerance in percent for ``series``."""
    return NOMINAL_TOLERANCE[normalize_series(series)]


def decade_values(series: str) -> List[float]:
    """Mantissas of ``series`` in the 1.0 - 9.99 decade."""
    return [m / 100 for m in SERIES[normalize_series(series)]]


def values_in_range(series: str, lo: float, hi: float) -> List[float]:
    """All values of ``series`` between ``lo`` and ``hi`` inclusive, sorted."""
    if lo <= 0 or hi <= 0:
        raise ValueError("component range limits must be positive")
    if lo > hi:
        lo, hi = hi, lo
    mantissas = SERIES[normalize_series(series)]
    out = []
    first = math.floor(math.log10(lo)) - 1
    last = math.ceil(math.log10(hi)) + 1
    for decade in range(first, last + 1):
        for m in mantissas:
            # Parse from a decimal string so 4.7e3 is exactly 4700.0.
            value = float(f"{m}e{decade - 2}")
            if lo * (1 - 1e-12) <= value <= hi * (1 + 1e-12):
                out.append(value)
    return out


def mantissa_of(value: float) -> int:
    """Three-digit mantissa of ``value`` (4700.0 -> 470)."""
    if value <= 0:
        raise ValueError("value must be positive")
    exponent = math.floor(math.log10(value) + 1e-12)
    return int(round(value / 10 ** (exponent - 2)))


def coarsest_series(value: float) -> str:
    """Name of the coarsest series that contains ``value`` (or ``""``)."""
    m = mantissa_of(value)
    for name in SERIES_ORDER:
        if m in SERIES[name]:
            return name
    return ""


def preference_score(value: float) -> int:
    """0 for an E6 value, 1 for E12, ... ; larger means less common."""
    name = coarsest_series(value)
    return SERIES_ORDER.index(name) if name else len(SERIES_ORDER)
