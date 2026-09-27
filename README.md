
# CalEl - Universal Passive Component Calculator for Circuit Design
 
## Overview
 
**CalEl** is a universal Python tool that finds the closest standard passive component values for analog circuit design. Whether you're designing resistor dividers, RC filters, or op-amp feedback networks, CalEl suggests optimal component values from industry-standard E-series (E6, E12, E24, E96, E192) in both CLI and GUI modes. Completely self-contained—no external dependencies.
 
## Problem Statement
 
Designing analog circuits often requires finding standard resistor/capacitor values that achieve target specifications (gain, frequency response, voltage dividers). Manually searching through E-series tables is tedious and error-prone. CalEl automates this, returning the closest standard values and highlighting actual achieved performance.
 
## Features
 
- ✅ **Resistor divider calculator** – Find R_high and R_low for target output voltage
- ✅ **Op-amp feedback network design** – Inverting and non-inverting topologies
- ✅ **RC filter/corner frequency** – Multiple input formats (tau, rise time, frequency, impedance product)
- ✅ **Flexible filtering** – Select by E-series standard (E6, E12, E24, E48, E96, E192), separately for resistors and capacitors
- ✅ **Multiple solutions** – Ranked by criteria (closest match, lowest tolerance stack, preferred values)
- ✅ **Tolerance analysis** – Shows tolerance stack-up and actual gain variation (±1%, ±5%)
- ✅ **Zero external dependencies** – Pure Python, CLI and GUI support
- ✅ **Output flexibility** – Raw values, formatted tables, detailed reports, CSV, JSON, Markdown, LaTeX
- ✅ **GUI** – tkinter app with real-time results, charts, themes and export (`calel --gui` or `calel-gui`)
## Installation
 
### Prerequisites
- Python 3.8 or higher
- No external packages required
### Setup
 
```bash
# Clone repository
git clone <repo-url>
cd calel
 
# Create virtual environment
python -m venv .venv
 
# Activate (Linux/macOS)
source .venv/bin/activate
 
# Activate (Windows)
.venv\Scripts\activate
 
# Install package
pip install -e .
```
 
## Quick Start
 
### Basic Usage
 
```bash
# Show help
calel --help
 
# Resistor divider: target 1.8V from 5V rail
calel --targ_v 1.8 --rail_v 5
 
# Filtered by series
calel --targ_v 1.8 --rail_v 5 --series E24
 
# Op-amp non-inverting gain: 100 V/V
calel --opamp_non_inv_vv 100
 
# Op-amp inverting gain: 60 dB
calel --opamp_inv_dB 60
 
# RC corner frequency: 100 Hz
calel --targ_corner_hz 100
 
# RC rise time (10%-90%): 10 microseconds (SI prefixes work: 10u)
calel --targ_rise_1090 10e-6

# Launch the GUI
calel --gui
```

### All Options

| Option | Meaning |
|--------|---------|
| `--targ_v V --rail_v V` | Resistor divider output from a rail |
| `--opamp_non_inv_vv G` / `--opamp_non_inv_dB dB` | Non-inverting gain |
| `--opamp_inv_vv G` / `--opamp_inv_dB dB` | Inverting gain (sign ignored) |
| `--targ_corner_hz Hz` / `--targ_corner_rad rad/s` | RC corner frequency |
| `--targ_tau s` (alias `--targ_rc`) | RC time constant / impedance product |
| `--targ_rise_1090 s` / `--targ_rise_2080 s` | RC rise time |
| `--series E24` | Resistor series (also capacitors unless `--cap_series`) |
| `--tolerance PCT` / `--cap_tolerance PCT` | Part tolerances (default: series nominal) |
| `--cap_series E12` | Capacitor series for RC |
| `--solutions N`, `-n N` | Number of solutions (default 5) |
| `--rank error\|worst_case\|preferred` | Closest match, lowest worst-case deviation, or most common values |
| `--impedance OHMS` | Preferred network resistance (R_high+R_low, Rf+Rg, or R for RC; default 10k) |
| `--prefer_low_values` | Lowest resistances (dividers/op-amps) or smallest capacitor (RC) |
| `--r_min/--r_max/--c_min/--c_max` | Component search range (default 10Ω–1MΩ, 10pF–100µF) |
| `--format`, `-f` | `table`, `raw`, `report`, `csv`, `json`, `markdown`, `latex` |
| `--output FILE`, `-o` | Write to a file |
| `--color auto\|always\|never` | Coloured output (honours `NO_COLOR`) |
| `--list_series [E24]` | Show the series table or one series' values |

Numbers accept SI prefixes and units: `4.7k`, `4k7`, `100n`, `10u`, `1.8V`, `1meg` (`m` = milli, `M` = mega).
Defaults can be stored in a JSON config file (path shown at the end of `calel --help`, override with `CALEL_CONFIG`).
 
## Usage Guide
 
### Resistor Divider
 
```bash
calel --targ_v 1.8 --rail_v 5 --series E24 --tolerance 1 --solutions 5
```
 
**Output:**
```
Target: 1.8V from 5V rail
Series: E24 (±1% tolerance)

Rank  R_high  R_low  V_out   Error   Tol(WC)  Tol(RSS)
1.    11kΩ    6.2kΩ  1.802V  +0.13%  ±1.28%   ±0.90%
2.    3.9kΩ   2.2kΩ  1.803V  +0.18%  ±1.28%   ±0.90%
3.    9.1kΩ   5.1kΩ  1.796V  -0.23%  ±1.29%   ±0.91%
4.    10kΩ    5.6kΩ  1.795V  -0.28%  ±1.29%   ±0.91%
5.    12kΩ    6.8kΩ  1.809V  +0.47%  ±1.28%   ±0.90%
```

`Tol(WC)` is the worst-case spread of the output with every part at its tolerance limit;
`Tol(RSS)` is the statistical root-sum-square estimate. The error column is coloured green
(within ¼ of the tolerance), yellow (within the tolerance) or red (outside it).
 
### Op-Amp Feedback Network
 
```bash
calel --opamp_non_inv_vv 100 --series E96 --tolerance 1 --solutions 3
```
 
**Output:**
```
Non-inverting amplifier: Target Gain = 100 V/V (40.00 dB)
Series: E96 (±1% tolerance)

Rank  R_feedback  R_ground  Gain(V/V)  Gain(dB)  Error   Tol(WC)  Tol(RSS)
1.    11.3kΩ      115Ω      99.26      39.94dB   -0.74%  ±2.00%   ±1.40%
2.    16.2kΩ      165Ω      99.18      39.93dB   -0.82%  ±2.00%   ±1.40%
3.    10.5kΩ      107Ω      99.13      39.92dB   -0.87%  ±2.00%   ±1.40%
```
 
### RC Filter/Corner Frequency
 
```bash
calel --targ_corner_hz 1000 --series E12
```
 
**Output:**
```
Target: f_c = 1kHz  (τ = 159.2µs)
Series: R E12 (±10%), C E12 (±10%)

Rank  R      C     f_c       tau      Error   Tol(WC)  Tol(RSS)
1.    4.7kΩ  33nF  1.026kHz  155.1µs  +2.61%  ±23.46%  ±14.14%
2.    3.9kΩ  39nF  1.046kHz  152.1µs  +4.64%  ±23.46%  ±14.14%
3.    5.6kΩ  27nF  1.053kHz  151.2µs  +5.26%  ±23.46%  ±14.14%
```

Use `-f report` to see the full working for each solution: formula, ideal ratio/product,
achieved range under tolerance, and per-component sensitivities.
 
## Technical Reference
 
### E-Series Standards
 
| Series | Count | Tolerance | Use Case |
|--------|-------|-----------|----------|
| E6     | 6     | ±20%      | Rough filtering, non-critical bias |
| E12    | 12    | ±10%      | General purpose, cost-sensitive |
| E24    | 24    | ±5%       | Standard production, feedback networks |
| E48    | 48    | ±2%       | Semi-precision networks |
| E96    | 96    | ±1%       | Precision analog, low-tolerance apps |
| E192   | 192   | ±0.5%     | High-precision instruments |
 
### Op-Amp Topologies Supported
 
1. **Non-Inverting**: Gain = 1 + (R_f / R_g)
2. **Inverting**: Gain = -(R_f / R_g)
### RC Time Constant Formats
 
- **tau (RC)**: Input as `XXeXX` seconds (e.g., `1e-6` = 1 µs)
- **Rise time (10%-90%)**: `t_rise = ln(9) * RC ≈ 2.2 * RC`
- **Rise time (20%-80%)**: `t_rise = ln(4) * RC ≈ 1.4 * RC`
- **Corner frequency (Hz)**: `f_c = 1 / (2π * R * C)`
- **Corner frequency (rad/s)**: `ω_c = 1 / (R * C)`

### Requirements Section
 
### Core Functionality
- [x] CLI argument parsing (argparse or custom)
- [x] E-series value databases (hardcoded, no external files)
- [x] Calculation engines for resistor divider, op-amp gain, RC values
- [x] Standard value matching algorithm (find closest match in series)
- [x] Tolerance stack-up calculation – Worst-case and RSS (root-sum-square) analysis for feedback network accuracy
### Enhanced Features
- [x] **Output formats** – CSV, JSON, markdown table, LaTeX
- [x] **GUI mode** – tkinter-based interface for interactive design
- [x] **Color-coded CLI output** – Warnings and errors highlighted
### User Experience
- [x] Help text explaining E-series standards with examples
- [x] Example outputs in --help command
- [x] Color-coded CLI output (warnings/errors)

### GUI Requirements
 
#### Core GUI Components
- [x] **Input Fields & Validation**
  - Target voltage/gain input with real-time validation
  - Rail voltage selector with preset values (3.3V, 5V, 12V, etc.)
  - Numeric input spinners with up/down buttons
  - Slider controls for selecting solution count
  - Series selection dropdown (E6, E12, E24, E96, E192)
  - Tolerance input with preset tolerances (±1%, ±5%, ±10%, ±20%)
#### Results Display & Visualization
- [x] **Dynamic Results Table**
  - Multi-column table (Rank, Component Values, Achieved Spec, Error %, Tolerance Stack)
  - Sortable columns (click to sort by different criteria)
  - Color-coded rows: green (excellent match), yellow (acceptable), red (poor match)
  - Copy-to-clipboard for individual results
  - Highlighted "best match" row
- [x] **Visualization Panels**
  - Gain vs Frequency plot (for RC filters)
  - Error percentage bar chart
  - Impedance/component value summary cards
#### Interactive Features
- [x] **Real-time Calculation**
  - Update results as user types/adjusts sliders
  - Debounce input to prevent excessive recalculation
  - Show calculation status (processing, complete, error)
#### User Interface & Layout
- [x] **Tab-Based Organization**
  - "Resistor Divider" tab
  - "Op-Amp Feedback" tab (inverting/non-inverting)
  - "RC Filter" tab (multiple frequency input options)
- [x] **Status Bar & Feedback**
  - Display current calculation time
  - Hint/help text for each input field
- [x] **Theme & Accessibility**
  - Light/dark mode toggle
  - High-contrast mode option
  - Adjustable font size
  - Tooltips for all controls
  - Keyboard shortcuts (Enter to calculate, Ctrl+S to save, etc.)
#### Advanced GUI Features
- [x] **Settings Panel**
  - Default series preference
  - Default tolerance preference
  - Preferred value filtering
- [x] **Help & Documentation**
  - Built-in help panel with examples
  - Interactive tutorials for each calculator type (Help → Tutorials, "Try it" loads each example)
  - Links to E-series standards documentation
  - Tooltips explaining tolerance stack-up concept
#### Performance & Reliability
- [x] **Error Handling UI**
  - Display clear error messages (not technical stack traces)
  - Suggest corrective actions
  - Highlight invalid input fields in red
  - Prevent invalid calculations
#### Platform & Integration
- [x] **Cross-Platform Support**
  - Windows, macOS, Linux native look-and-feel
  - Scaling for different DPI (high-res displays)
  - Touch-friendly input (for tablets if applicable) – via font/row scaling (Ctrl+=)
- [x] **Integration Points**
  - Copy results to system clipboard
  - Drag-and-drop file import/export – session files can be dropped on the window when the optional `tkdnd` Tk extension is installed; otherwise use File → Open session (Ctrl+O)
  - Print support for reports (Ctrl+P; `lp`/`lpr` on Linux/macOS, the shell print verb on Windows)

## Architecture Notes

Every calculator reduces the target to an ideal **ratio** (divider: `R_high/R_low = (1-k)/k`;
non-inverting: `Rf/Rg = G-1`; inverting: `Rf/Rin = |G|`) or **product** (RC: `R·C = τ`).
`matcher` then walks every standard value `b` in range, computes the ideal partner and takes
the standard values just below and above it, so all useful pairs are found in O(n log n).
Pairs that differ only by a decade shift (10k/5.6k vs 100k/56k) are collapsed, keeping the
variant closest to `--impedance` (or the lowest one with `--prefer_low_values`).

Tolerance stack-up evaluates every tolerance corner for the worst case and uses relative
sensitivities `S_i = ∂ln f/∂ln x_i` for RSS: `√Σ(S_i·tol_i)²`.
 
### Directory Structure
```
calel/
├── setup.py
├── calel/
│   ├── __main__.py          # CLI entry point
│   ├── core/
│   │   ├── e_series.py      # E-series databases
│   │   ├── calculator.py    # Core calculation logic
│   │   └── matcher.py       # Value matching & ranking
│   ├── cli/
│   │   └── parser.py        # CLI argument handling
│   ├── gui/
│   │   └── app.py           # tkinter GUI
│   └── utils/
│       ├── formatting.py    # Output formatting
│       └── config.py        # Configuration handling
├── tests/                   # unittest-style, run with pytest or unittest
├── examples/
│   ├── cli_examples.sh      # CLI tour
│   └── api_usage.py         # using CalEl as a library
└── README.md
```
 
### Key Design Principles
- **No dependencies** – Keep it portable and lightweight
- **Calculation transparency** – Show work, allow user to verify
- **Multiple solutions** – Don't force a single answer
## Examples
 
### Example 1: Design a 5V-to-1.8V Divider (±5% tolerance requirement)
```bash
calel --targ_v 1.8 --rail_v 5 --series E24 
```
 
### Example 2: Non-inverting Op-Amp Amplifier (Gain = 47 V/V, ±1% resistors)
```bash
calel --opamp_non_inv_vv 47 --series E96
```
 
### Example 3: RC Low-Pass Filter (Corner freq = 10 kHz, prefer smaller components)
```bash
calel --targ_corner_hz 10000 --series E24 --prefer_low_values
```
 
## Testing
 
```bash
# Run test suite
python -m pytest tests/

# Without pytest installed
python -m unittest discover -s tests

```
 
## Contributing
 
Contributions welcome! Please:
1. Add tests for new features
2. Follow PEP 8 style
3. Update this README with new functionality
## License
 
[Your License Here]
 
## Support
 
For issues, feature requests, or questions:
- Open an issue on GitHub
- Check existing examples in `/examples/`
- Review technical reference above
