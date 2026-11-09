"""The board server's post plumbing (design 04 of the personal CRM, increments 1 and 2): the per-start
token, the checks every `POST` passes, and the two small JSON answers beside the boards.

`serve_boards.py` serves the pages and calls this module for:

- `GET /_board-server.json` – `{"server": 1, "token": ..., "started": <iso>, "saves": [kinds],
  "mail": false}`, `Cache-Control: no-store`. The token is `secrets.token_urlsafe(32)`, made when
  the server starts, held in memory only and never written to a file. It is served only under the
  Host check and with no CORS header, so another site's script cannot read it.
- `GET /_saved.json` – the saved files still waiting in the inbox folder (`board_inbox.py`).
- `POST /_save/<kind>` – files a page's saved decisions through `board_inbox.py`.
- `POST /_mail/text` – one snapshot message's whole text, fetched live (increment 4; only when the
  mail-review skill is checked out, else 404 and `"mail": false`): `{"account", "threadId",
  "messageId"}` answers `{"text", "chars", "cut", "fetched"}`. It passes the same checks as every
  post, reads only (`inbox_serve.py` calls `messages.get` and nothing else) and writes nothing.

A post is refused with 403 and the same two words, `{"refused": "not allowed"}`, when the Host is
not this machine, the `Origin` is not this server's own (`http://localhost:<port>` or
`http://127.0.0.1:<port>`), the `Content-Type` is not `application/json` (a cross-site post of
that type needs a preflight this server never grants), or `X-Board-Token` is not this start's
token. A body over 25 MB is refused with 413 before it is read; one with no length with 411; a
body that is not a JSON object with 400. No answer carries an `Access-Control-*` header.
"""
from __future__ import annotations

import datetime
import hmac
import io
import json
import secrets

import board_inbox

SERVER_PATH = "/_board-server.json"
SAVED_PATH = "/_saved.json"
SAVE_PREFIX = "/_save/"
MAIL_TEXT_PATH = "/_mail/text"
GET_PATHS = (SERVER_PATH, SAVED_PATH)
TOKEN_HEADER = "X-Board-Token"
MAX_BODY = 25 * 1024 * 1024          # screenshots travel as data URIs
ORIGIN_HOSTS = ("localhost", "127.0.0.1")
NOT_ALLOWED = {"refused": "not allowed"}
SERVER_VERSION = 1


def new_token() -> str:
    return secrets.token_urlsafe(32)


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _encode(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _headers(handler, status: int, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()


def answer(handler, status: int, data: dict) -> None:
    """Write a JSON answer to a post."""
    body = _encode(data)
    _headers(handler, status, body)
    handler.wfile.write(body)


def get(handler, path: str):
    """The answer to one of `GET_PATHS`, as `send_head` returns it (headers sent, body to copy)."""
    if handler.token is None or handler.inbox is None:
        handler.send_error(404, "not found")
        return None
    if path == SERVER_PATH:
        data = {"server": SERVER_VERSION, "token": handler.token, "started": handler.started,
                "saves": handler.inbox.kinds(), "mail": handler.inbox.fetcher is not None}
    else:
        data = {"folder": handler.inbox.shown, "saved": handler.inbox.waiting()}
    body = _encode(data)
    _headers(handler, 200, body)
    return io.BytesIO(body)


def allowed(handler) -> bool:
    """The Origin, content type and token of a post from this server's own page."""
    if handler.token is None:
        return False
    port = handler.server.server_address[1]
    if (handler.headers.get("Origin") or "") not in {"http://%s:%d" % (h, port) for h in ORIGIN_HOSTS}:
        return False
    if (handler.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
        return False
    sent = handler.headers.get(TOKEN_HEADER) or ""
    return hmac.compare_digest(sent.encode("utf-8"), handler.token.encode("utf-8"))


def _length(handler) -> int | None:
    text = handler.headers.get("Content-Length")
    try:
        n = int(text) if text is not None else -1
    except ValueError:
        n = -1
    return n if n >= 0 else None


def post(handler) -> None:
    """Every POST: refuse what fails a check, else file the body (`board_inbox.Inbox.save`)."""
    if not handler._local():
        handler.close_connection = True
        return answer(handler, 403, NOT_ALLOWED)
    length = _length(handler)
    if length is None:
        handler.close_connection = True
        return answer(handler, 411, {"refused": "the post has no length"})
    if length > MAX_BODY:
        handler.close_connection = True
        return answer(handler, 413, {"refused": "the post is larger than 25 MB"})
    raw = handler.rfile.read(length)
    if not allowed(handler):
        return answer(handler, 403, NOT_ALLOWED)
    path = handler.path.split("?", 1)[0].split("#", 1)[0]
    kind = path[len(SAVE_PREFIX):] if path.startswith(SAVE_PREFIX) else ""
    mail = path == MAIL_TEXT_PATH and handler.inbox is not None and handler.inbox.fetcher is not None
    if handler.inbox is None or (not mail and kind not in handler.inbox.kinds()):
        return answer(handler, 404, {"refused": "nothing is saved at that address"})
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        body = None
    if not isinstance(body, dict):
        return answer(handler, 400, {"refused": "the post is not a JSON object"})
    if mail:      # read-only: one message's whole text, nothing written
        status, data = handler.inbox.mail_text(body)
        return answer(handler, status, data)
    try:
        return answer(handler, 200, handler.inbox.save(kind, raw, body))
    except board_inbox.Refused as err:
        return answer(handler, 400, {"refused": str(err)})
    except OSError:      # the folder could not be written: a reason of our own, never the path
        return answer(handler, 500, {"refused": "the inbox folder could not be written"})
