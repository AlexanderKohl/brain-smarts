"""Assemble a UI mockup harness from a product's own stylesheets.

Inlines the real CSS files the screen loads, plus the custom properties the app defines
elsewhere, around a markup fragment — so what renders is styled by the same rules as the running
app, specificity collisions and all. See ../SKILL.md; in particular, the harness is written
inside the working repository because the Browser pane cannot screenshot a file outside the
project folder.

    python shared/skills/ui-mockup/scripts/build_mockup.py \
      --css path/to/one.css --css path/to/two.css \
      --tokens path/to/globals.css \
      --body temp/ui-mockup/fragment.html \
      --name links-table
"""

from __future__ import annotations

import argparse
import io
import pathlib
import re
import sys

TOKEN_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+);")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{name} — mockup</title>
<style>
:root{{{tokens}}}
body{{margin:0;background:var(--mockup-bg,#f2f4f7);font:14px system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ghl-text,#101828)}}
{css}
</style></head>
<body>
{body}
</body></html>
"""


def read(path: pathlib.Path, label: str) -> str:
    if not path.is_file():
        # Never quietly substitute an approximation: a mockup built from CSS that is not the
        # product's own is a drawing, not a preview, and must not be presented as one.
        sys.exit(f"{label} not found: {path}")
    return io.open(path, encoding="utf-8").read()


def custom_properties(sources: list[pathlib.Path]) -> str:
    """Every `--name: value;` declaration found, in file order; later files win."""
    found: dict[str, str] = {}
    for source in sources:
        for name, value in TOKEN_RE.findall(read(source, "Token source")):
            found[name] = value.strip()
    return "".join(f"{name}:{value};" for name, value in found.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a UI mockup harness from real stylesheets.")
    parser.add_argument("--css", action="append", default=[], required=True,
                        help="Stylesheet to inline, in load order. Repeatable.")
    parser.add_argument("--tokens", action="append", default=[],
                        help="Stylesheet to lift CSS custom properties from (e.g. globals.css). Repeatable.")
    parser.add_argument("--body", required=True,
                        help="HTML fragment matching what the components render, or - for stdin.")
    parser.add_argument("--name", default="mockup", help="Used for the filename and the page title.")
    parser.add_argument("--out-dir", default="temp/ui-mockup",
                        help="Must sit inside the working repository, or the pane cannot screenshot it.")
    args = parser.parse_args()

    body = sys.stdin.read() if args.body == "-" else read(pathlib.Path(args.body), "Body fragment")
    css = "\n".join(read(pathlib.Path(path), "Stylesheet") for path in args.css)
    tokens = custom_properties([pathlib.Path(path) for path in args.tokens])

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.name}.preview.html"
    io.open(out, "w", encoding="utf-8", newline="").write(
        PAGE.format(name=args.name, tokens=tokens, css=css, body=body)
    )

    print(f"wrote {out}")
    print(f"file:///{out.resolve().as_posix()}")
    print(f"stylesheets inlined: {len(args.css)}; custom properties: {tokens.count(':')}")
    print("Resize the pane to the real viewport before screenshotting, and delete this file when done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
