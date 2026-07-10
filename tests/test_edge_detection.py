from __future__ import annotations

from pathlib import Path

from analysis.edge_detection import analyze_logic_capture, derive_timing, load_edges, pair_pulses

FIXTURES = Path(__file__).parent / "fixtures"


def test_logic_edge_pairing_and_missing_edge_detection(tmp_path: Path) -> None:
    edges = load_edges(FIXTURES / "synthetic_logic_capture.csv")
    pulses, errors = pair_pulses(edges, "CIR_READ")
    assert len(pulses) == 59
    assert any(error["error"] == "MISSING_FALL" for error in errors)


def test_irq_latency_and_outlier_are_derived() -> None:
    edges = load_edges(FIXTURES / "synthetic_logic_capture.csv")
    _, errors, summaries = derive_timing(edges)
    irq = next(row for row in summaries if row["metric"] == "irq_latency")
    assert irq["count"] == 60
    assert float(irq["max_us"]) > 20.0
    assert any(error["error"] == "MISSING_FALL" for error in errors)
    assert any(error["error"] == "STATISTICAL_OUTLIER" for error in errors)
    assert irq["source_type"] == "SYNTHETIC"
    assert irq["hardware_verified"] is False


def test_analyzer_writes_derived_tables(tmp_path: Path) -> None:
    result = analyze_logic_capture(
        FIXTURES / "synthetic_logic_capture.csv",
        edge_pairs_csv=tmp_path / "edge_pairs.csv",
        summary_csv=tmp_path / "summary.csv",
        errors_csv=tmp_path / "errors.csv",
    )
    assert result["raw_edge_count"] > result["paired_pulse_count"]
    assert result["error_count"] >= 1
    assert "SYNTHETIC" in (tmp_path / "summary.csv").read_text(encoding="utf-8")


def test_marker_segmentation_and_warmup_filter_without_embedded_frame_ids(tmp_path: Path) -> None:
    capture = tmp_path / "unsegmented.csv"
    capture.write_text(
        "timestamp_us,channel,value\n"
        "0,FRAME_START,1\n1,IRQ_PIN,1\n2,ISR_ACTIVE,1\n3,ISR_ACTIVE,0\n"
        "10,FRAME_START,1\n11,IRQ_PIN,1\n13,ISR_ACTIVE,1\n14,ISR_ACTIVE,0\n",
        encoding="utf-8",
    )
    edges = load_edges(capture)
    assert {edge.frame_id for edge in edges if edge.channel == "IRQ_PIN"} == {1, 2}
    result = analyze_logic_capture(
        capture,
        edge_pairs_csv=tmp_path / "pairs.csv",
        summary_csv=tmp_path / "summary.csv",
        errors_csv=tmp_path / "errors.csv",
        warmup_frames=1,
    )
    assert result["warmup_frames_excluded"] == 1
