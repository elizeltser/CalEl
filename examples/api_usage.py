"""Using CalEl as a library.

Run from the repository root:  python examples/api_usage.py
"""

from calel.core import calculator
from calel.utils import formatting

# Divider: 12 V -> 3.3 V using 1 % E96 resistors around 100 kΩ total.
opts = calculator.Options(series="E96", tolerance=1, impedance=100e3, solutions=3)
result = calculator.divider(3.3, 12, opts)
print(formatting.render(result, "table"))

best = result.best
print(
    f"\nBest: R_high={formatting.format_eng(best.value('R_high'), 'Ω')}, "
    f"R_low={formatting.format_eng(best.value('R_low'), 'Ω')} -> "
    f"{best.achieved:.4f} V, worst case {best.spec_min:.4f} … {best.spec_max:.4f} V"
)

# Op-amp: inverting gain of -4.7 V/V, ranked by worst-case deviation from target.
result = calculator.opamp(-4.7, inverting=True, options=calculator.Options(rank="worst_case"))
print()
print(formatting.render(result, "markdown"))

# RC: 20-80 % rise time of 1 µs; E24 resistors with E6 capacitors.
result = calculator.rc(1e-6, "rise_2080", calculator.Options(series="E24", cap_series="E6"))
print()
print(formatting.render(result, "report"))
