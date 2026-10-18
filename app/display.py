"""Small, consistent labels for PCB references across the interface."""

import re

from markupsafe import Markup, escape

EMPTY_PART = "\u00a0" * 3


def pcb_label(pcb, include_model=True):
    """Format model, revision and serial with visible three-space empty parts."""
    fields = ("model", "revision", "serial") if include_model else ("revision", "serial")
    return " - ".join((getattr(pcb, field, "") or "").strip() or EMPTY_PART for field in fields)


def search_excerpt(value, query, limit=200):
    """Show text around the first match so a result's keyword is visible."""
    value = value or ""
    if len(value) <= limit:
        return value
    match = re.search(re.escape(query), value, flags=re.IGNORECASE) if query else None
    position = match.start() if match else -1
    if position < 0:
        return value[:limit] + "…"
    start = max(0, position - min(50, limit // 4))
    end = min(len(value), start + max(limit, len(query)))
    return ("…" if start else "") + value[start:end] + ("…" if end < len(value) else "")


def highlight_match(value, query):
    """Escape user content before wrapping literal, case-insensitive matches."""
    value = str(value or "")
    if not query:
        return escape(value)
    pieces = re.split(f"({re.escape(query)})", value, flags=re.IGNORECASE)
    return Markup("".join(
        f'<mark class="search-match">{escape(part)}</mark>' if index % 2 else str(escape(part))
        for index, part in enumerate(pieces)
    ))
