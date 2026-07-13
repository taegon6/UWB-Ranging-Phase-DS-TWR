from __future__ import annotations

from pathlib import Path

from tools.phase6_toolchain_source_recovery import (
    KNOWN_MISSING_REFS,
    classify_reference_usage,
    classify_toolchain,
    evaluate_source_candidates,
    hash_invariant,
    is_placeholder_source,
    recovery_gate,
    runtime_header_contract,
)


def test_recovery_scope_tracks_all_fifteen_recorded_missing_sources() -> None:
    assert len(KNOWN_MISSING_REFS) == 15
    assert len(set(KNOWN_MISSING_REFS)) == 15


def test_exact_toolchain_version_mismatch_is_not_accepted() -> None:
    evidence = classify_toolchain(
        "C:/Program Files/SEGGER/SEGGER Embedded Studio for ARM 5.68/lib/libc.a",
        [{"version": "8.28", "executable_sha256": "a" * 64}],
    )
    assert evidence["classification"] == "TOOLCHAIN_FAMILY_IDENTIFIED"
    assert evidence["exact_installed"] is False


def test_duplicate_candidates_with_distinct_hashes_are_ambiguous(tmp_path: Path) -> None:
    first, second = tmp_path / "a.c", tmp_path / "b.c"
    first.write_text("int a;\n", encoding="utf-8")
    second.write_text("int b;\n", encoding="utf-8")
    result = evaluate_source_candidates([first, second])
    assert result["decision"] == "REJECTED_AMBIGUOUS"


def test_candidate_hash_mismatch_and_placeholder_are_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.c"
    candidate.write_text("/* PLACEHOLDER: replace me */\n", encoding="utf-8")
    assert is_placeholder_source(candidate)
    result = evaluate_source_candidates([candidate], expected_sha256="0" * 64)
    assert result["decision"] == "REJECTED_PLACEHOLDER"


def test_candidate_hash_mismatch_is_rejected_without_placeholder(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.c"
    candidate.write_text("int real_source;\n", encoding="utf-8")
    assert evaluate_source_candidates([candidate], expected_sha256="0" * 64)["decision"] == "REJECTED_HASH_MISMATCH"


def test_legacy_runtime_header_contract_mismatch_is_blocking() -> None:
    result = runtime_header_contract('#include "__vfprintf.h"\n', set())
    assert result["status"] == "RUNTIME_HEADER_MISMATCH"


def test_baseline_and_2a2t_hash_invariant_detects_change(tmp_path: Path) -> None:
    source = tmp_path / "baseline.c"
    source.write_text("int baseline;\n", encoding="utf-8")
    expected = hash_invariant({"baseline.c": source.read_bytes()}, tmp_path)
    assert expected["unchanged"] is True
    source.write_text("int changed;\n", encoding="utf-8")
    assert hash_invariant({"baseline.c": b"int baseline;\n"}, tmp_path)["unchanged"] is False


def test_inactive_reference_is_not_equated_to_a_resolved_source() -> None:
    inactive = classify_reference_usage("../Src/urop_2/custom_ds_twr_responder.c", set())
    unresolved = classify_reference_usage("../Src/custom_code/switching.c", set())
    assert inactive == "INACTIVE_REFERENCE_PROVEN"
    assert unresolved == "ACTIVE_OR_UNRESOLVED_REFERENCE"


def test_provenance_gate_blocks_baseline_four_image_and_flash() -> None:
    plan = recovery_gate("TOOLCHAIN_FAMILY_IDENTIFIED", [{"blocking": True, "candidate_decision": "NO_CANDIDATE"}])
    assert plan["allow_baseline_build"] is False
    assert plan["allow_four_image_build"] is False
    assert plan["allow_flash_execute"] is False
    assert plan["allow_execute"] is False


def test_many_unresolved_sources_make_the_legacy_environment_not_ready() -> None:
    plan = recovery_gate("TOOLCHAIN_FAMILY_IDENTIFIED", [{"blocking": True, "candidate_decision": "NO_CANDIDATE"}] * 15)
    assert plan["outcome"] == "LEGACY_BUILD_ENVIRONMENT_NOT_READY"
