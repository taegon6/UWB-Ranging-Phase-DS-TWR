# UWB Main Experiment: Two Anchors + One Tag

The main experiment mode is now:

- anchor A: `(0, 0)`
- anchor B: `(2.5, 0)`
- one tag estimated on a 2D map
- ranging mode label: `ss-twr` or `ds-twr`
- only the positive-`y` solution is kept

## Fast Start

Open this repository in VS Code:

```powershell
cd "C:\Users\User\Documents\학부연구생\research\uwb_followup\original_repos\UWB-Ranging-Optimization"
code .
```

Run either SS-TWR or DS-TWR:

```text
Ctrl+Shift+P -> Tasks: Run Task -> UWB MAIN SS: 2-anchor collect + analyze
Ctrl+Shift+P -> Tasks: Run Task -> UWB MAIN DS: 2-anchor collect + analyze
```

Inputs:

- Anchor A COM port, for example `COM3`
- Anchor B COM port, for example `COM4`
- Anchor spacing, default `2.5`
- Ranging mode, `ss-twr` or `ds-twr`
- Capture duration, for example `60`
- Run tag, for example `los_2anchor`

The main task automatically:

1. collects raw serial logs from both anchors,
2. converts the two distances to positive-`y` 2D tag positions,
3. saves a 2D map PNG,
4. generates a position summary report.

Outputs:

- `logs/*.anchorA.raw.txt`
- `logs/*.anchorB.raw.txt`
- `logs/*.position.csv`
- `logs/*.map.png`
- `logs/*.meta.json`
- `analysis/two_anchor_position_summary.csv`
- `analysis/two_anchor_position_summary.md`

Manual one-command run:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_two_anchor_experiment.ps1 -PortA COM3 -PortB COM4 -BaselineM 2.5 -RangingMode ss-twr -DurationS 60 -Tag los_2anchor_ss
```

For DS-TWR runs:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_two_anchor_experiment.ps1 -PortA COM3 -PortB COM4 -BaselineM 2.5 -RangingMode ds-twr -DurationS 60 -Tag los_2anchor_ds
```

## Firmware Example Selection

Use these tasks before building/flashing firmware:

- `UWB firmware: select SS initiator`
- `UWB firmware: select SS responder`
- `UWB firmware: select DS initiator`
- `UWB firmware: select DS responder`

Then run:

```text
Tasks: Run Task -> UWB: build current example
```

Manual equivalents:

```powershell
python tools\set_uwb_example.py ss-initiator
python tools\set_uwb_example.py ss-responder
python tools\set_uwb_example.py ds-initiator
python tools\set_uwb_example.py ds-responder
```

Dependencies:

```powershell
python -m pip install pyserial matplotlib
```

# DS-TWR Distance Logging

This folder contains local helper scripts for collecting and analyzing DW3000
DS-TWR `DIST: ... m` output.

## VS Code Flow

Open this repository in VS Code:

```powershell
cd "C:\Users\User\Documents\학부연구생\research\uwb_followup\original_repos\UWB-Ranging-Optimization"
code .
```

Run tasks with `Ctrl+Shift+P` -> `Tasks: Run Task`.

Useful tasks:

- `UWB: list serial ports`
- `UWB: collect distance log`
- `UWB: collect 2-anchor position map`
- `UWB: analyze distance logs`

`UWB: collect distance log` asks for:

- COM port, for example `COM3`
- mode: `origin` or `final`
- true measured distance in meters
- capture duration in seconds
- optional tag, for example `los_1m`

Outputs:

- `logs/*.raw.txt`: raw serial lines with timestamps
- `logs/*.dist.csv`: parsed distance samples
- `logs/*.meta.json`: capture metadata
- `analysis/distance_summary.csv`: numeric summary
- `analysis/distance_summary.md`: readable summary

## Manual Commands

Collect one 60-second final-mode run at 1.0 m:

```powershell
python tools\collect_distance_log.py --port COM3 --mode final --distance-m 1.0 --duration 60 --tag los_1m
```

Analyze all collected runs:

```powershell
python tools\analyze_distance_logs.py --log-dir logs --out-dir analysis
```

## Two-Anchor 2D Position Map

Use this when you have two anchors and one tag. The default geometry is:

- anchor A: `(0, 0)`
- anchor B: `(2.5, 0)`
- tag: estimated from the two measured ranges

Two-anchor ranging has two mirror-image solutions, one with positive `y` and
one with negative `y`. This workflow keeps only the positive-`y` solution.

Run from VS Code:

```text
Tasks: Run Task -> UWB: collect 2-anchor position map
```

Inputs:

- Anchor A COM port, for example `COM3`
- Anchor B COM port, for example `COM4`
- Anchor spacing, default `2.5`
- Capture duration
- Optional tag, for example `los_2anchor`

Manual command:

```powershell
python tools\collect_two_anchor_position.py --port-a COM3 --port-b COM4 --baseline-m 2.5 --duration 60 --tag los_2anchor
```

Outputs:

- `logs/*.anchorA.raw.txt`: raw serial output from anchor A
- `logs/*.anchorB.raw.txt`: raw serial output from anchor B
- `logs/*.position.csv`: timestamped `x,y` estimates
- `logs/*.map.png`: 2D map image with anchors and positive-y tag estimates

The position formula is:

```text
x = (dA^2 - dB^2 + B^2) / (2B)
y = sqrt(dA^2 - x^2)
```

where `B = 2.5 m`, `dA` is distance to anchor A, and `dB` is distance to
anchor B.

## Comparison Plan

Collect at least these four runs first:

- `origin`, 1.0 m, 60 seconds
- `final`, 1.0 m, 60 seconds
- `origin`, 2.0 m, 60 seconds
- `final`, 2.0 m, 60 seconds

Compare mean error, standard deviation, RMSE, p95 absolute error, and outlier
count. Lower standard deviation means the distance output is steadier. Lower
mean error/RMSE means it is closer to the ground-truth distance.
