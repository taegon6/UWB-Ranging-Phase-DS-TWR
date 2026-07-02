#!/usr/bin/env python3
"""Fuse two-anchor UWB ranges with TurtleBot cmd_vel commands using EKF.

This is an offline post-processing tool. It does not use odometry. The motion
model uses only the commanded linear.x and angular.z values.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uwb_csv", help="Position CSV from collect_tag_two_anchor_position.py")
    parser.add_argument("cmd_vel_csv", help="CSV with elapsed_s, linear.x, angular.z")
    parser.add_argument("--out", help="Output fused CSV path")
    parser.add_argument("--plot", help="Output plot PNG path")
    parser.add_argument("--baseline-m", type=float, default=None)
    parser.add_argument("--range-std-m", type=float, default=0.15)
    parser.add_argument("--cmd-v-std-mps", type=float, default=0.08)
    parser.add_argument("--cmd-w-std-radps", type=float, default=0.10)
    parser.add_argument(
        "--cmd-v-scale",
        type=float,
        default=1.0,
        help="Scale factor applied to cmd_vel linear.x before EKF prediction.",
    )
    parser.add_argument("--theta-std-deg", type=float, default=45.0)
    parser.add_argument("--position-std-m", type=float, default=0.5)
    parser.add_argument("--velocity-response", type=float, default=6.0, help="1/s first-order response from v to cmd_v")
    parser.add_argument("--initial-heading-deg", type=float, default=None)
    parser.add_argument("--initial-x-m", type=float, default=None)
    parser.add_argument("--initial-y-m", type=float, default=None)
    parser.add_argument("--known-start-x-m", type=float, default=None)
    parser.add_argument("--known-start-y-m", type=float, default=None)
    parser.add_argument("--known-end-x-m", type=float, default=None)
    parser.add_argument("--known-end-y-m", type=float, default=None)
    parser.add_argument(
        "--auto-calibrate-endpoints",
        action="store_true",
        help="Use known start/end to set initial pose and cmd_v scale for this post-processing run.",
    )
    parser.add_argument("--cmd-time-offset-s", type=float, default=0.0)
    parser.add_argument(
        "--time-align",
        choices=["auto", "elapsed", "absolute"],
        default="auto",
        help=(
            "How to align cmd_vel to UWB time. auto/absolute use cmd Unix "
            "timestamp and UWB ISO timestamp when available; elapsed uses only "
            "cmd elapsed_s plus --cmd-time-offset-s."
        ),
    )
    parser.add_argument(
        "--after-last-cmd",
        choices=["zero", "hold"],
        default="zero",
        help="Command to use after cmd_vel log ends.",
    )
    return parser.parse_args()


def read_uwb(path: Path) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "ok":
                continue
            try:
                rows.append(
                    {
                        "elapsed_s": float(row["elapsed_s"]),
                        "timestamp": row.get("timestamp", ""),
                        "baseline_m": float(row.get("baseline_m") or 2.5),
                        "d_anchor_a_m": float(row["d_anchor_a_m"]),
                        "d_anchor_b_m": float(row["d_anchor_b_m"]),
                        "x_m": float(row["x_m"]),
                        "y_m": float(row["y_m"]),
                    }
                )
            except (KeyError, ValueError):
                continue
    return rows


def read_cmd(path: Path, offset_s: float) -> list[tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            elapsed = float(row["elapsed_s"]) + offset_s
            linear = float(row.get("linear.x", row.get("linear_x_mps", "0")))
            angular = float(row.get("angular.z", row.get("angular_z_radps", "0")))
            rows.append((elapsed, linear, angular))
    rows.sort(key=lambda item: item[0])
    return rows


def parse_local_timestamp(value: str) -> dt.datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        # UWB collector writes local ISO timestamps, for example
        # 2026-07-02T16:10:37.697.
        return dt.datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        # TurtleBot cmd_vel logs may write Unix epoch seconds.
        return dt.datetime.fromtimestamp(float(text))
    except ValueError:
        return None


def infer_cmd_time_offset(uwb_rows: list[dict[str, float | str]], cmd_path: Path) -> float | None:
    if not uwb_rows:
        return None
    uwb_first = uwb_rows[0]
    uwb_abs = parse_local_timestamp(str(uwb_first.get("timestamp", "")))
    if uwb_abs is None:
        return None
    uwb_origin = uwb_abs - dt.timedelta(seconds=float(uwb_first["elapsed_s"]))
    with cmd_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cmd_abs = parse_local_timestamp(row.get("timestamp", ""))
            if cmd_abs is None:
                continue
            try:
                cmd_elapsed = float(row["elapsed_s"])
            except (KeyError, ValueError):
                continue
            cmd_origin = cmd_abs - dt.timedelta(seconds=cmd_elapsed)
            return (cmd_origin - uwb_origin).total_seconds()
    return None


def command_at(commands: list[tuple[float, float, float]], t: float, after_last: str) -> tuple[float, float]:
    if not commands:
        return 0.0, 0.0
    if t < commands[0][0]:
        return 0.0, 0.0
    lo, hi = 0, len(commands) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if commands[mid][0] <= t:
            lo = mid + 1
        else:
            hi = mid - 1
    idx = max(0, hi)
    if idx == len(commands) - 1 and t > commands[-1][0] and after_last == "zero":
        return 0.0, 0.0
    return commands[idx][1], commands[idx][2]


def infer_heading(rows: list[dict[str, float | str]], commands: list[tuple[float, float, float]]) -> float:
    if not rows:
        return math.pi / 2.0
    end_time = commands[-1][0] if commands else float(rows[-1]["elapsed_s"])
    points = [r for r in rows if float(r["elapsed_s"]) <= end_time]
    if len(points) < 2:
        points = rows
    dx = float(points[-1]["x_m"]) - float(points[0]["x_m"])
    dy = float(points[-1]["y_m"]) - float(points[0]["y_m"])
    if math.hypot(dx, dy) < 1e-6:
        return math.pi / 2.0
    return math.atan2(dy, dx)


def wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def transpose(a: list[list[float]]) -> list[list[float]]:
    return [list(row) for row in zip(*a)]


def matadd(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def inv2(m: list[list[float]]) -> list[list[float]]:
    det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
    if abs(det) < 1e-12:
        det = 1e-12 if det >= 0 else -1e-12
    return [[m[1][1] / det, -m[0][1] / det], [-m[1][0] / det, m[0][0] / det]]


def run_ekf(
    rows: list[dict[str, float | str]],
    commands: list[tuple[float, float, float]],
    baseline: float,
    args: argparse.Namespace,
) -> list[dict[str, float | str]]:
    if not rows:
        return []
    if args.auto_calibrate_endpoints:
        missing = [
            name
            for name in ["known_start_x_m", "known_start_y_m", "known_end_x_m", "known_end_y_m"]
            if getattr(args, name) is None
        ]
        if missing:
            raise SystemExit(f"--auto-calibrate-endpoints requires: {', '.join('--' + name.replace('_', '-') for name in missing)}")
        dx = args.known_end_x_m - args.known_start_x_m
        dy = args.known_end_y_m - args.known_start_y_m
        true_distance = math.hypot(dx, dy)
        commanded_distance = integrate_commands(commands, float(rows[0]["elapsed_s"]), float(rows[-1]["elapsed_s"]), args.after_last_cmd)
        if commanded_distance > 1e-9:
            args.cmd_v_scale = true_distance / commanded_distance
        args.initial_x_m = args.known_start_x_m
        args.initial_y_m = args.known_start_y_m
        args.initial_heading_deg = math.degrees(math.atan2(dy, dx))

    theta0 = math.radians(args.initial_heading_deg) if args.initial_heading_deg is not None else infer_heading(rows, commands)
    initial_x = args.initial_x_m if args.initial_x_m is not None else float(rows[0]["x_m"])
    initial_y = args.initial_y_m if args.initial_y_m is not None else float(rows[0]["y_m"])
    state = [initial_x, initial_y, theta0, 0.0]
    theta_var = math.radians(args.theta_std_deg) ** 2
    p = [
        [args.position_std_m**2, 0.0, 0.0, 0.0],
        [0.0, args.position_std_m**2, 0.0, 0.0],
        [0.0, 0.0, theta_var, 0.0],
        [0.0, 0.0, 0.0, args.cmd_v_std_mps**2],
    ]
    r_mat = [[args.range_std_m**2, 0.0], [0.0, args.range_std_m**2]]
    out: list[dict[str, float | str]] = []
    last_t = float(rows[0]["elapsed_s"])

    for row in rows:
        t = float(row["elapsed_s"])
        dt = max(1e-3, t - last_t)
        last_t = t
        cmd_v, cmd_w = command_at(commands, t, args.after_last_cmd)
        cmd_v *= args.cmd_v_scale
        x, y, theta, v = state
        alpha = max(0.0, args.velocity_response)
        beta = min(1.0, alpha * dt)
        v_pred = v + beta * (cmd_v - v)
        theta_pred = wrap_angle(theta + cmd_w * dt)
        x_pred = x + v_pred * math.cos(theta_pred) * dt
        y_pred = y + v_pred * math.sin(theta_pred) * dt

        # Jacobian of process model wrt [x, y, theta, v].
        f = [
            [1.0, 0.0, -v_pred * math.sin(theta_pred) * dt, math.cos(theta_pred) * dt * (1.0 - beta)],
            [0.0, 1.0, v_pred * math.cos(theta_pred) * dt, math.sin(theta_pred) * dt * (1.0 - beta)],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0 - beta],
        ]
        q = [
            [(args.cmd_v_std_mps * dt) ** 2, 0.0, 0.0, 0.0],
            [0.0, (args.cmd_v_std_mps * dt) ** 2, 0.0, 0.0],
            [0.0, 0.0, (args.cmd_w_std_radps * dt) ** 2, 0.0],
            [0.0, 0.0, 0.0, (args.cmd_v_std_mps * beta) ** 2],
        ]
        state = [x_pred, y_pred, theta_pred, v_pred]
        p = matadd(matmul(matmul(f, p), transpose(f)), q)

        anchors = [(0.0, 0.0), (baseline, 0.0)]
        z = [float(row["d_anchor_a_m"]), float(row["d_anchor_b_m"])]
        h_rows: list[list[float]] = []
        z_hat: list[float] = []
        for ax, ay in anchors:
            dx = state[0] - ax
            dy = state[1] - ay
            dist = max(1e-6, math.hypot(dx, dy))
            z_hat.append(dist)
            h_rows.append([dx / dist, dy / dist, 0.0, 0.0])
        hp = matmul(h_rows, p)
        s = matadd(matmul(hp, transpose(h_rows)), r_mat)
        k_gain = matmul(matmul(p, transpose(h_rows)), inv2(s))
        residual = [z[0] - z_hat[0], z[1] - z_hat[1]]
        state = [state[i] + sum(k_gain[i][j] * residual[j] for j in range(2)) for i in range(4)]
        state[2] = wrap_angle(state[2])
        kh = matmul(k_gain, h_rows)
        i_minus_kh = [[(1.0 if i == j else 0.0) - kh[i][j] for j in range(4)] for i in range(4)]
        p = matmul(i_minus_kh, p)

        speed = abs(state[3])
        out_row = dict(row)
        out_row.update(
            {
                "cmd_linear_x_mps": cmd_v,
                "cmd_angular_z_radps": cmd_w,
                "x_cmd_ekf_m": state[0],
                "y_cmd_ekf_m": state[1],
                "theta_cmd_ekf_deg": math.degrees(state[2]),
                "v_cmd_ekf_mps": state[3],
                "heading_cmd_ekf_deg": math.degrees(state[2]) if speed > 1e-4 else "",
                "speed_cmd_ekf_mps": speed,
                "range_residual_a_m": residual[0],
                "range_residual_b_m": residual[1],
            }
        )
        out.append(out_row)
    return out


def write_csv(path: Path, rows: list[dict[str, float | str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def integrate_commands(commands: list[tuple[float, float, float]], start_s: float, end_s: float, after_last: str) -> float:
    if end_s <= start_s:
        return 0.0
    # Integrate on the command sample grid plus endpoints.
    times = [start_s]
    times.extend(t for t, _, _ in commands if start_s < t < end_s)
    times.append(end_s)
    total = 0.0
    for t0, t1 in zip(times, times[1:]):
        mid = (t0 + t1) / 2.0
        cmd_v, _ = command_at(commands, mid, after_last)
        total += cmd_v * max(0.0, t1 - t0)
    return total


def write_plot(path: Path, rows: list[dict[str, float | str]], baseline: float) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plot")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_x = [float(r["x_m"]) for r in rows]
    raw_y = [float(r["y_m"]) for r in rows]
    ekf_x = [float(r["x_cmd_ekf_m"]) for r in rows]
    ekf_y = [float(r["y_cmd_ekf_m"]) for r in rows]
    plt.figure(figsize=(7, 6))
    plt.plot(raw_x, raw_y, ".", ms=1.5, alpha=0.45, label="raw two-anchor xy")
    plt.plot(ekf_x, ekf_y, linewidth=2.0, label="cmd_vel + range EKF")
    plt.scatter([0.0, baseline], [0.0, 0.0], marker="^", s=100, color="red", label="anchors")
    plt.axis("equal")
    plt.grid(True, alpha=0.3)
    plt.xlabel("x [m]")
    plt.ylabel("y [m]")
    plt.title("TurtleBot cmd_vel + UWB range EKF")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def summarize(rows: list[dict[str, float | str]]) -> None:
    if len(rows) < 2:
        return
    raw_dx = float(rows[-1]["x_m"]) - float(rows[0]["x_m"])
    raw_dy = float(rows[-1]["y_m"]) - float(rows[0]["y_m"])
    ekf_dx = float(rows[-1]["x_cmd_ekf_m"]) - float(rows[0]["x_cmd_ekf_m"])
    ekf_dy = float(rows[-1]["y_cmd_ekf_m"]) - float(rows[0]["y_cmd_ekf_m"])
    raw_net = math.hypot(raw_dx, raw_dy)
    ekf_net = math.hypot(ekf_dx, ekf_dy)
    raw_heading = math.degrees(math.atan2(raw_dy, raw_dx))
    ekf_heading = math.degrees(math.atan2(ekf_dy, ekf_dx))
    cmd_distance = sum(float(rows[i]["cmd_linear_x_mps"]) * max(0.0, float(rows[i]["elapsed_s"]) - float(rows[i - 1]["elapsed_s"])) for i in range(1, len(rows)))
    print(f"rows: {len(rows)}")
    print(f"raw net displacement: {raw_net:.3f} m, heading {raw_heading:.2f} deg")
    print(f"cmd_vel EKF net displacement: {ekf_net:.3f} m, heading {ekf_heading:.2f} deg")
    print(f"integrated cmd distance over UWB duration: {cmd_distance:.3f} m")
    print(f"final EKF theta: {float(rows[-1]['theta_cmd_ekf_deg']):.2f} deg")


def main() -> int:
    args = parse_args()
    uwb_path = Path(args.uwb_csv)
    cmd_path = Path(args.cmd_vel_csv)
    rows = read_uwb(uwb_path)
    if not rows:
        raise SystemExit("No valid UWB rows found")
    offset_s = args.cmd_time_offset_s
    inferred_offset_s = None
    if args.time_align in {"auto", "absolute"}:
        inferred_offset_s = infer_cmd_time_offset(rows, cmd_path)
        if inferred_offset_s is None:
            if args.time_align == "absolute":
                raise SystemExit("Could not infer absolute timestamp alignment from UWB/cmd_vel timestamps")
            print("timestamp alignment: elapsed_s only; absolute timestamps not available")
        else:
            offset_s += inferred_offset_s
            print(f"timestamp alignment: cmd_vel offset {offset_s:+.3f} s")
    else:
        print(f"timestamp alignment: elapsed_s, cmd_vel offset {offset_s:+.3f} s")
    commands = read_cmd(cmd_path, offset_s)
    baseline = args.baseline_m if args.baseline_m is not None else float(rows[0]["baseline_m"])
    out_path = Path(args.out) if args.out else uwb_path.with_suffix("").with_name(uwb_path.stem + ".cmd_ekf.csv")
    plot_path = Path(args.plot) if args.plot else uwb_path.with_suffix("").with_name(uwb_path.stem + ".cmd_ekf.png")
    fused = run_ekf(rows, commands, baseline, args)
    write_csv(out_path, fused)
    write_plot(plot_path, fused, baseline)
    summarize(fused)
    print(f"output csv: {out_path}")
    print(f"plot png: {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
