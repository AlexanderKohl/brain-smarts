"""Local browser UI for managing a reusable Xero OAuth connection."""

from __future__ import annotations

import argparse
import html
import json
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import SCOPE_PROFILES, XeroConnection, XeroOAuthError


PROFILE_DETAILS = {
    "accounting": ("Accounting", "Transactions, reports, settings, contacts and attachments"),
    "identity": ("Identity", "Xero user identity, profile and email"),
    "payroll": ("Payroll", "Employees, pay runs, payslips, timesheets and settings"),
    "files": ("Files", "File library"),
    "assets": ("Assets", "Fixed assets"),
    "projects": ("Projects", "Projects, tasks and time"),
    "einvoicing": ("eInvoicing", "eInvoicing registration information"),
}

# Sentinel in the organisation dropdown: starts OAuth to connect additional orgs.
ADD_ORGANISATION_VALUE = "__add_organisation__"
ADD_ORGANISATION_DEFAULT_PROFILES = ["accounting"]


def scopes_for_profiles(profile_names: list[str]) -> str:
    selected = list(dict.fromkeys(profile_names))
    if not selected:
        raise XeroOAuthError("Select at least one Xero scope group.")
    unknown = [name for name in selected if name not in SCOPE_PROFILES]
    if unknown:
        raise XeroOAuthError(f"Unknown Xero scope profile: {unknown[0]}")
    scopes = dict.fromkeys(
        scope for name in selected for scope in SCOPE_PROFILES[name]
    )
    return " ".join(scopes)


def scope_selector(
    granted_scope_text: str,
    *,
    default_accounting: bool = False,
    selected_org_name: str | None = None,
    connected: bool = False,
) -> str:
    granted = set(granted_scope_text.split())
    rows = []
    for name, scopes in SCOPE_PROFILES.items():
        label, description = PROFILE_DETAILS[name]
        relevant = set(scopes) - {"offline_access"}
        missing = relevant - granted
        status = "Granted" if relevant and not missing else f"{len(missing)} not granted"
        checked = " checked" if default_accounting and name == "accounting" else ""
        rows.append(
            "<label class='scope-option'>"
            f"<input type='checkbox' name='profile' value='{html.escape(name)}'{checked}> "
            f"<strong>{html.escape(label)}</strong> — {html.escape(description)}"
            f"<small>{html.escape(status)}</small></label>"
        )
    if connected:
        org_label = selected_org_name or "the selected organisation"
        heading = f"Add scope groups for {html.escape(org_label)}"
        intro = (
            f"<p>These scopes apply to the <strong>currently selected organisation</strong> "
            f"(<strong>{html.escape(org_label)}</strong>) and this OAuth connection. "
            "Tick groups to request, then authorise — this is <em>not</em> how you add another "
            "organisation. To connect more orgs, use <strong>Add Organisation…</strong> in the "
            "Organisation dropdown above.</p>"
            "<p>Selected groups are deduplicated into one Xero authorisation request. If a group "
            "is unavailable to this app, Xero may reject the request with "
            "<code>invalid_scope</code>.</p>"
        )
        button = "Authorise selected groups for this organisation"
    else:
        heading = "Connect to Xero"
        intro = (
            "<p>Select one or more scope groups for the initial connection. Accounting is "
            "selected by default. On the Xero consent screen you can choose which organisations "
            "to allow.</p>"
            "<p>Selected groups are deduplicated into one authorisation request. If a group is "
            "unavailable to this app, Xero may reject the request with "
            "<code>invalid_scope</code>.</p>"
        )
        button = "Authorise and connect"
    return (
        f"<div class='card'><h2>{heading}</h2>{intro}"
        "<form method='post' action='/connect'><div class='scope-grid'>"
        + "".join(rows)
        + f"</div><button type='submit'>{html.escape(button)}</button></form></div>"
    )


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font:16px system-ui,sans-serif;max-width:900px;margin:3rem auto;padding:0 1rem;color:#172b4d}}
.card{{border:1px solid #ccd6e0;border-radius:12px;padding:1.25rem;margin:1rem 0}}
a,button{{background:#13b5ea;color:#fff;border:0;border-radius:7px;padding:.65rem 1rem;
text-decoration:none;cursor:pointer;display:inline-block}} button.danger{{background:#b42318}}
select{{padding:.6rem;min-width:300px}} code{{background:#eef2f6;padding:.15rem .3rem}}
.ok{{color:#067647}} .error{{color:#b42318}} table{{border-collapse:collapse;width:100%}}
td,th{{text-align:left;border-bottom:1px solid #ddd;padding:.55rem}}
.scope-grid{{display:grid;gap:.65rem;margin:1rem 0}} .scope-option{{display:block;
border:1px solid #d8e0e8;border-radius:7px;padding:.75rem}} .scope-option small{{
display:block;color:#52606d;margin:.3rem 0 0 1.5rem}}
</style></head><body><h1>{html.escape(title)}</h1>{body}</body></html>""".encode()


class Manager:
    def __init__(self, connection: XeroConnection):
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

        def begin_authorise(self, profiles: list[str]) -> None:
            scopes = scopes_for_profiles(profiles)
            state = secrets.token_urlsafe(32)
            manager.states.add(state)
            self.redirect(manager.connection.authorisation_url(state, scopes))

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path == "/":
                    self.dashboard()
                elif parsed.path == "/connect":
                    query = urllib.parse.parse_qs(parsed.query)
                    profiles = query.get("profile", list(ADD_ORGANISATION_DEFAULT_PROFILES))
                    self.begin_authorise(profiles)
                elif parsed.path == "/oauth/callback":
                    self.callback(urllib.parse.parse_qs(parsed.query))
                elif parsed.path == "/health":
                    self.send_page("Xero connection manager", "<p class='ok'>Running</p>")
                else:
                    self.send_page("Not found", "<p>Page not found.</p>", 404)
            except XeroOAuthError as exc:
                self.send_page(
                    "Xero connection error",
                    f"<p class='error'>{html.escape(str(exc))}</p><p><a href='/'>Back</a></p>",
                    400,
                )

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            form = urllib.parse.parse_qs(self.rfile.read(length).decode())
            try:
                if self.path == "/connect":
                    self.begin_authorise(form.get("profile", []))
                    return
                elif self.path == "/refresh":
                    manager.connection.refresh()
                elif self.path == "/tenant":
                    tenant_id = str(form.get("tenant_id", [""])[0])
                    if tenant_id == ADD_ORGANISATION_VALUE:
                        self.begin_authorise(list(ADD_ORGANISATION_DEFAULT_PROFILES))
                        return
                    manager.connection.select_tenant(tenant_id)
                elif self.path == "/disconnect":
                    manager.connection.revoke()
                else:
                    self.send_page("Not found", "<p>Page not found.</p>", 404)
                    return
                self.redirect("/")
            except XeroOAuthError as exc:
                self.send_page(
                    "Xero connection error",
                    f"<p class='error'>{html.escape(str(exc))}</p><p><a href='/'>Back</a></p>",
                    400,
                )

        def callback(self, query: dict[str, list[str]]) -> None:
            state = query.get("state", [""])[0]
            if not state or state not in manager.states:
                raise XeroOAuthError("The OAuth state was missing or invalid.")
            manager.states.remove(state)
            if query.get("error"):
                raise XeroOAuthError(query.get("error_description", query["error"])[0])
            code = query.get("code", [""])[0]
            if not code:
                raise XeroOAuthError("Xero did not return an authorisation code.")
            manager.connection.exchange_code(code)
            self.redirect("/")

        def dashboard(self) -> None:
            status = manager.connection.status()
            if not status["connected"]:
                detail = (
                    f"<p class='error'>{html.escape(status.get('error', 'Not connected'))}</p>"
                    if status.get("error")
                    else "<p>Xero is not connected.</p>"
                )
                body = (
                    f"<div class='card'>{detail}</div>"
                    + scope_selector("", default_accounting=True, connected=False)
                    + f"<p>Token store: <code>{html.escape(status['token_file'])}</code></p>"
                )
                self.send_page("Xero connection manager", body)
                return

            connections = status["connections"]
            selected = status.get("selected_tenant_id")
            selected_org_name = next(
                (
                    str(item.get("tenantName") or item["tenantId"])
                    for item in connections
                    if item.get("tenantId") == selected
                ),
                None,
            )
            missing_scopes = status.get("missing_scopes") or []
            scope_warning = (
                "<p class='error'>Missing granted scopes: <code>"
                + html.escape(" ".join(missing_scopes))
                + "</code>. Reauthorise to grant them.</p>"
                if missing_scopes
                else ""
            )
            options = "".join(
                f"<option value='{html.escape(str(item['tenantId']))}' "
                f"{'selected' if item.get('tenantId') == selected else ''}>"
                f"{html.escape(str(item.get('tenantName') or item['tenantId']))}</option>"
                for item in connections
            )
            add_org_option = (
                f"<option value='{html.escape(ADD_ORGANISATION_VALUE)}'>"
                "Add Organisation…</option>"
            )
            add_org_query = urllib.parse.urlencode(
                [("profile", name) for name in ADD_ORGANISATION_DEFAULT_PROFILES]
            )
            rows = "".join(
                "<tr>"
                f"<td>{html.escape(str(item.get('tenantName', '')))}</td>"
                f"<td><code>{html.escape(str(item.get('tenantId', '')))}</code></td>"
                f"<td>{html.escape(str(item.get('tenantType', '')))}</td>"
                "</tr>"
                for item in connections
            )
            body = f"""
<div class="card"><p class="ok">Connected to Xero.</p>
<p>Default Accounting scopes: <code>{html.escape(str(status.get('requested_scopes', '')))}</code></p>
<p>Granted scopes: <code>{html.escape(str(status.get('scopes', '')))}</code></p>
{scope_warning}
<form method="post" action="/tenant" id="org-form">
<label for="org-select">Organisation<br>
<select name="tenant_id" id="org-select">{options}{add_org_option}</select></label>
<button type="submit">Save selection</button></form>
<p>Choose an organisation and <strong>Save selection</strong> to set the active org for API
calls. Choose <strong>Add Organisation…</strong> to open Xero consent and connect another
organisation (Accounting scopes). Xero’s consent screen may list every org already linked to
this app — tick any additional ones you want.</p>
</div>
<div class="card"><table><thead><tr><th>Organisation</th><th>Tenant ID</th>
<th>Type</th></tr></thead><tbody>{rows}</tbody></table></div>
<form method="post" action="/refresh" style="display:inline"><button>Refresh token</button></form>
{scope_selector(str(status.get('scopes', '')), selected_org_name=selected_org_name, connected=True)}
<form method="post" action="/disconnect" style="display:inline"
onsubmit="return confirm('Disconnect this Xero authorisation?')">
<button class="danger">Disconnect</button></form>
<p>Token store: <code>{html.escape(status['token_file'])}</code></p>
<script>
(function () {{
  var select = document.getElementById('org-select');
  if (!select) return;
  select.addEventListener('change', function () {{
    if (select.value === {json.dumps(ADD_ORGANISATION_VALUE)}) {{
      window.location.href = '/connect?{html.escape(add_org_query)}';
    }}
  }});
}})();
</script>"""
            self.send_page("Xero connection manager", body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    connection = XeroConnection.from_environment()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(Manager(connection)))
    url = f"http://localhost:{args.port}/"
    print(f"Xero connection manager: {url}")
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
