"""GET /api/cron - Vercel Cron calls this Monday and Thursday at 07:00 IST (vercel.json).
Refreshes all 50 investors in one go, then (optionally) sends Vikram the brief on Telegram."""
from http.server import BaseHTTPRequestHandler

import _http
import _engine
import _notify


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _http.is_cron(self):
            return _http.send(self, {"error": "only Vercel Cron may call this"}, 401)
        try:
            res = _engine.run_all("cron")
            res["telegram"] = _notify.send_brief(res.get("run_id"))
            res.pop("report", None)
            _http.send(self, res)
        except Exception as e:
            _http.send(self, {"error": str(e)[:300]}, 500)

    def log_message(self, *a):
        pass
