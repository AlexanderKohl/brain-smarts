"""One call to an OAuth token endpoint (a refresh or a code exchange), with its failure sorted by
what certainly happened (design synced-secrets-repository.md, section 9; refresh-failure plan,
part A):

- nothing was sent: the failure came while a new connection was made (name lookup, refused,
  unreachable, proxy tunnel, TLS handshake). Raised as ProviderNotCalled; the journal record is
  removed and the next attempt refreshes normally.
- refused: the endpoint answered HTTP 400 or 401 with a JSON body carrying ``error`` (RFC 6749,
  section 5.2). Raised as ProviderRefused with the status and the error code; a well-formed OAuth
  error answer issues no token, so the record is removed too. ``invalid_grant`` is left to the
  connector, which raises its own sign-in-needed error from it.
- uncertain: anything else after the connection was made (a time-out, a reset, HTTP 500 to 599,
  any other 4xx, a body that is not a well-formed OAuth error). The plain exception, or
  TokenEndpointError for an answer; the record stays in calling.

"Nothing was sent" is decided by a fact, never from an exception's type: every call opens a new
connection (never a reused one; Python's ssl sends no TLS early data) through a connection class
whose connect() sets a flag once the socket, any proxy tunnel and the TLS handshake are complete.
A 2xx answer is returned as it is; reading it is the connector's job. Nothing is retried, since no
second call may carry the same refresh token, and nothing is logged."""

from __future__ import annotations

import http.client
import json
import ssl
import urllib.parse
import urllib.request
from typing import Any, Mapping

from secret_store.journal import ProviderNotCalled, ProviderRefused

BODY_LIMIT = 1000  # characters of an error answer kept on the exception, never logged


class TokenEndpointError(Exception):
    """An answer from the token endpoint that is neither a token nor a well-formed OAuth error: the
    provider may have acted on the request, so the refresh is uncertain."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"the token endpoint answered HTTP {status}; the refresh is uncertain")
        self.status, self.body = status, body


class _TokenConnection(http.client.HTTPSConnection):
    """An HTTPS connection that records when it is fully made. handshake_done turns true only after
    the socket, any proxy tunnel and the TLS handshake have all succeeded; no request byte is
    written before that."""

    handshake_done = False

    def connect(self) -> None:
        super().connect()
        self.handshake_done = True


def _encode(body: Any) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return urllib.parse.urlencode(dict(body)).encode("ascii")


def _connection(host: str, port: int, timeout: float) -> _TokenConnection:
    """A new connection, through the HTTPS proxy of the environment when one applies."""
    context = ssl.create_default_context()
    proxy = urllib.request.getproxies().get("https")
    if proxy and not urllib.request.proxy_bypass(host):
        parts = urllib.parse.urlsplit(proxy if "://" in proxy else f"http://{proxy}")
        conn = _TokenConnection(parts.hostname, parts.port or 8080, timeout=timeout, context=context)
        conn.set_tunnel(host, port)
        return conn
    return _TokenConnection(host, port, timeout=timeout, context=context)


def _oauth_error(status: int, data: bytes) -> str | None:
    """The error code of a well-formed OAuth error answer, or None."""
    if status not in (400, 401):
        return None
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    error = parsed.get("error") if isinstance(parsed, dict) else None
    return error if isinstance(error, str) and error.strip() else None


def post_token(url: str, headers: Mapping[str, str], body: Any, timeout: float = 60) -> tuple[int, bytes]:
    """POST body (bytes, text, or a mapping sent form-encoded) to the token endpoint at url and
    return (status, bytes) for a 2xx answer. Raises ProviderNotCalled, ProviderRefused,
    TokenEndpointError or the plain exception, as the module docstring sorts them."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ProviderNotCalled("a token endpoint must be an https address; nothing was sent")
    data = _encode(body)
    sent_headers = dict(headers)
    if not any(k.lower() == "content-type" for k in sent_headers):
        sent_headers["Content-Type"] = "application/x-www-form-urlencoded"
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    conn = _connection(parts.hostname, parts.port or 443, timeout)
    try:
        try:
            conn.connect()
            conn.request("POST", path, body=data, headers=sent_headers)
            response = conn.getresponse()
            status, payload = response.status, response.read()
        except Exception as exc:
            if not conn.handshake_done:
                raise ProviderNotCalled(
                    f"no connection to {parts.hostname} ({type(exc).__name__}); nothing was sent") from exc
            raise
    finally:
        conn.close()
    if 200 <= status < 300:
        return status, payload
    text = payload.decode("utf-8", errors="replace")[:BODY_LIMIT]
    error = _oauth_error(status, payload)
    if error is not None:
        raise ProviderRefused(status, error, text)
    raise TokenEndpointError(status, text)
