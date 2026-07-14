"""Calibration mode declarations used by configuration and reports."""

CALIBRATION_MODES = (
    "COMBINED_SINGLE_LINK",
    "REFERENCE_NODE_SEQUENTIAL",
    "OFFLINE_2A2T_LEAST_SQUARES",
)

IDENTIFIABILITY_LIMITATION = (
    "Range bias alone does not separately identify per-node TX and RX delay; "
    "the unconstrained workflow estimates only combined contributions."
)
