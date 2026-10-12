"""/api/pitch - Vikram's pitch facts (one-liner, traction, ask), used by email drafts so they never invent anything.
GET   read (public, it's his pitch)          POST {fields} save (needs Vikram's key; FOUNDER login)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lets Vercel find the _helper modules
from http.server import BaseHTTPRequestHandler

import _db
import _http

FIELDS = {"one_liner": 220, "traction": 220, "ask": 160}


def load(role="engine"):
    try:
        return {r["key"]: r["value"] for r in _db.q("select key, value from founder_profile", role=role)}
    except _db.DBError:
        return {}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        _http.send(self, {"profile": load(), "can_edit": _http.has_key(self)})

    def do_POST(self):
        if not _http.has_key(self):
            return _http.send(self, {"error": "Saving your pitch needs Vikram's key."}, 401)
        b = _http.body(self)
        fields = (b if isinstance(b, dict) else {}).get("fields") or {}
        stmts = [("insert into founder_profile (key, value) values ($1, $2) on conflict (key) do update set value = excluded.value",
                  [k, str(fields[k]).strip()[:n]]) for k, n in FIELDS.items() if k in fields]
        try:
            _db.tx(stmts, role="founder")
        except _db.DBError as e:
            return _http.send(self, {"error": str(e)}, 400)
        _http.send(self, {"ok": True, "profile": load()})

    def log_message(self, *a):
        pass
