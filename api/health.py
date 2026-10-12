"""GET /api/health - which parts are switched on (never prints secrets)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lets Vercel find the _helper modules
from http.server import BaseHTTPRequestHandler

import _db
import _gemini
import _http
import _notify
import _sources


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        out = {"ok": True, "version": os.environ.get("VERCEL_GIT_COMMIT_SHA", "local")[:7], "gemini": _gemini.configured(), "gateway": "OpenRouter -> Google (google-vertex / google-ai-studio only)", "models": _gemini.MODELS,
               "database": {r: _db.configured(r) for r in ("engine", "founder")},
               "owner_login_on_server": bool(os.environ.get("DATABASE_URL")),
               "cron_secret": bool(os.environ.get("CRON_SECRET")), "editor_key": bool(os.environ.get("DASHBOARD_KEY")),
               "telegram": _notify.configured(), "window_days": _sources.WINDOW}
        if "probe=1" in self.path and _http.has_key(self):  # the live AI test costs quota: editor only
            try:
                out["db_rows"] = _db.q("select count(*) as n from vcs")[0]["n"]
                txt, _ = _gemini.generate("Reply with exactly: OK", timeout=30)
                out["gemini_probe"] = txt.strip()[:10]
                out["gemini_model"] = _gemini.LAST["model"]
            except Exception as e:
                out["probe_error"] = str(e)[:200]
        _http.send(self, out)

    def log_message(self, *a):
        pass
