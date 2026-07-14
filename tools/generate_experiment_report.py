#!/usr/bin/env python3
"""Generate the Markdown report for a completed mock run directory."""

from __future__ import annotations

import argparse

from _common import root_relative

from analysis.report_generator import generate_experiment_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    args = parser.parse_args()
    path = generate_experiment_report(root_relative(args.run_dir))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
