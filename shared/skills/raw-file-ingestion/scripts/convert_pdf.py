"""PDF files as Markdown, page by page, through a text extractor this computer has.

The standard library cannot read PDF text, so the first of these that is available is used:
poppler's `pdftotext` on PATH, then the `pypdf` package. With neither, the record waits as
`pending_conversion` with a note saying what to install. Returns (status, markdown, notes).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from markdown_blocks import fence

TIMEOUT = 300                          # seconds for one extraction; a PDF that takes longer is `failed`
Result = tuple[str, str, list[str]]
Pages = tuple[list[str], str]          # the text of each page, and the extractor that read it


class ExtractionError(Exception):
    def __init__(self, message: str, password: bool = False):
        super().__init__(message)
        self.password = password


def with_pdftotext(path: Path) -> Optional[Pages]:
    """Pages from poppler's pdftotext, keeping the layout's spacing; None when it is not installed."""
    program = shutil.which("pdftotext")
    if not program:
        return None
    try:
        done = subprocess.run([program, "-layout", "-enc", "UTF-8", str(path), "-"],
                              capture_output=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ExtractionError(f"pdftotext took longer than {TIMEOUT} seconds") from None
    if done.returncode:
        message = (done.stderr.decode("utf-8", errors="replace").strip().splitlines() or ["no message"])[-1]
        raise ExtractionError(f"pdftotext: {message}", password="password" in message.lower())
    version = subprocess.run([program, "-v"], capture_output=True, timeout=30)
    found = re.search(rb"version ([\d.]+)", version.stderr + version.stdout)
    text = done.stdout.decode("utf-8", errors="replace")
    if text.endswith("\f"):                                   # pdftotext ends every page with a form feed
        text = text[:-1]
    return text.split("\f"), "pdftotext" + (f" {found.group(1).decode()}" if found else "") + " (-layout)"


def with_pypdf(path: Path) -> Optional[Pages]:
    """Pages from the pypdf package; None when it is not installed."""
    try:
        import pypdf
    except ImportError:
        return None
    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("pypdf: the file needs a password", password=True)
        return [page.extract_text() or "" for page in reader.pages], f"pypdf {pypdf.__version__}"
    except ExtractionError:
        raise
    except Exception as err:                                  # pypdf raises many kinds for damaged files
        raise ExtractionError(f"pypdf: {err}") from None


EXTRACTORS: list[Callable[[Path], Optional[Pages]]] = [with_pdftotext, with_pypdf]


def page_list(numbers: list[int]) -> str:
    return ", ".join(str(n) for n in numbers)


def pdf_to_markdown(path: Path, extractors: list[Callable[[Path], Optional[Pages]]] = EXTRACTORS) -> Result:
    try:
        found = next((pages for pages in (extract(path) for extract in extractors) if pages is not None), None)
    except ExtractionError as err:
        if err.password:
            return "pending_conversion", "", [
                f"The PDF is protected with a password ({err}). An unprotected copy can be converted. "
                "The raw file is preserved."]
        return "failed", "", [f"Text extraction failed ({err}). The raw file is preserved."]
    if found is None:
        return "pending_conversion", "", [
            "No PDF text extractor is installed on this computer. Install poppler (for `pdftotext`) or the "
            "`pypdf` package (`pip install pypdf`), then convert again. The raw file is preserved."]
    pages, extractor = found
    blank = [n for n, text in enumerate(pages, start=1) if not text.strip()]
    blocks = []
    for number, text in enumerate(pages, start=1):
        body = fence(text.strip("\n"), "text") if text.strip() else "_No text on this page._"
        blocks.append(f"### Page {number}\n\n{body}")
    notes = [f"Text extracted with {extractor}, page by page: {len(pages)} page(s), each in a fenced block "
             "that keeps its line breaks and spacing. Images, and text drawn as images, are not extracted."]
    if extractor.startswith("pypdf"):
        notes.append("pypdf reads text in the order the file stores it, which can differ from the visual "
                     "order of columns and tables.")
    status = "complete"
    if pages and len(blank) == len(pages):
        status = "pending_conversion"
        notes.append("No page has a text layer: the pages are images, as a scan is. They need OCR.")
    elif blank:
        status = "partial"
        notes.append(f"Page(s) {page_list(blank)} have no text layer (scanned or image-only); they need OCR.")
    return status, "\n\n".join(blocks) or "_The PDF has no pages._", notes
