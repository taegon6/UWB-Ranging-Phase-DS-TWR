# 2A2T change log

## 2026-07-10 — pre-hardware environment foundation

- Preserved clean overlay baseline manifest, tracked file list and SHA-256 snapshot.
- Added repository/code analysis and parameter inventory without modifying baseline firmware sources.
- Added reproducible Python dependency locks and environment checker.
- Added Flash/UART/logic Protocols, guarded real adapters and deterministic fault-injectable mock backend.
- Added A1/A2/T1/T2 config/schema and build/flash dry-run orchestration.
- Added portable firmware trace null backend and timing metric contract.
- Added synthetic logic/UART/range fixtures, timing analyzer, UART recovery and antenna-delay dry-run solver.
- Added unified mock experiment runner, unique result archive and automatic report.
- Added connection/calibration documentation and unresolved hardware list.
- Applied timing repetitions/warm-up semantics, frame-marker segmentation, statistical outlier listing, and complete synthetic fault accounting in reports.
- Applied calibration sample/warm-up/objective configuration, three dry-run mode branches, point-bias tables, and measurement-metadata placeholders.
- Added full tracked/untracked source hash snapshots and artifact-level synthetic provenance markers.
- Hardened real-mode/backend matching, J-Link opt-in/command planning, sigrok duration/connection arguments, and raw/sidecar overwrite protection.

Status: `SIMULATED_NOT_HARDWARE_VERIFIED`.
