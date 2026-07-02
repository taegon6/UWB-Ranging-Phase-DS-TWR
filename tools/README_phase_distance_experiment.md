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

If `*.map.png` has no position points, check the real anchor spacing. For
example, if `BaselineM=2.5` but both measured distances are around `0.7 m`, the
two circles cannot intersect.
