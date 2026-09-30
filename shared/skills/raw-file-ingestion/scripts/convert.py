"""Conversion of a raw file into the Markdown of its source record (CONTRACT §11.2, §11.4).

`convert(path)` reads the raw file, never changes it, and returns a `Conversion`: the status the
record carries in `conversion_status`, the extracted Markdown, and one note per limitation.
"""
from __future__ import annotations

import codecs
import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from convert_office import docx_to_markdown, xlsx_to_markdown
from markdown_blocks import fence, table

# Text shown verbatim in a fenced block, with the block's language: the text can then add no
# heading, list or HTML of its own to the record, and keeps its line breaks and spacing.
FENCED = {
    ".css": "css", ".htm": "html", ".html": "html", ".js": "javascript", ".json": "json",
    ".log": "text", ".py": "python", ".sql": "sql", ".ts": "typescript", ".txt": "text",
    ".xml": "xml", ".yaml": "yaml", ".yml": "yaml",
}
MARKDOWN = {".markdown", ".md"}
DELIMITED = {".csv", ".tsv"}
TEXT_EXTENSIONS = set(FENCED) | MARKDOWN | DELIMITED
# Formats read by a converter of their own, which returns (status, markdown, notes).
CONVERTERS = {
    ".docm": docx_to_markdown, ".docx": docx_to_markdown,
    ".xlsm": xlsx_to_markdown, ".xlsx": xlsx_to_markdown,
}
FRONT_MATTER = re.compile(r"\A---\n(.*?\n)(?:---|\.\.\.)(?:\n|\Z)", re.S)

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
                          ["Read as UTF-8 text."])
    except UnicodeDecodeError:
        return Conversion("partial", lf(data.decode("utf-8", errors="replace")),
                          ["The file is not UTF-8: characters that could not be decoded are shown as "
                           "\N{REPLACEMENT CHARACTER}. Review against the raw file."])


def markdown_document(text: str) -> tuple[str, str]:
    """A Markdown file as written; front matter moves into a YAML block so it stays apart from the record's."""
    found = FRONT_MATTER.match(text)
    if not found:
        return text, "Markdown kept as written."
    body = text[found.end():].lstrip("\n")
    return ("Front matter of the raw file:\n\n" + fence(found.group(1), "yaml") + "\n\n" + body,
            "Markdown kept as written; its front matter is shown as a YAML block.")


def delimited_table(text: str, suffix: str) -> tuple[str, str]:
    """A CSV or TSV file as a Markdown table, its first row the header; as text when it will not parse."""
    delimiter = "\t"
    if suffix == ".csv":
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    try:
        rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter, strict=True) if row]
    except csv.Error as err:
        return fence(text, "text"), f"Not read as a table ({err}); shown as text."
    if not rows:
        return fence(text, "text"), "No rows found; shown as text."
    shown = {"\t": "tab"}.get(delimiter, f"`{delimiter}`")
    return (table(rows[0], rows[1:]),
            f"Shown as a table: the first row is the header, then {len(rows) - 1} data rows; "
            f"delimiter {shown}; blank lines left out.")


def json_block(text: str) -> tuple[str, str]:
    """JSON verbatim: reformatting could change how numbers are written, so it is only checked."""
    try:
        json.loads(text)
    except json.JSONDecodeError as err:
        return fence(text, "json"), f"Not valid JSON ({err.msg} at line {err.lineno}); shown verbatim."
    return fence(text, "json"), "Valid JSON, shown verbatim."


def render(suffix: str, text: str) -> tuple[str, str]:
    """The record's Markdown for decoded text, and a note on how it is shown."""
    if suffix in MARKDOWN:
        return markdown_document(text)
    if suffix in DELIMITED:
        return delimited_table(text, suffix)
    if suffix == ".json":
        return json_block(text)
    return fence(text, FENCED[suffix]), "Shown verbatim in a fenced block."


def convert(path: Path) -> Conversion:
    suffix = path.suffix.lower()
    if suffix in CONVERTERS:
        return Conversion(*CONVERTERS[suffix](path))
    if suffix not in TEXT_EXTENSIONS:
        return Conversion("pending_conversion", "",
                          ["This format requires a specialised converter. The raw file has been preserved."])
    try:
        data = path.read_bytes()
    except OSError as err:
        return Conversion("failed", "", [f"The raw file could not be read: {err.strerror}."])
    conversion = decode(data)
    if conversion.status == "failed":
        return conversion
    if not conversion.markdown.strip():
        conversion.markdown = "_The file is empty._"
        return conversion
    conversion.markdown, note = render(suffix, conversion.markdown)
    conversion.notes.append(note)
    return conversion
