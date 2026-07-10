"""Hardware-free analysis helpers for the 2A2T pre-hardware workflow."""

SYNTHETIC_SOURCE_TYPE = "SYNTHETIC"


def synthetic_metadata() -> dict[str, object]:
    """Return the mandatory provenance block for generated data."""

    return {"source_type": SYNTHETIC_SOURCE_TYPE, "hardware_verified": False}
