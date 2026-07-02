# UWB Two-Anchor Heading Experiment

This setup is for the current main workflow:

- two anchors: A1 and B2
- one tag connected to the PC by UART
- A1 at `(0, 0)`
- B2 at `(2.5, 0)`
- tag is only evaluated on the positive `y` side

## Lab Layout

```text
A1 (0,0) ---------------- B2 (2.5,0)
              +y
              |
              |
             tag
```

Keep the anchors at the same height and facing the test area. Measure the
anchor spacing with a tape measure and pass it as `-BaselineM`.

## Static Precision Run

Use this to check repeatability at a marked point. Keep the tag still for the
whole run.

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_tag_heading_experiment.ps1 `
  -Mode Static `
  -TagPort COM8 `
  -BaselineM 2.5 `
  -DurationS 60 `
  -Tag static_P1
```

Static mode uses a larger median window by default (`90` samples). This is good
for standard deviation checks, but it is not suitable for heading while moving.

## Moving Heading Run

Use this for trajectory and heading estimation. Move the tag along one planned
path during the capture.

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_tag_heading_experiment.ps1 `
  -Mode Moving `
  -TagPort COM8 `
  -BaselineM 2.5 `
  -DurationS 60 `
  -Tag moving_line_forward
```

Moving mode uses a shorter position median window by default (`10` samples),
then automatically runs:

```text
UWB position -> Kalman filter -> velocity heading
UWB position -> Kalman filter -> sliding PCA heading
```

## Recommended Paths

Start with simple marked paths:

- forward: `(1.25, 0.5)` to `(1.25, 2.5)`
- left/right: `(0.5, 1.5)` to `(2.0, 1.5)`
- diagonal: `(0.5, 0.8)` to `(2.0, 2.2)`
- L-shape: forward, then right

Move slowly and steadily for the first run. Heading is unreliable while the tag
is stopped, so the analysis keeps `is_moving=0` below the speed threshold.

## Outputs

Each run writes files under `logs\tag_heading_run` by default:

- `*.raw.txt`: raw tag UART lines
- `*.position.csv`: raw two-anchor position estimates
- `*.map.png`: positive-y 2D map
- `*.heading_kalman.csv`: Kalman trajectory, speed, and heading columns
- `*.heading_kalman.png`: trajectory/speed/heading plot

The heading CSV adds these columns:

```text
x_kalman_m,y_kalman_m,vx_mps,vy_mps,speed_mps,
heading_velocity_deg,heading_pca_deg,heading_pca_axis_deg,is_moving
```

## Tuning

Useful moving-mode knobs:

- `-MovingMedianWindow 5`: less delay, more noise
- `-MovingMedianWindow 10`: first recommended moving setting
- `-PcaWindowS 0.5`: faster PCA heading
- `-PcaWindowS 1.0`: smoother PCA heading
- `-MovingSpeedThreshold 0.15`: default stop/move cutoff

For a faster tag, lower `-PcaWindowS` and possibly raise `-AccelStd`.
