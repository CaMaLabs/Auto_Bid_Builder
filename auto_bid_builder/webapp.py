from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import urllib.parse

from .settings import AppSettings, ProviderSettings, SecretStore, load_settings, save_settings

CSS = """
body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#f5f7fa;color:#111827}main{max-width:1100px;margin:32px auto;padding:0 20px}.card{background:white;border:1px solid #d7dce3;border-radius:12px;padding:18px;margin:16px 0;box-shadow:0 1px 3px #0001}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}.provider{border:1px solid #d7dce3;border-radius:10px;padding:14px}label{display:block;font-weight:600;margin-top:10px}input,textarea{width:100%;box-sizing:border-box;padding:9px;border:1px solid #b8c0cc;border-radius:7px}input[type=checkbox]{width:auto}button{padding:10px 16px;border:0;border-radius:8px;background:#1f6feb;color:white;font-weight:700;cursor:pointer;margin-top:12px}.muted{color:#5d6673;font-size:.92rem}.ok{background:#dafbe1;border:1px solid #4ac26b;padding:10px;border-radius:8px}.pill{display:inline-block;padding:3px 8px;border-radius:99px;background:#eef2f7;font-size:.8rem;margin-left:6px}
"""


def _provider_card(provider: ProviderSettings, secrets: SecretStore) -> str:
    fields = [
        f'<input type="hidden" name="provider_id" value="{html.escape(provider.id)}">',
        f'<label><input type="checkbox" name="enabled" value="1" {"checked" if provider.enabled else ""}> Enabled</label>',
        f'<label>Feed URL<input name="feed_url" value="{html.escape(provider.feed_url)}"></label>' if provider.kind == "rss" else "",
        f'<label>Base URL<input name="base_url" value="{html.escape(provider.base_url)}"></label>' if provider.base_url or provider.kind not in {"sam"} else "",
    ]
    for field_name in provider.credential_fields:
        configured = secrets.has(provider.id, field_name)
        fields.append(
            f'<label>{html.escape(field_name.replace("_", " ").title())} '
            f'<span class="pill">{"configured" if configured else "not set"}</span>'
            f'<input type="password" name="secret_{html.escape(field_name)}" value="" placeholder="Leave blank to keep current value"></label>'
        )
    fields.append('<button type="submit">Save provider</button>')
    return (
        '<form method="post" action="/settings/provider" class="provider">'
        f'<h3>{html.escape(provider.label)}</h3><div class="muted">{html.escape(provider.notes)}</div>'
        + "".join(fields)
        + '</form>'
    )


def render_settings(settings: AppSettings, secrets: SecretStore, saved: bool = False) -> str:
    cards = "".join(_provider_card(p, secrets) for p in settings.providers)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Auto Bid Builder Settings</title><style>{CSS}</style></head><body><main>
<h1>Auto Bid Builder</h1><p class="muted">Bid-source configuration. Public sources work without accounts. Credentials are stored outside Git using the OS credential store or ABB_* environment variables.</p>
{'<div class="ok">Settings saved.</div>' if saved else ''}
<div class="card"><h2>Opportunity search</h2><form method="post" action="/settings/general">
<label>Preferred states<input name="preferred_states" value="{html.escape(','.join(settings.preferred_states))}" placeholder="CA,NV"></label>
<label>Lookback days<input type="number" min="1" max="365" name="lookback_days" value="{settings.lookback_days}"></label>
<label>Minimum triage score<input type="number" step="1" name="minimum_score" value="{settings.minimum_score:g}"></label>
<button type="submit">Save search settings</button></form></div>
<div class="card"><h2>Bid outlets</h2><div class="grid">{cards}</div></div>
</main></body></html>"""


class SettingsHandler(BaseHTTPRequestHandler):
    secret_store = SecretStore()

    def _redirect(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/settings?saved=1")
        self.end_headers()

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8")
        parsed = urllib.parse.parse_qs(body, keep_blank_values=True)
        return {k: v[-1] for k, v in parsed.items()}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in {"/", "/settings"}:
            self.send_error(404)
            return
        settings = load_settings()
        body = render_settings(settings, self.secret_store, "saved=1" in parsed.query).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        form = self._form()
        settings = load_settings()
        if self.path == "/settings/general":
            settings.preferred_states = [x.strip().upper() for x in form.get("preferred_states", "").split(",") if x.strip()]
            settings.lookback_days = max(1, int(form.get("lookback_days", settings.lookback_days)))
            settings.minimum_score = float(form.get("minimum_score", settings.minimum_score))
            save_settings(settings)
            self._redirect(); return

        if self.path == "/settings/provider":
            provider_id = form.get("provider_id", "")
            provider = next((x for x in settings.providers if x.id == provider_id), None)
            if provider is None:
                self.send_error(400, "unknown provider"); return
            provider.enabled = form.get("enabled") == "1"
            if "feed_url" in form:
                provider.feed_url = form.get("feed_url", "").strip()
            if "base_url" in form:
                provider.base_url = form.get("base_url", "").strip()
            for field_name in provider.credential_fields:
                entered = form.get(f"secret_{field_name}", "").strip()
                if entered:
                    self.secret_store.set(provider.id, field_name, entered)
            save_settings(settings)
            self._redirect(); return

        self.send_error(404)


def run_settings_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), SettingsHandler)
    print(f"Auto Bid Builder settings: http://{host}:{port}/settings")
    server.serve_forever()
