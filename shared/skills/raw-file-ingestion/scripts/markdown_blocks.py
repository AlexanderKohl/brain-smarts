"""Markdown blocks the converters write: a fenced block and a table that the content cannot break."""
from __future__ import annotations

import re


def fence(text: str, info: str = "") -> str:
    """`text` verbatim in a fenced block longer than any run of backticks inside it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{ticks}{info}\n{text}{ticks}"


def cell(value: str) -> str:
    """One table cell: a pipe would end the cell and a line end the row, so both are escaped."""
    return value.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>").strip()


def table(header: list[str], rows: list[list[str]]) -> str:
    """A Markdown table; a row shorter than the widest is padded with empty cells."""
    width = max([len(header)] + [len(row) for row in rows])

    def line(cells: list[str]) -> str:
        return "| " + " | ".join([cell(c) for c in cells] + [""] * (width - len(cells))) + " |"

    return "\n".join([line(header), "|" + "---|" * width] + [line(row) for row in rows])
