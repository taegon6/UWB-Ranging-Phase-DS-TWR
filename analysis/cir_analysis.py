"""Named CIR/phase timing definitions; no hardware values are embedded."""

METRIC_ENDPOINTS = {
    "cir_read_duration": ("CIR_READ:rising", "CIR_READ:falling"),
    "phase_processing_duration": ("PHASE_PROCESS:rising", "PHASE_PROCESS:falling"),
    "filter_duration": ("FILTER_ACTIVE:rising", "FILTER_ACTIVE:falling"),
}
