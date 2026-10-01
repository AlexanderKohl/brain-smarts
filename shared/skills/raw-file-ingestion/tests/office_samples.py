"""Fictional Word and Excel files for the tests (SMART-RULE-0008), written as the XML parts Office saves.

Only the parts the converter reads are written, in the form Word and Excel write them.
"""
from __future__ import annotations

import io
import zipfile

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
R_NS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
S_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL_NS = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
DRAWING_NS = ('xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
              'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
              'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"')
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def package(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", XML + '<Types xmlns="http://schemas.openxmlformats.org/'
                                                      'package/2006/content-types"/>')
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def para(content: str, style: str = "", numbering: tuple[int, int] | None = None) -> str:
    props = f'<w:pStyle w:val="{style}"/>' if style else ""
    if numbering:
        props += f'<w:numPr><w:ilvl w:val="{numbering[1]}"/><w:numId w:val="{numbering[0]}"/></w:numPr>'
    return f"<w:p>{'<w:pPr>' + props + '</w:pPr>' if props else ''}{content}</w:p>"


def docx(body: str, *, footnotes: str = "", links: dict[str, str] | None = None, extra: dict[str, str] | None = None) -> bytes:
    styles = (XML + f'<w:styles {W_NS}>'
              '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="MyHeading"><w:name w:val="My Heading"/>'
              '<w:basedOn w:val="Heading2"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/>'
              '<w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>'
              '</w:styles>')
    numbering = (XML + f'<w:numbering {W_NS}>'
                 '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>'
                 '<w:lvl w:ilvl="1"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
                 '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
                 '</w:abstractNum>'
                 '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                 '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
                 '</w:numbering>')
    rels = "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   f'relationships/hyperlink" Target="{url}" TargetMode="External"/>'
                   for rid, url in (links or {}).items())
    parts = {
        "word/document.xml": XML + f'<w:document {W_NS} {R_NS} {DRAWING_NS}><w:body>{body}'
                                   '<w:sectPr/></w:body></w:document>',
        "word/styles.xml": styles,
        "word/numbering.xml": numbering,
        "word/_rels/document.xml.rels": XML + f"<Relationships {REL_NS}>{rels}</Relationships>",
    }
    if footnotes:
        parts["word/footnotes.xml"] = (XML + f'<w:footnotes {W_NS}>'
                                       '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r>'
                                       f'</w:p></w:footnote>{footnotes}</w:footnotes>')
    parts.update(extra or {})
    return package(parts)


def cell(ref: str, value: str = "", kind: str = "", style: str = "", formula: str | None = None,
         stored: bool = True) -> str:
    """One worksheet cell; `stored=False` writes a formula with the empty <v/> some programs leave."""
    attrs = f' r="{ref}"' + (f' t="{kind}"' if kind else "") + (f' s="{style}"' if style else "")
    inner = f"<f>{formula}</f>" if formula is not None else ""
    if kind == "inlineStr":
        inner += f"<is><t>{value}</t></is>"
    else:
        inner += f"<v>{value}</v>" if stored else "<v></v>"
    return f"<c{attrs}>{inner}</c>"


def sheet(rows: dict[int, list[str]], merged: list[str] | None = None) -> str:
    data = "".join(f'<row r="{r}">{"".join(cells)}</row>' for r, cells in sorted(rows.items()))
    merges = ""
    if merged:
        merges = f'<mergeCells count="{len(merged)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merged) + "</mergeCells>"
    return XML + f"<worksheet {S_NS}><sheetData>{data}</sheetData>{merges}</worksheet>"


def xlsx(sheets: list[tuple[str, str, str]], strings: list[str], *, date1904: bool = False,
         extra: dict[str, str] | None = None) -> bytes:
    """`sheets`: (name, state, worksheet XML); strings: the shared strings, referred to by index."""
    states = ["" if state == "visible" else f' state="{state}"' for _, state, _ in sheets]
    book = "".join(f'<sheet name="{name}" sheetId="{n}"{states[n - 1]} r:id="rId{n}"/>'
                   for n, (name, _, _) in enumerate(sheets, start=1))
    rels = "".join(f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   f'relationships/worksheet" Target="worksheets/sheet{n}.xml"/>' for n in range(1, len(sheets) + 1))
    shared = "".join(f"<si><t>{text}</t></si>" for text in strings)
    epoch = ' date1904="1"' if date1904 else ""
    parts = {
        "xl/workbook.xml": XML + f'<workbook {S_NS} {R_NS}>'
                                 f'<workbookPr{epoch}/><sheets>{book}</sheets></workbook>',
        "xl/_rels/workbook.xml.rels": XML + f"<Relationships {REL_NS}>{rels}</Relationships>",
        "xl/sharedStrings.xml": XML + f'<sst {S_NS} count="{len(strings)}">{shared}</sst>',
        # Style 0 General; 1 the built-in date format 14; 2 a custom date-time format; 3 a custom
        # number format with a quoted unit, which must not read as a date.
        "xl/styles.xml": XML + f'<styleSheet {S_NS}><numFmts count="2">'
                               '<numFmt numFmtId="164" formatCode="yyyy-mm-dd hh:mm"/>'
                               '<numFmt numFmtId="165" formatCode="0.00 &quot;m&quot;"/></numFmts>'
                               '<cellXfs count="4"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/>'
                               '<xf numFmtId="165"/></cellXfs></styleSheet>',
    }
    for n, (_, _, xml) in enumerate(sheets, start=1):
        parts[f"xl/worksheets/sheet{n}.xml"] = xml
    parts.update(extra or {})
    return package(parts)
