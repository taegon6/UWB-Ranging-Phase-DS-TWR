"""CIR processing endpoint definitions."""

STAGES = (
    "accumulator_read",
    "signed_sample_decode",
    "phase_extraction",
    "phase_combination",
    "median_filter_update",
    "result_packaging",
)
