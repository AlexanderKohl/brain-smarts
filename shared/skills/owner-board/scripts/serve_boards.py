"""Serve the owner's boards over http on this machine, the board pages and the status pages they
link to, and nothing else.

`python -m http.server --directory memory/boards` serves only the directory folder, but the
directory page links to each board's status page with a relative link that leaves that folder
(`../projects/<node>/status/status.html` for a board in memory, `../../../<repository>/brain/status/status.html`
for a board in a project repository). Opened as a file those links work; over http a browser
drops every `..` that would climb above the site's root, so the request arrives as
`/projects/<node>/status/status.html` or `/<repository>/brain/status/status.html`, and the plain
server answers 404.

This server answers those requests. It serves:
- the directory folder at `/`, as before;
- for every registered board, the board's node folder (the folder that holds `status/`, so the
  status page's own links to `../tasks/...` resolve) at the URL prefix the directory page's link
  arrives at.

Nothing outside those folders is served: no other part of memory, and none of a project
repository except its `brain/` node. A path segment that starts with a dot is refused, a
directory is served only through its `index.html` (no listings), a symbolic link or junction
that leads outside its folder is refused, and a request whose Host header is not this machine
(`localhost`, `127.0.0.1` or `[::1]`) is refused, which stops a web page on another site from
reading the boards through DNS rebinding. Bind it to 127.0.0.1 only.

One more answer, under the same Host and path rules: `GET /_boards-status.json` says whether the
memory checkout the boards are drawn from has fallen behind, so a page can warn the owner before
they decide again what was already decided (`page_js.BEHIND_JS`):
`{"behind": N, "changed": [...], "checked": "<iso time>"}`, where N is
`git rev-list --count HEAD..origin/main` in that checkout (a push from a session copy moves
origin/main in the shared .git, so no fetch is needed) and `changed` names at most 20 tracked
files changed or staged there, which block it catching up. It is worked out on each request,
each git call stopped after a few seconds; any failure gives `{"behind": null, "error": "..."}`
with a short reason of this script's own, never git's output.

The pages' saves (personal CRM design 04, increments 1 and 2), under the same Host rule:
`GET /_board-server.json` hands a served page this start's token, `POST /_save/<kind>` files a
page's saved decisions into `/memory/inbox/` and `GET /_saved.json` lists what waits there. The
checks every post passes are in `serve_post.py`, the saving in `board_inbox.py`.

Usage, from the brain root:
    python shared/skills/owner-board/scripts/serve_boards.py --port 8765
"""
from __future__ import annotations

import argparse
import datetime
import http.server
import io
import json
import os
import posixpath
import subprocess
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import board_config  # noqa: E402
import board_inbox  # noqa: E402
import build_boards  # noqa: E402
import serve_post  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}
STATUS_PATH = "/_boards-status.json"
UPSTREAM = "origin/main"
MAX_CHANGED = 20
GIT_TIMEOUT = 5


class GitFailed(Exception):
    """A git call in the memory checkout failed; the message is safe to send to the page."""


def _git(folder: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise GitFailed("git " + args[0] + " took longer than " + str(GIT_TIMEOUT) + " seconds")
    except OSError:
        raise GitFailed("git could not be run")
    if out.returncode:
        raise GitFailed("git " + args[0] + " failed (exit " + str(out.returncode) + ")")
    return out.stdout


def changed_paths(porcelain: str) -> list[str]:
    """The paths of `git status --porcelain=v1 -z --untracked-files=no`; a rename's source,
    which follows its entry as a field of its own, is skipped."""
    fields = porcelain.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            i += 1
    return paths


def memory_status(folder: Path | None) -> dict:
    """How far the memory checkout lags origin/main, and the tracked files changed or staged in it."""
    try:
        if folder is None:
            raise GitFailed("no memory checkout")
        behind = int(_git(folder, "rev-list", "--count", "HEAD.." + UPSTREAM).strip())
        changed = changed_paths(_git(folder, "status", "--porcelain=v1", "-z", "--untracked-files=no"))
    except (GitFailed, ValueError) as err:
        reason = str(err) if isinstance(err, GitFailed) else "git gave no count"
        return {"behind": None, "error": reason}
    return {"behind": behind, "changed": changed[:MAX_CHANGED],
            "checked": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}


def arrival(href: str) -> str:
    """The URL path a relative link from the site's root page arrives at: every `..` that would
    climb above the root is dropped, as a browser does. Always starts with `/`, never ends with one."""
    parts: list[str] = []
    for seg in href.replace("\\", "/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts)


def mounts(config: board_config.Config) -> list[tuple[str, Path]]:
    """(URL prefix, folder) for every board's node folder, longest prefix first, then the
    directory folder at `/`. A board's node folder is the parent of its status folder."""
    out: list[tuple[str, Path]] = []
    for board in config.boards:
        node = Path(board["folder"]).parent
        prefix = arrival(build_boards.href_to(config, node))
        if prefix != "/":
            out.append((prefix, node))
    out.sort(key=lambda m: len(m[0]), reverse=True)
    out.append(("/", Path(config.directory_folder)))
    return out


def resolve(url_path: str, table: list[tuple[str, Path]]) -> Path | None:
    """The file a request path names, or None when it is outside every mount, names a dot
    segment, climbs out of its folder, or is a directory without an index.html."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(url_path).path)
    path = posixpath.normpath("/" + path.lstrip("/"))
    segments = [s for s in path.split("/") if s]
    if any(s.startswith(".") or "\\" in s or ":" in s for s in segments):
        return None
    for prefix, folder in table:
        if prefix == "/":
            rest = segments
        elif path == prefix or path.startswith(prefix + "/"):
            rest = [s for s in path[len(prefix):].split("/") if s]
        else:
            continue
        base = folder.resolve()
        target = base.joinpath(*rest).resolve() if rest else base
        if target != base and base not in target.parents:
            return None
        if target.is_dir():
            target = target / "index.html"
        return target if target.is_file() else None
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    table: list[tuple[str, Path]] = []
    memory: Path | None = None   # the memory checkout the boards are drawn from
    token: str | None = None     # this start's token (serve_post.py); none: every post is refused
    started: str = ""
    inbox: board_inbox.Inbox | None = None

    def _local(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            name = host.split("]", 1)[0] + "]"
        else:
            name = host.rsplit(":", 1)[0] if ":" in host else host
        return name in LOCAL_HOSTS

    def send_head(self):  # noqa: D401 – the standard handler's seam
        if not self._local():
            self.send_error(403, "this server answers only on this machine")
            return None
        path = urllib.parse.urlsplit(self.path).path
        if path == STATUS_PATH:
            return self._status()
        if path in serve_post.GET_PATHS:
            return serve_post.get(self, path)
        target = resolve(self.path, self.table)
        if target is None:
            self.send_error(404, "not found")
            return None
        self.path = "/" + target.name   # the parent's send_head serves what translate_path returns
        self._target = target
        return super().send_head()

    def do_POST(self):  # noqa: N802 – the standard handler's name
        serve_post.post(self)

    def _status(self):
        """The memory checkout's status as JSON, worked out now and never cached."""
        body = json.dumps(memory_status(self.memory)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return io.BytesIO(body)

    def translate_path(self, path):
        return str(getattr(self, "_target", ""))

    def list_directory(self, path):
        self.send_error(404, "not found")
        return None

    def log_message(self, format, *args):  # quieter: one line per request on stderr, as before
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


def make_handler(config: board_config.Config):
    """The handler for one start of the server: its mounts, and a token of its own."""
    return type("BoardHandler", (Handler,), {"table": mounts(config), "memory": Path(config.memory),
                                             "token": serve_post.new_token(), "started": serve_post.now_iso(),
                                             "inbox": board_inbox.Inbox.from_config(config)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--root", help="the brain root (default: found from here)")
    parser.add_argument("--list", action="store_true", help="print the mounts and exit")
    args = parser.parse_args(argv)
    config = board_config.Config(args.root or os.getcwd())
    handler = make_handler(config)
    if args.list:
        for prefix, folder in handler.table:
            print(f"{prefix}  ->  {folder}")
        return 0
    server = http.server.ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"serving the boards on http://localhost:{args.port}/ ({len(handler.table)} folders)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
