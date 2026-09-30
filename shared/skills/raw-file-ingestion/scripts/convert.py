"""Conversion of a raw file into the Markdown of its source record (CONTRACT §11.2, §11.4).

`convert(path)` reads the raw file, never changes it, and returns a `Conversion`: the status the
record carries in `conversion_status`, the extracted Markdown, and one note per limitation.
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from pathlib import Path

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".xml", ".html", ".htm", ".log", ".py", ".js", ".ts", ".css", ".sql"
}

# Byte-order marks, longest first: a UTF-32 little-endian mark begins with the UTF-16 one.
BOMS = [
    (codecs.BOM_UTF32_LE, "utf-32-le", "UTF-32"),
    (codecs.BOM_UTF32_BE, "utf-32-be", "UTF-32"),
    (codecs.BOM_UTF8, "utf-8", "UTF-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le", "UTF-16"),
    (codecs.BOM_UTF16_BE, "utf-16-be", "UTF-16"),
]


def lf(text: str) -> str:
    """Line ends as LF, as a universal-newline read gives them."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class Conversion:
    status: str                     # complete | partial | pending_conversion | failed
    markdown: str = ""
    notes: list[str] = field(default_factory=list)


def decode(data: bytes) -> Conversion:
    """Text from a text file's bytes: UTF-8, or the encoding its byte-order mark names."""
    for bom, encoding, name in BOMS:
        if data.startswith(bom):
            try:
                text = data[len(bom):].decode(encoding)
            except UnicodeDecodeError:
                break
            return Conversion("complete", lf(text),
                              [f"Decoded as {name}, named by the byte-order mark the file starts with; "
                               "the mark itself is left out."])
    if b"\x00" in data:
        return Conversion("failed", "", [
            "The file holds NUL bytes, so it is binary or UTF-16 without a byte-order mark; no text was "
            "extracted. Review it and run a specialised converter."])
    try:
        return Conversion("complete", lf(data.decode("utf-8")),
                          ["Direct text extraction completed."])
    except UnicodeDecodeError:
        return Conversion("partial", lf(data.decode("utf-8", errors="replace")),
                          ["The file is not UTF-8: characters that could not be decoded are shown as "
                           "\N{REPLACEMENT CHARACTER}. Review against the raw file."])


def convert(path: Path) -> Conversion:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return Conversion("pending_conversion", "",
                          ["This format requires a specialised converter. The raw file has been preserved."])
    try:
        data = path.read_bytes()
    except OSError as err:
        return Conversion("failed", "", [f"The raw file could not be read: {err.strerror}."])
    return decode(data)
