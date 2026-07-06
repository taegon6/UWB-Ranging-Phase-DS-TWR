# UWB Ranging Optimization Follow-up

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
- The responder overlay uses `RNG_DELAY_MS = 5`, which improved the observed
  two-anchor tag UART rate from about 18 Hz to about 90 Hz in the local lab
  test.
- If the 2D map has no valid positive-y points, check that the physical anchor
  spacing matches `--baseline-m`.
