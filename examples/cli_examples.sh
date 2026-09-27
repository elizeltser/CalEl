#!/usr/bin/env sh
# A tour of the calel command line. Run from the repository root with the
# package installed (pip install -e .).
set -e

echo "== 5 V -> 1.8 V divider, E24"
calel --targ_v 1.8 --rail_v 5 --series E24

echo; echo "== Non-inverting amplifier, G = 47 V/V, E96 1 % parts"
calel --opamp_non_inv_vv 47 --series E96

echo; echo "== Inverting amplifier, 60 dB, with a 100 kΩ-scale network"
calel --opamp_inv_dB 60 --impedance 1meg -n 3

echo; echo "== RC low-pass at 10 kHz, smallest capacitor"
calel --targ_corner_hz 10000 --series E24 --prefer_low_values

echo; echo "== 10 us rise time, E96 resistors with E12 capacitors"
calel --targ_rise_1090 10u --series E96 --cap_series E12 -n 3

echo; echo "== Full working for one design"
calel --targ_v 3.3 --rail_v 12 --series E96 -n 2 -f report

echo; echo "== Machine-readable exports"
calel --opamp_non_inv_vv 11 -f csv -n 3
calel --targ_corner_hz 1k -f json -n 1 | head -20
