# UWB Ranging Optimization Follow-up

## Pre-hardware 2A2T environment

The repository now includes a hardware-free experiment foundation for future
A1/A2/T1/T2 work. It preserves the existing A1/B2/TG firmware overlay and does
not claim real 2A2T operation.

```text
source_type = SYNTHETIC
hardware_verified = false
```

Run from this repository root:

```powershell
python tools\check_environment.py
python tools\run_hardware_experiment.py --config configs\mock_hardware.yaml --experiment timing_characterization --backend mock --dry-run --analyze --report
python tools\calibrate_antenna_delay.py --config configs\antenna_calibration.example.yaml --backend mock --dry-run
```

Start with [docs/PRE_HARDWARE_SETUP.md](docs/PRE_HARDWARE_SETUP.md) and
[HANDOFF.md](HANDOFF.md). Real wiring and input fields are listed in
[docs/HARDWARE_CONNECTION_CHECKLIST.md](docs/HARDWARE_CONNECTION_CHECKLIST.md).

This folder preserves the local two-anchor DS-TWR ranging work prepared from
`FastTurtle7892/UWB-Ranging-Optimization`.

## Contents

- `tools/`: local UART collection, plotting, and analysis helpers.
- `firmware_overlay/`: source files to overlay onto the upstream
  `UWB-Ranging-Optimization` firmware tree.
- `phase_ds_twr_two_anchor.patch`: the full patch captured from the clean
  upload branch.

## Current Experiment Setup

- Hardware: nRF52840-DK + DWS/DW3000 boards
- Mode: phase-corrected DS-TWR on CH9
- Layout: two anchors, one tag
- Anchor coordinates: A1 `(0, 0)`, B2 `(baseline, 0)`
- Tag UART output expected by the tools:

```text
ANCHOR:A1 DIST: 0.779 m
ANCHOR:B2 DIST: 1.024 m
```

## Fast Run Command

From an upstream `UWB-Ranging-Optimization` checkout with the firmware already
flashed:

```powershell
python tools\collect_tag_two_anchor_position.py `
  --tag-port COM8 `
  --baseline-m 2.5 `
  --duration 60 `
  --height-diff-m 0.37 `
  --tag phase_ds_twr_run `
  --out-dir logs\phase_distance_run
```

or:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_phase_distance_experiment.ps1 `
  -TagPort COM8 `
  -BaselineM 2.5 `
  -DurationS 60 `
  -HeightDiffM 0.37 `
  -MedianWindow 1 `
  -Tag phase_ds_twr_run
```

## TurtleBot UWB + cmd_vel Postprocess

Collect UWB first, then fuse the saved position CSV with a TurtleBot
`cmd_vel` CSV after the run:

```powershell
python tools\apply_cmd_vel_range_ekf.py `
  logs\phase_distance_run\run.position.csv `
  logs\cmd_vel\straight_01_cmd_vel.csv `
  --time-align auto `
  --auto-calibrate-endpoints `
  --known-start-x-m 0 `
  --known-start-y-m 4 `
  --known-end-x-m 1.03 `
  --known-end-y-m 2.06
```

The postprocess writes `*.cmd_ekf.csv` and `*.cmd_ekf.png` next to the UWB
CSV. Real logs, plots, and CSV outputs stay ignored by git.

## Notes

- Real experiment logs are intentionally not committed.
- A pre-existing project note says the responder overlay's `RNG_DELAY_MS = 5`
  changed a past local two-anchor UART observation from about 18 Hz to about
  90 Hz. That log is not present here, was not reproduced in this task, and is
  not a verified timing result for the current environment.
- If the 2D map has no valid positive-y points, check that the physical anchor
  spacing matches `--baseline-m`.
