"""Local browser UI for managing a reusable HighLevel agency connection."""

from __future__ import annotations

import argparse
import html
import secrets
import threading
import urllib.parse
import webbrowser
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import HighLevelConnection, HighLevelOAuthError


def validate_installation_url(value: str) -> str:
    value = value.strip()
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise HighLevelOAuthError(
            "Use the HTTPS Installation URL generated in the HighLevel app Auth pane."
        )
    return value


def installation_url_with_state(value: str, state: str) -> str:
    parsed = urllib.parse.urlparse(validate_installation_url(value))
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, item) for key, item in query if key != "state"]
    query.append(("state", state))
    return urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query))
    )


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font:16px system-ui,sans-serif;max-width:960px;margin:3rem auto;padding:0 1rem;color:#182230}}
.card{{border:1px solid #d0d5dd;border-radius:12px;padding:1.25rem;margin:1rem 0}}
a,button{{background:#155eef;color:#fff;border:0;border-radius:7px;padding:.65rem 1rem;
text-decoration:none;cursor:pointer;display:inline-block}} button.danger{{background:#b42318}}
input[type=url]{{padding:.65rem;width:min(760px,95%);margin:.45rem 0}}
code{{background:#f2f4f7;padding:.15rem .3rem;word-break:break-all}}
.ok{{color:#067647}} .error{{color:#b42318}} .muted{{color:#667085}}
table{{border-collapse:collapse;width:100%}} td,th{{text-align:left;border-bottom:1px solid #ddd;padding:.55rem}}
</style></head><body><h1>{html.escape(title)}</h1>{body}</body></html>""".encode()


class Manager:
    def __init__(self, connection: HighLevelConnection):
        self.connection = connection
        self.installation_url = connection.config.installation_url
        self.states: set[str] = set()
        self.message = ""


def handler_for(manager: Manager):
    class Handler(BaseHTTPRequestHandler):
        def send_page(self, title: str, body: str, status: int = 200) -> None:
            payload = page(title, body)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(payload)

        def redirect(
            self,
            location: str,
            *,
            state_cookie: str | None = None,
        ) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            if state_cookie:
                cookie = cookies.SimpleCookie()
                cookie["ghl_oauth_state"] = state_cookie
                cookie["ghl_oauth_state"]["httponly"] = True
                cookie["ghl_oauth_state"]["samesite"] = "Lax"
                cookie["ghl_oauth_state"]["path"] = "/oauth/callback"
                cookie["ghl_oauth_state"]["max-age"] = 600
                self.send_header("Set-Cookie", cookie.output(header="").strip())
            self.end_headers()

        def form(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 100_000:
                raise HighLevelOAuthError("The submitted form is too large.")
            return urllib.parse.parse_qs(self.rfile.read(length).decode())

        def state_cookie(self) -> str:
            jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            morsel = jar.get("ghl_oauth_state")
            return morsel.value if morsel else ""

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path == "/":
                    self.dashboard()
                elif parsed.path == "/oauth/callback":
                    self.callback(urllib.parse.parse_qs(parsed.query))
                elif parsed.path == "/health":
                    self.send_page(
                        "HighLevel connection manager",
                        "<p class='ok'>Running</p>",
                    )
                else:
                    self.send_page("Not found", "<p>Page not found.</p>", 404)
            except HighLevelOAuthError as exc:
                self.send_page(
                    "HighLevel connection error",
                    f"<p class='error'>{html.escape(str(exc))}</p>"
                    "<p><a href='/'>Back</a></p>",
                    400,
                )

        def do_POST(self) -> None:
            try:
                if self.path == "/connect":
                    form = self.form()
                    manager.installation_url = validate_installation_url(
                        str(form.get("installation_url", [""])[0])
                    )
                    state = secrets.token_urlsafe(32)
                    manager.states.add(state)
                    self.redirect(
                        installation_url_with_state(
                            manager.installation_url, state
                        ),
                        state_cookie=state,
                    )
                    return
                if self.path == "/refresh":
                    manager.connection.refresh()
                    manager.message = "Agency token refreshed and rotated securely."
                elif self.path == "/locations":
                    manager.connection.refresh_location_catalog()
                    manager.message = "Approved subaccount catalogue refreshed."
                elif self.path == "/disconnect":
                    manager.connection.clear_local_authorisation()
                    manager.message = (
                        "Local token cleared. Uninstall the app in HighLevel "
                        "to revoke its external authorisation."
                    )
                else:
                    self.send_page("Not found", "<p>Page not found.</p>", 404)
                    return
                self.redirect("/")
            except HighLevelOAuthError as exc:
                self.send_page(
                    "HighLevel connection error",
                    f"<p class='error'>{html.escape(str(exc))}</p>"
                    "<p><a href='/'>Back</a></p>",
                    400,
                )

        def callback(self, query: dict[str, list[str]]) -> None:
            cookie_state = self.state_cookie()
            returned_state = str(query.get("state", [""])[0])
            candidate = returned_state or cookie_state
            if (
                not candidate
                or candidate not in manager.states
                or cookie_state != candidate
                or (returned_state and returned_state != candidate)
            ):
                raise HighLevelOAuthError(
                    "The OAuth browser session was missing or invalid."
                )
            manager.states.remove(candidate)
            if query.get("error"):
                description = query.get("error_description", query["error"])[0]
                raise HighLevelOAuthError(str(description))
            code = str(query.get("code", [""])[0])
            if not code:
                raise HighLevelOAuthError(
                    "HighLevel did not return an authorisation code."
                )
            manager.connection.exchange_code(code)
            try:
                manager.connection.refresh_location_catalog()
                manager.message = (
                    "Agency connected and approved subaccounts discovered."
                )
            except HighLevelOAuthError as exc:
                manager.message = (
                    "Agency connected. Subaccount discovery needs review: "
                    f"{exc}"
                )
            self.redirect("/")

        def dashboard(self) -> None:
            status = manager.connection.status()
            message = (
                f"<div class='card'><p class='ok'>{html.escape(manager.message)}</p></div>"
                if manager.message
                else ""
            )
            manager.message = ""
            if not status["connected"]:
                error = (
                    f"<p class='error'>{html.escape(str(status['error']))}</p>"
                    if status.get("error")
                    else "<p>HighLevel agency access is not connected.</p>"
                )
                body = f"""
{message}<div class="card">{error}
<p>Configured callback: <code>{html.escape(status['redirect_uri'])}</code></p>
<p>Paste the standard or white-label <strong>Installation URL</strong> generated
in the HighLevel app Auth pane. It is kept only in this running process.</p>
<form method="post" action="/connect">
<input type="url" name="installation_url" required
value="{html.escape(manager.installation_url, quote=True)}"
placeholder="https://marketplace.gohighlevel.com/..."><br>
<button>Connect HighLevel agency</button></form></div>
<p class="muted">Token store: <code>{html.escape(status['token_store'])}</code></p>"""
                self.send_page("HighLevel connection manager", body)
                return

            rows = "".join(
                "<tr>"
                f"<td>{html.escape(str(item.get('name') or ''))}</td>"
                f"<td><code>{html.escape(str(item.get('id') or ''))}</code></td>"
                "</tr>"
                for item in status["location_catalog"]
            )
            if not rows:
                rows = (
                    "<tr><td colspan='2'>No subaccounts are recorded yet. "
                    "Use Refresh subaccounts.</td></tr>"
                )
            warning = (
                f"<p class='error'>{html.escape(str(status['location_discovery_warning']))}</p>"
                if status.get("location_discovery_warning")
                else ""
            )
            body = f"""
{message}<div class="card"><p class="ok">Connected with a Company agency token.</p>
<p>Company: <strong>{html.escape(str(status['company_profile'].get('name') or ''))}</strong></p>
<p>Company ID: <code>{html.escape(str(status['company_id']))}</code></p>
<p>Granted scopes: <code>{html.escape(str(status['scope']))}</code></p>
<p>All locations approved: <strong>{html.escape(str(status['approve_all_locations']))}</strong><br>
Future locations included: <strong>{html.escape(str(status['install_to_future_locations']))}</strong></p>
{warning}</div>
<div class="card"><h2>Agency subaccounts</h2>
<table><thead><tr><th>Name</th><th>Location ID</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="muted">Catalogue refreshed:
{html.escape(str(status.get('location_catalog_refreshed_at') or 'not yet'))}</p></div>
<form method="post" action="/locations" style="display:inline">
<button>Refresh subaccounts</button></form>
<form method="post" action="/refresh" style="display:inline">
<button>Refresh agency token</button></form>
<form method="post" action="/disconnect" style="display:inline"
onsubmit="return confirm('Clear the local HighLevel token? This does not uninstall the app in HighLevel.')">
<button class="danger">Clear local token</button></form>
<p class="muted">Token store: <code>{html.escape(status['token_store'])}</code></p>"""
            self.send_page("HighLevel connection manager", body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=8766, type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    connection = HighLevelConnection.from_environment()
    server = ThreadingHTTPServer(
        (args.host, args.port),
        handler_for(Manager(connection)),
    )
    url = f"http://localhost:{args.port}/"
    print(f"HighLevel connection manager: {url}")
    print(f"OAuth callback: {connection.config.redirect_uri}")
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
