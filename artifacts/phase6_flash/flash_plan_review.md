# Phase 6 Flash Plan Review (dry-run)

source_type = CODE_INSPECTION_AND_BUILD
hardware_verified = false
flash_executed = false
execution_allowed = false

- Status: `FLASH_PLAN_BLOCKED_BUILD_FAILURE`.
- Planned order only: `A1 -> A2 -> T2 -> T1`; T1 is last because it is the coordinator.
- Failure policy: stop on first failure; no automatic rollback.
- Every probe serial, UART port, and image hash remains unresolved; the file contains no executable J-Link command.
