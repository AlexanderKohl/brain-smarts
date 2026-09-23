#!/usr/bin/env python3
"""Local browser UI for /temp/ai-session/ai-call-log.jsonl.

Serves a small HTML timeline and a JSON API. Stdlib only. Bind defaults to
127.0.0.1:8768 so it stays on this machine.

Usage:
  python view_log.py
  python view_log.py --port 8768 --open
  python session_log.py view --open
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from session_log import find_repo_root, log_path, temp_dir

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8768
# Cap payload size so the timeline stays usable on multi-MB logs.
DEFAULT_TEXT_CLIP = 6_000
VIEWER_DIR = Path(__file__).resolve().parent.parent / "viewer"
INDEX_HTML = VIEWER_DIR / "index.html"
VALID_KINDS = frozenset(
    {"model_call", "model_response", "thinking", "tool_result", "python_run"}
)
TEXT_FIELDS = ("call_text", "response_text", "thinking_text", "content", "output", "note")


def clip_record(obj: dict[str, Any], limit: int) -> dict[str, Any]:
    """Return a shallow copy with long text fields clipped for the list UI."""
    out = dict(obj)
    clipped = False
    for key in TEXT_FIELDS:
        val = out.get(key)
        if isinstance(val, str) and len(val) > limit:
            out[key] = val[:limit] + f"\n… [truncated {len(val) - limit} chars]"
            clipped = True
    if clipped:
        out["_clipped"] = True
    return out


def read_jsonl_tail(
    path: Path,
    *,
    limit: int,
    kinds: set[str] | None = None,
    text_clip: int = DEFAULT_TEXT_CLIP,
) -> tuple[list[dict[str, Any]], int]:
    """Parse JSONL and return the last `limit` matching records plus total line count.

    For typical session logs (a few MB) a full read is fine. Incomplete final
    lines are skipped (same spirit as the transcript listener). Long text fields
    are clipped so the browser JSON stays small.
    """
    if not path.is_file():
        return [], 0

    records: list[dict[str, Any]] = []
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            total += 1
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            kind = obj.get("kind")
            if kinds is not None and (kind is None or kind not in kinds):
                continue
            records.append(obj)

    if limit > 0 and len(records) > limit:
        records = records[-limit:]
    if text_clip > 0:
        records = [clip_record(r, text_clip) for r in records]
    return records, total


def file_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "bytes": 0, "mtime": None, "path": str(path)}
    st = path.stat()
    mtime = datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds")
    return {
        "exists": True,
        "bytes": int(st.st_size),
        "mtime": mtime,
        "path": str(path),
    }


def parse_kinds(raw: str | None) -> set[str] | None:
    """Return None (no filter), empty set (match nothing), or a kind set."""
    if raw is None:
        return None
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    if not parts:
        return set()
    return {p for p in parts if p in VALID_KINDS}


def handler_for(repo_root: Path):
    html_bytes = INDEX_HTML.read_bytes() if INDEX_HTML.is_file() else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            # Keep console quiet; owner only needs startup URL.
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)

            if path in {"/", "/index.html"}:
                if html_bytes is None:
                    self._send(
                        500,
                        b"viewer/index.html missing",
                        "text/plain; charset=utf-8",
                    )
                    return
                self._send(200, html_bytes, "text/html; charset=utf-8")
                return

            if path == "/api/log":
                try:
                    limit = int((qs.get("limit") or ["100"])[0])
                except ValueError:
                    limit = 100
                limit = max(1, min(limit, 5000))
                kinds = parse_kinds((qs.get("kinds") or [None])[0])
                try:
                    text_clip = int((qs.get("text_clip") or [str(DEFAULT_TEXT_CLIP)])[0])
                except ValueError:
                    text_clip = DEFAULT_TEXT_CLIP
                text_clip = max(0, min(text_clip, 500_000))
                lp = log_path(repo_root)
                records, total = read_jsonl_tail(
                    lp, limit=limit, kinds=kinds, text_clip=text_clip
                )
                meta = file_meta(lp)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "records": records,
                        "shown": len(records),
                        "total": total,
                        "limit": limit,
                        "text_clip": text_clip,
                        "kinds": sorted(kinds) if kinds is not None else None,
                        **meta,
                    },
                )
                return

            if path == "/api/health":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "log": file_meta(log_path(repo_root)),
                        "temp_dir": str(temp_dir(repo_root)),
                    },
                )
                return

            self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def serve(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = False,
    repo_root: Path | None = None,
) -> int:
    root = repo_root or find_repo_root()
    if not INDEX_HTML.is_file():
        print(
            json.dumps(
                {"ok": False, "error": f"missing viewer HTML: {INDEX_HTML}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    httpd = ThreadingHTTPServer((host, port), handler_for(root))
    url = f"http://{host}:{port}/"
    print(
        json.dumps(
            {
                "ok": True,
                "url": url,
                "log_path": str(log_path(root)),
                "hint": "Open in a browser, or Cursor/VS Code: Simple Browser: Show",
            },
            ensure_ascii=False,
        )
    )
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(json.dumps({"ok": True, "stopped": True}, ensure_ascii=False))
    finally:
        httpd.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Serve a local HTML viewer for /temp/ai-session/ai-call-log.jsonl"
    )
    p.add_argument("--root", help="Repository root (optional; auto-discovered)")
    p.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default {DEFAULT_HOST})")
    p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Bind port (default {DEFAULT_PORT})",
    )
    p.add_argument(
        "--open",
        action="store_true",
        help="Open the default system browser after start",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_repo_root(Path(args.root).resolve() if args.root else None)
    return serve(
        host=args.host,
        port=args.port,
        open_browser=bool(args.open),
        repo_root=root,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
