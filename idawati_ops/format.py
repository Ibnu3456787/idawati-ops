"""Plain-text table rendering (no dependencies)."""

from __future__ import annotations


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render headers + rows as an aligned plain-text table.

    Columns are sized to the widest cell (header included), separated by two
    spaces. An empty row list renders the headers plus a ``(no rows)`` line.
    """
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    if not rows:
        lines.append("(no rows)")
    else:
        lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)
