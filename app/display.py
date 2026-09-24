"""Small, consistent labels for PCB references across the interface."""

EMPTY_PART = "\u00a0" * 3


def pcb_label(pcb, include_model=True):
    """Format model, revision and serial with visible three-space empty parts."""
    fields = ("model", "revision", "serial") if include_model else ("revision", "serial")
    return " - ".join((getattr(pcb, field, "") or "").strip() or EMPTY_PART for field in fields)
