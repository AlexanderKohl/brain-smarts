"""Word (.docx) and Excel (.xlsx) files as Markdown, read with the standard library alone.

Both are Office Open XML packages: ZIP files of XML parts. Each converter returns
(status, markdown, notes) for convert.py, and names in its notes everything it leaves out.
"""
from __future__ import annotations

import datetime as dt
import posixpath
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET
from typing import Optional

from markdown_blocks import table

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
V = "{urn:schemas-microsoft-com:vml}"
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"   # a compound file: encrypted Office or .doc/.xls

MAX_PART = 200 * 1024 * 1024        # uncompressed bytes of one XML part; more is refused, not read
Result = tuple[str, str, list[str]]


class PackageError(Exception):
    """The file is not an Office package this converter can read."""


def read_xml(package: zipfile.ZipFile, name: str) -> Optional[ET.Element]:
    """One XML part, or None when the package has no such part."""
    try:
        info = package.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART:
        raise PackageError(f"{name} is over {MAX_PART // 2 ** 20} MB uncompressed")
    data = package.read(info)
    if b"<!DOCTYPE" in data:          # Office parts never declare one; entity tricks need one
        raise PackageError(f"{name} declares a DOCTYPE")
    return ET.fromstring(data)


def relationships(package: zipfile.ZipFile, part: str) -> dict[str, str]:
    """A part's relationship ids and their targets: a path inside the package, or an external URL."""
    folder, name = posixpath.split(part)
    rels = read_xml(package, posixpath.join(folder, "_rels", name + ".rels"))
    found: dict[str, str] = {}
    for rel in [] if rels is None else rels.iter(REL + "Relationship"):
        target = rel.get("Target", "")
        if rel.get("TargetMode") != "External":
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        found[rel.get("Id", "")] = target
    return found


def open_package(path, convert) -> Result:
    with open(path, "rb") as handle:
        if handle.read(8) == OLE_SIGNATURE:
            return "pending_conversion", "", [
                "The file is a compound file, not an Office Open XML package: it is protected with a password, "
                "or saved in the older binary format. Remove the password or save it as .docx/.xlsx, then "
                "convert that copy. The raw file is preserved."]
    try:
        with zipfile.ZipFile(path) as package:
            return convert(package)
    except (zipfile.BadZipFile, PackageError, ET.ParseError, zlib.error, EOFError, RuntimeError,
            ValueError, IndexError, KeyError) as err:
        return "failed", "", [f"Not read as an Office file: {err}. The raw file is preserved."]


def plain(text: str) -> str:
    """Paragraph text that cannot turn into Markdown structure: line-leading markers are escaped.

    Only punctuation takes a backslash escape, so a numbered line escapes its dot, not its digits.
    """
    text = re.sub(r"(?m)^(\s*)([#>+*=-])", r"\1\\\2", text)
    return re.sub(r"(?m)^(\s*\d+)([.)])", r"\1\\\2", text)


# Word ---------------------------------------------------------------------------------------

LIST_ITEM = re.compile(r"\s*(-|1\.) ")
MARKER = re.compile(r"_\[(image(: [^\]]*)?|Page break)\]_")     # what the converter adds, not text


class WordDocument:
    def __init__(self, package: zipfile.ZipFile):
        self.package = package
        self.body = read_xml(package, "word/document.xml")
        if self.body is None or self.body.find(W + "body") is None:
            raise PackageError("it has no word/document.xml body")
        self.links = relationships(package, "word/document.xml")
        self.styles = self.read_styles()
        self.ordered = self.read_numbering()
        self.cited: list[tuple[str, str]] = []
        self.counts = {"page breaks": 0, "images": 0, "tracked changes": 0}
        # Read after the counters exist: a note's own text passes through inline() too.
        self.notes_text: dict[str, dict[str, str]] = {"footnote": {}, "endnote": {}}
        for kind in self.notes_text:
            self.notes_text[kind] = self.read_notes(kind)

    def read_styles(self) -> dict[str, dict]:
        """Paragraph styles: heading level and list flag, following each style's basedOn chain."""
        root = read_xml(self.package, "word/styles.xml")
        raw: dict[str, dict] = {}
        for style in [] if root is None else root.iter(W + "style"):
            name = style.find(W + "name")
            name = (name.get(W + "val") if name is not None else "") or ""
            outline = style.find(f"{W}pPr/{W}outlineLvl")
            level = None
            if re.fullmatch(r"(?i)heading ([1-9])", name):
                level = int(name[-1])
            elif name.lower() == "title":
                level = 1
            elif outline is not None and outline.get(W + "val", "9").isdigit() and int(outline.get(W + "val")) < 9:
                level = int(outline.get(W + "val")) + 1
            based = style.find(W + "basedOn")
            raw[style.get(W + "styleId", "")] = {
                "level": level, "list": style.find(f"{W}pPr/{W}numPr") is not None,
                "based": based.get(W + "val") if based is not None else None}
        resolved: dict[str, dict] = {}
        for style_id, style in raw.items():
            level, is_list, seen, based = style["level"], style["list"], {style_id}, style["based"]
            while based in raw and based not in seen:
                seen.add(based)
                level = level if level is not None else raw[based]["level"]
                is_list = is_list or raw[based]["list"]
                based = raw[based]["based"]
            resolved[style_id] = {"level": level, "list": is_list}
        return resolved

    def read_numbering(self) -> set[tuple[str, str]]:
        """(numId, level) pairs numbered in order rather than bulleted."""
        root = read_xml(self.package, "word/numbering.xml")
        if root is None:
            return set()
        abstract: dict[str, dict[str, str]] = {}
        for item in root.findall(W + "abstractNum"):
            formats = {}
            for level in item.findall(W + "lvl"):
                fmt = level.find(W + "numFmt")
                formats[level.get(W + "ilvl", "0")] = fmt.get(W + "val", "") if fmt is not None else ""
            abstract[item.get(W + "abstractNumId", "")] = formats
        ordered = set()
        for num in root.findall(W + "num"):
            ref = num.find(W + "abstractNumId")
            formats = abstract.get(ref.get(W + "val", "") if ref is not None else "", {})
            for level, fmt in formats.items():
                if fmt not in ("bullet", "none", ""):
                    ordered.add((num.get(W + "numId", ""), level))
        return ordered

    def read_notes(self, kind: str) -> dict[str, str]:
        root = read_xml(self.package, f"word/{kind}s.xml")
        found = {}
        for note in [] if root is None else root.findall(W + kind):
            if note.get(W + "type") in (None, "normal"):
                found[note.get(W + "id", "")] = " ".join(
                    self.inline(p).strip() for p in note.findall(W + "p")).strip()
        return found

    def inline(self, element: ET.Element) -> str:
        """The text of runs inside `element`, with links, note markers and image markers."""
        out: list[str] = []
        for child in element:
            tag = child.tag
            if tag == W + "t":
                out.append(child.text or "")
            elif tag == W + "tab":
                out.append("\t")
            elif tag in (W + "br", W + "cr"):
                if child.get(W + "type") == "page":
                    self.counts["page breaks"] += 1
                    out.append("\x0c")
                else:
                    out.append("\n")
            elif tag == W + "noBreakHyphen":
                out.append("-")
            elif tag in (W + "del", W + "moveFrom"):
                self.counts["tracked changes"] += 1          # deleted text: shown as if accepted
            elif tag in (W + "ins", W + "moveTo"):
                self.counts["tracked changes"] += 1
                out.append(self.inline(child))
            elif tag == MC + "AlternateContent":             # Choice and Fallback hold the same content
                choice = child.find(MC + "Choice")
                out.append(self.inline(choice) if choice is not None else "")
            elif tag == W + "hyperlink":
                text, target = self.inline(child), self.links.get(child.get(R + "id", ""), "")
                out.append(f"[{text}]({target})" if text and target.startswith(("http:", "https:", "mailto:"))
                           else text)
            elif tag in (W + "footnoteReference", W + "endnoteReference"):
                kind = "footnote" if tag == W + "footnoteReference" else "endnote"
                label = ("" if kind == "footnote" else "e") + child.get(W + "id", "")
                self.cited.append((label, self.notes_text[kind].get(child.get(W + "id", ""), "")))
                out.append(f"[^{label}]")
            elif tag in (W + "drawing", W + "pict"):
                if any(True for _ in child.iter(A + "blip")) or any(True for _ in child.iter(V + "imagedata")):
                    self.counts["images"] += 1
                    described = next((d.get("descr") for d in child.iter(WP + "docPr") if d.get("descr")), "")
                    out.append(f"_[image: {described}]_" if described else "_[image]_")
                out.append(self.inline(child))                 # text boxes inside the drawing
            elif tag == W + "p":                                # a paragraph inside a text box
                out.append(self.inline(child) + "\n")
            elif tag not in (W + "instrText", W + "delText", W + "rPr", W + "pPr"):
                out.append(self.inline(child))
        return "".join(out)

    def paragraph(self, p: ET.Element) -> list[str]:
        """Markdown blocks for one paragraph: a heading, a list item or text, and page-break markers."""
        props = p.find(W + "pPr")
        style_id = ""
        if props is not None and props.find(W + "pStyle") is not None:
            style_id = props.find(W + "pStyle").get(W + "val", "")
        style = self.styles.get(style_id, {"level": None, "list": False})
        blocks: list[str] = []
        if props is not None and props.find(W + "pageBreakBefore") is not None:
            self.counts["page breaks"] += 1
            blocks.append("_[Page break]_")
        text = self.inline(p)
        pieces = text.split("\x0c")
        for number, piece in enumerate(pieces):
            if number:
                blocks.append("_[Page break]_")
            piece = piece.strip()
            if not piece:
                continue
            numbering = props.find(W + "numPr") if props is not None else None
            if style["level"]:
                blocks.append("#" * min(style["level"], 6) + " " + " ".join(piece.split()))
            elif numbering is not None or style["list"]:
                level = numbering.find(W + "ilvl") if numbering is not None else None
                num = numbering.find(W + "numId") if numbering is not None else None
                ilvl = level.get(W + "val", "0") if level is not None else "0"
                num_id = num.get(W + "val", "") if num is not None else ""
                marker = "1." if (num_id, ilvl) in self.ordered else "-"
                blocks.append("  " * int(ilvl if ilvl.isdigit() else 0) + f"{marker} " + plain(piece))
            else:
                blocks.append(plain(piece))
        return blocks

    def cell_text(self, cell: ET.Element) -> str:
        parts = []
        for child in cell:
            if child.tag == W + "p":
                parts.append(self.inline(child).replace("\x0c", " ").strip())
            elif child.tag == W + "tbl":
                for row in child.iter(W + "tr"):
                    parts.append(" / ".join(self.cell_text(c) for c in row.findall(W + "tc")))
            elif child.tag == W + "sdt":
                content = child.find(W + "sdtContent")
                parts.append(self.cell_text(content) if content is not None else "")
        return "\n".join(part for part in parts if part)

    def table_block(self, tbl: ET.Element) -> Optional[str]:
        rows = []
        for tr in tbl.findall(W + "tr"):
            cells: list[str] = []
            for tc in tr.findall(W + "tc"):
                cells.append(self.cell_text(tc))
                span = tc.find(f"{W}tcPr/{W}gridSpan")
                if span is not None and span.get(W + "val", "1").isdigit():
                    cells += [""] * (int(span.get(W + "val")) - 1)
            rows.append(cells)
        return table(rows[0], rows[1:]) if rows else None

    def blocks(self, container: ET.Element) -> list[str]:
        out: list[str] = []
        for child in container:
            if child.tag == W + "p":
                out += self.paragraph(child)
            elif child.tag == W + "tbl":
                block = self.table_block(child)
                if block:
                    out.append(block)
            elif child.tag == W + "sdt":
                content = child.find(W + "sdtContent")
                if content is not None:
                    out += self.blocks(content)
        return out

    def convert(self) -> Result:
        blocks = self.blocks(self.body.find(W + "body"))
        blocks = [b for n, b in enumerate(blocks) if not (b == "_[Page break]_" and (n == 0 or n == len(blocks) - 1))]
        if self.cited:
            blocks.append("\n".join(f"[^{label}]: {text}" for label, text in self.cited))
        notes = ["Read from the document's XML: headings, paragraphs, lists, tables, links and footnotes in "
                 "document order. Bold, italic, fonts and colours are not kept."]
        if self.counts["page breaks"]:
            notes.append("A Word file has no fixed pages; its explicit page breaks are marked _[Page break]_.")
        if self.counts["images"]:
            notes.append(f"{self.counts['images']} image(s) are marked _[image]_, with their alt text where it "
                         "is set; the images themselves are not extracted.")
        if self.counts["tracked changes"]:
            notes.append("The document has tracked changes; the text is shown as if they were accepted.")
        names = self.package.namelist()
        if any(re.fullmatch(r"word/(header|footer)\d*\.xml", n) for n in names):
            notes.append("Headers and footers are not extracted.")
        if "word/comments.xml" in names:
            notes.append("Comments are not extracted.")
        markdown = ""
        for number, block in enumerate(blocks):
            # Items of one list stay together; every other block is its own paragraph.
            together = number and LIST_ITEM.match(block) and LIST_ITEM.match(blocks[number - 1])
            markdown += ("\n" if together else "\n\n" if number else "") + block
        if not MARKER.sub("", markdown).strip():
            return "pending_conversion", markdown, notes + [
                "No text found. If the document is scanned pages, it needs OCR."]
        return "complete", markdown, notes


def docx_to_markdown(path) -> Result:
    return open_package(path, lambda package: WordDocument(package).convert())


# Excel --------------------------------------------------------------------------------------

BUILTIN_DATE_FORMATS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))


def column_number(letters: str) -> int:
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number


def column_letters(number: int) -> str:
    letters = ""
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def rich_text(element: Optional[ET.Element]) -> str:
    """A string item's text: its runs, not the phonetic guide some Asian-language files carry."""
    if element is None:
        return ""
    parts = [element.findtext(S + "t") or ""] + [run.findtext(S + "t") or "" for run in element.findall(S + "r")]
    text = "".join(parts)
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), text).replace("\r\n", "\n")


def is_date_format(code: str) -> bool:
    bare = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", code)
    return bool(re.search(r"[dmyhs]", bare, re.I)) and "general" not in bare.lower()


class Workbook:
    def __init__(self, package: zipfile.ZipFile):
        self.package = package
        book = read_xml(package, "xl/workbook.xml")
        if book is None:
            raise PackageError("it has no xl/workbook.xml")
        props = book.find(S + "workbookPr")
        epoch = "1904" if props is not None and props.get("date1904") in ("1", "true") else "1900"
        self.epoch = dt.datetime(1904, 1, 1) if epoch == "1904" else dt.datetime(1899, 12, 30)
        targets = relationships(package, "xl/workbook.xml")
        self.sheets = [(sheet.get("name", ""), targets.get(sheet.get(R + "id", ""), ""), sheet.get("state", "visible"))
                       for sheet in book.iter(S + "sheet")]
        strings = read_xml(package, "xl/sharedStrings.xml")
        self.strings = [] if strings is None else [rich_text(item) for item in strings.findall(S + "si")]
        self.date_styles = self.read_date_styles()
        self.counts = {"cached formulas": 0, "uncached formulas": 0, "merged ranges": 0}

    def read_date_styles(self) -> set[int]:
        """Indexes of the cell styles whose number format shows a date or time."""
        styles = read_xml(self.package, "xl/styles.xml")
        if styles is None:
            return set()
        custom = {int(f.get("numFmtId", "0")): f.get("formatCode", "") for f in styles.iter(S + "numFmt")}
        xfs = styles.find(S + "cellXfs")
        found = set()
        for index, xf in enumerate([] if xfs is None else xfs.findall(S + "xf")):
            fmt = int(xf.get("numFmtId", "0"))
            if fmt in BUILTIN_DATE_FORMATS or (fmt in custom and is_date_format(custom[fmt])):
                found.add(index)
        return found

    def as_date(self, value: str) -> str:
        serial = float(value)
        moment = self.epoch + dt.timedelta(days=serial)
        if serial < 1:
            return moment.time().isoformat(timespec="seconds")
        if moment.time() == dt.time(0):
            return moment.date().isoformat()
        return moment.isoformat(timespec="seconds")

    def value(self, c: ET.Element) -> str:
        kind = c.get("t", "n")
        stored = c.find(S + "v")
        raw = stored.text if stored is not None else None
        formula = c.find(S + "f")
        if formula is not None:
            # No calculated value: no <v>, or an empty one (as some writers leave) on a cell that is not
            # a string result; an empty <v> on a string result is a calculated empty string.
            if kind != "inlineStr" and (stored is None or (not raw and kind != "str")):
                self.counts["uncached formulas"] += 1
                return "=" + (formula.text or "") if formula.text else "="
            self.counts["cached formulas"] += 1
        if kind == "inlineStr":
            return rich_text(c.find(S + "is"))
        if raw is None:
            return ""
        if kind == "s":
            return self.strings[int(raw)] if raw.isdigit() and int(raw) < len(self.strings) else ""
        if kind == "b":
            return "TRUE" if raw == "1" else "FALSE"
        if kind == "n" and c.get("s", "").isdigit() and int(c.get("s")) in self.date_styles:
            try:
                return self.as_date(raw)
            except (ValueError, OverflowError):
                return raw
        return raw                                          # numbers as stored; errors and strings as they are

    def sheet_block(self, name: str, target: str, state: str, number: int) -> str:
        heading = f"### Sheet {number}: {name}" + ("" if state == "visible" else f" ({state})")
        root = read_xml(self.package, target) if target else None
        if root is None or root.tag != S + "worksheet":
            return heading + "\n\n_Not a worksheet (a chart sheet or a missing part); not extracted._"
        cells: dict[int, dict[int, str]] = {}
        last_row = 0
        for row in root.iter(S + "row"):
            last_row = int(row.get("r")) if (row.get("r") or "").isdigit() else last_row + 1
            last_col = 0
            for c in row.findall(S + "c"):
                ref = re.match(r"([A-Z]+)", c.get("r", ""))
                last_col = column_number(ref.group(1)) if ref else last_col + 1
                text = self.value(c)
                if text != "":
                    cells.setdefault(last_row, {})[last_col] = text
        merged = root.find(S + "mergeCells")
        self.counts["merged ranges"] += 0 if merged is None else len(merged.findall(S + "mergeCell"))
        if not cells:
            return heading + "\n\n_Empty sheet._"
        first = min(min(row) for row in cells.values())
        last = max(max(row) for row in cells.values())
        header = ["Row"] + [column_letters(n) for n in range(first, last + 1)]
        rows = [[str(r)] + [cells[r].get(n, "") for n in range(first, last + 1)] for r in sorted(cells)]
        return heading + "\n\n" + table(header, rows)

    def convert(self) -> Result:
        blocks = [self.sheet_block(name, target, state, number)
                  for number, (name, target, state) in enumerate(self.sheets, start=1)]
        notes = ["Read from the workbook's XML: each sheet is a table headed by its column letters, each row by "
                 "its row number, so every value keeps its cell reference. Empty rows and columns are left out.",
                 "Numbers are shown as stored, without their display format (currency, percentage, decimal "
                 "places); dates and times are shown in ISO form."]
        status = "complete"
        if self.counts["cached formulas"]:
            notes.append(f"{self.counts['cached formulas']} formula cell(s) show the value last calculated and "
                         "saved with the file.")
        if self.counts["uncached formulas"]:
            status = "partial"
            notes.append(f"{self.counts['uncached formulas']} formula cell(s) have no calculated value saved "
                         "(a program, not a spreadsheet application, wrote the file) and show their formula "
                         "instead. Opening and saving a copy in a spreadsheet application would store the values.")
        if self.counts["merged ranges"]:
            notes.append(f"{self.counts['merged ranges']} merged range(s): the value is shown in the first cell only.")
        names = self.package.namelist()
        if any(n.startswith(("xl/drawings/", "xl/charts/", "xl/media/")) for n in names):
            notes.append("Charts and images are not extracted.")
        if any(n.startswith(("xl/comments", "xl/threadedComments/")) for n in names):
            notes.append("Cell comments are not extracted.")
        return status, "\n\n".join(blocks) or "_The workbook has no sheets._", notes


def xlsx_to_markdown(path) -> Result:
    return open_package(path, lambda package: Workbook(package).convert())
