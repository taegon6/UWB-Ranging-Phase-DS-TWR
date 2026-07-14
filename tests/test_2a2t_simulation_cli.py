from __future__ import annotations

from pathlib import Path

from tools.run_2a2t_parameter_simulation import run_simulation


ROOT = Path(__file__).resolve().parents[1]


def test_phase_0_to_4_runner_creates_canonical_synthetic_run(tmp_path: Path) -> None:
    run_dir = run_simulation(
        ROOT / "configs" / "simulation_2a2t_paper_baseline.yaml",
        ROOT / "configs" / "simulation_2a2t_parameter_sweep.yaml",
        tmp_path,
    )

    assert run_dir.name.endswith("_run01")
    required = [
        "question.md",
        "protocol.md",
        "run_matrix.md",
        "metadata.yaml",
        "run_log.md",
        "qc.md",
        "analysis_environment.md",
        "results/validation.md",
        "results/report.md",
        "closeout.md",
    ]
    for relative in required:
        content = (run_dir / relative).read_text(encoding="utf-8")
        assert "SYNTHETIC" in content
        assert "hardware_verified" in content
        assert "false" in content
    assert "phase_5_enabled: false" in (run_dir / "metadata.yaml").read_text(encoding="utf-8")
    assert (run_dir / "results" / "candidates.csv").is_file()
    assert (run_dir / "results" / "pareto_candidates.csv").is_file()
