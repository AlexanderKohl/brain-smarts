"""Local browser UI for managing a Google Workspace OAuth connection."""

from __future__ import annotations

import argparse
import html
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import DEFAULT_SCOPES, GoogleConnection, GoogleOAuthError


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font:16px system-ui,sans-serif;max-width:900px;margin:3rem auto;padding:0 1rem;color:#172b4d}}
.card{{border:1px solid #ccd6e0;border-radius:12px;padding:1.25rem;margin:1rem 0}}
a,button{{background:#1a73e8;color:#fff;border:0;border-radius:7px;padding:.65rem 1rem;
text-decoration:none;cursor:pointer;display:inline-block}} button.danger{{background:#b42318}}
code{{background:#eef2f6;padding:.15rem .3rem;word-break:break-all}}
.ok{{color:#067647}} .error{{color:#b42318}} .muted{{color:#52606d}}
</style></head><body><h1>{html.escape(title)}</h1>{body}</body></html>""".encode()


class Manager:
    def __init__(self, connection: GoogleConnection):
        self.connection = connection
        self.states: set[str] = set()


def handler_for(manager: Manager):
    class Handler(BaseHTTPRequestHandler):
        def send_page(self, title: str, body: str, status: int = 200) -> None:
            payload = page(title, body)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path == "/":
                    self.dashboard()
                elif parsed.path == "/connect":
                    state = secrets.token_urlsafe(32)
                    manager.states.add(state)
                    self.redirect(manager.connection.authorisation_url(state))
                elif parsed.path == "/oauth/callback":
                    self.callback(urllib.parse.parse_qs(parsed.query))
                elif parsed.path == "/health":
                    self.send_page(
                        "Google Workspace connection manager",
                        "<p class='ok'>Running</p>",
                    )
                else:
                    self.send_page("Not found", "<p>Page not found.</p>", 404)
            except GoogleOAuthError as exc:
                self.send_page(
                    "Google connection error",
                    f"<p class='error'>{html.escape(str(exc))}</p>"
                    "<p><a href='/'>Back</a></p>",
                    400,
                )

        def do_POST(self) -> None:
            try:
                if self.path == "/refresh":
                    manager.connection.refresh()
                elif self.path == "/disconnect":
                    manager.connection.revoke()
                else:
                    self.send_page("Not found", "<p>Page not found.</p>", 404)
                    return
                self.redirect("/")
            except GoogleOAuthError as exc:
                self.send_page(
                    "Google connection error",
                    f"<p class='error'>{html.escape(str(exc))}</p>"
                    "<p><a href='/'>Back</a></p>",
                    400,
                )

        def callback(self, query: dict[str, list[str]]) -> None:
            state = query.get("state", [""])[0]
            if not state or state not in manager.states:
                raise GoogleOAuthError("The OAuth state was missing or invalid.")
            manager.states.remove(state)
            if query.get("error"):
                raise GoogleOAuthError(
                    query.get("error_description", query["error"])[0]
                )
            code = query.get("code", [""])[0]
            if not code:
                raise GoogleOAuthError(
                    "Google did not return an authorisation code."
                )
            manager.connection.exchange_code(code)
            self.redirect("/")

        def dashboard(self) -> None:
            status = manager.connection.status()
            alias = status["account_alias"]
            registry_email = status["registry_email"]
            if not status["connected"]:
                detail = (
                    f"<p class='error'>{html.escape(status.get('error', 'Not connected'))}</p>"
                    if status.get("error")
                    else "<p>This Google account is not connected.</p>"
                )
                body = f"""
<div class="card">
<p>Account alias: <code>{html.escape(alias)}</code></p>
<p>Expected login: <code>{html.escape(registry_email)}</code></p>
{detail}
<p class="muted">Vault entry: <code>{html.escape(str(status.get('vault_entry', '')))}</code></p>
</div>
<div class="card">
<p>Scopes requested on connect:</p>
<p><code>{html.escape(status.get('requested_scopes', ''))}</code></p>
<p><a href="/connect">Connect with Google</a></p>
</div>
<p>Token store: <code>{html.escape(str(status.get('token_store', '')))}</code></p>
"""
                self.send_page("Google Workspace connection manager", body)
                return

            missing = status.get("missing_scopes") or []
            scope_warning = (
                "<p class='error'>Missing granted scopes: <code>"
                + html.escape(" ".join(missing))
                + "</code>. Reconnect to grant them.</p>"
                if missing
                else ""
            )
            body = f"""
<div class="card">
<p class="ok">Connected.</p>
<p>Account alias: <code>{html.escape(alias)}</code></p>
<p>Registry email: <code>{html.escape(registry_email)}</code></p>
<p>Connected email: <code>{html.escape(str(status.get('email') or ''))}</code></p>
<p>Name: {html.escape(str(status.get('name') or ''))}</p>
<p>Granted scopes:</p>
<p><code>{html.escape(str(status.get('scopes') or ''))}</code></p>
{scope_warning}
</div>
<form method="post" action="/refresh" style="display:inline">
<button>Refresh token</button></form>
<p><a href="/connect">Re-authorise</a></p>
<form method="post" action="/disconnect" style="display:inline"
onsubmit="return confirm('Disconnect this Google authorisation?')">
<button class="danger">Disconnect</button></form>
<p>Token store: <code>{html.escape(str(status.get('token_store', '')))}</code></p>
<p class="muted">Default scopes include: {html.escape(' '.join(DEFAULT_SCOPES[:3]))} …</p>
"""
            self.send_page("Google Workspace connection manager", body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--account",
        help="Google account alias from the CRM node's data/google-accounts.json",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=8767, type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    connection = GoogleConnection.from_environment(args.account)
    server = ThreadingHTTPServer(
        (args.host, args.port), handler_for(Manager(connection))
    )
    url = f"http://localhost:{args.port}/"
    print(f"Google Workspace connection manager: {url}")
    print(f"Account alias: {connection.account.alias}")
    print(f"Expected login: {connection.account.email}")
    print(f"Vault entry: {connection.config.account.vault_entry}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
