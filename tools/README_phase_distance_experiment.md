# Phase DS-TWR Distance Experiment Set

This runner is for the current phase-corrected DS-TWR test:

- A1 anchor at `(0, 0)`
- B2 anchor at `(baseline, 0)`
- one tag UART connected to the PC
- CH9 phase-corrected DS-TWR firmware already flashed

## Run

```powershell
cd path\to\UWB-Ranging-Optimization
powershell -ExecutionPolicy Bypass -File tools\run_phase_distance_experiment.ps1 `
  -TagPort COM8 `
  -BaselineM 2.5 `
  -DurationS 60 `
  -HeightDiffM 0.37 `
  -Tag phase_static_P1
```

If you want the red dashed reference lines to be a measured target distance
instead of the run mean:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_phase_distance_experiment.ps1 `
  -TagPort COM8 `
  -BaselineM 2.5 `
  -DurationS 60 `
  -Tag phase_static_P1 `
  -TargetACm 100 `
  -TargetBCm 180
```

## Outputs

Each run writes a matched experiment set under `logs\phase_distance_run`:

- `*.raw.txt`: raw tag UART lines
- `*.position.csv`: paired A1/B2 distances and positive-y position attempt
- `*.meta.json`: run metadata
- `*.map.png`: 2D map when the two distances intersect
- `*.distance_wave.png`: A1/B2 distance waveform in centimeters
- `*.summary.md`: short run summary

The position CSV also includes raw and height-corrected A1/B2 distances plus
range-level EKF columns. Use `HeightDiffM=0.37` when the tag is 37 cm lower
than the anchors.

## TurtleBot cmd_vel EKF

After collecting UWB, fuse it with a TurtleBot `cmd_vel` CSV:

```powershell
python tools\apply_cmd_vel_range_ekf.py `
  logs\phase_distance_run\run.position.csv `
  logs\cmd_vel\straight_01_cmd_vel.csv `
  --auto-calibrate-endpoints `
  --known-start-x-m 0 `
  --known-start-y-m 4 `
  --known-end-x-m 1.03 `
  --known-end-y-m 2.06
```

This is a postprocess step. The UWB collector can still run without any
TurtleBot command log.

If `*.map.png` has no position points, check the real anchor spacing. For
example, if `BaselineM=2.5` but both measured distances are around `0.7 m`, the
two circles cannot intersect.
