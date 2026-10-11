"""/api/proof - shows, live, that Vikram's columns are protected by the database itself.
GET   what each login is allowed to update (read from Postgres' own permission tables)
POST  {id}  the "try to break it" test: the robot tries to overwrite a note, the edit screen tries to fake a score.
      Each attempt runs in a transaction that ends in a forced error, so even if a permission were ever missing,
      nothing could actually change. Safe to press any number of times."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lets Vercel find the _helper modules

from http.server import BaseHTTPRequestHandler

import _db
import _engine
import _http

PRIV = ("select column_name, privilege_type from information_schema.column_privileges "
        "where table_name = 'vcs' and grantee = current_user and privilege_type = 'UPDATE' order by column_name")


def attempt(role, sql, params):
    try:
        _db.tx([(sql, params), ("select 1 / 0", [])], role=role)
        return {"blocked": False, "message": "unexpected: statement ran"}
    except _db.DBError as e:
        msg = str(e)
        if "division by zero" in msg:
            return {"blocked": False, "message": "WARNING: permission not enforced (change was rolled back)"}
        return {"blocked": True, "message": msg}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            eng = [r["column_name"] for r in _db.q(PRIV, role="engine")]
            fou = [r["column_name"] for r in _db.q(PRIV, role="founder")]
        except _db.DBError as e:
            return _http.send(self, {"error": str(e)}, 500)
        _http.send(self, {"engine_can_update": eng, "founder_can_update": fou})

    def do_POST(self):
        b = _http.body(self)
        try:
            vid = int((b if isinstance(b, dict) else {}).get("id") or 0)
        except (TypeError, ValueError):
            vid = 0
        try:
            before = _db.q(_engine.FINGERPRINT)[0]
            vc = _db.q("select id, name, notes, follow_up_score from vcs where id = $1", [vid]) or \
                _db.q("select id, name, notes, follow_up_score from vcs order by id limit 1")
            vc = vc[0]
            tests = [
                {"who": "Signal robot (pulse_engine)", "tries": "overwrite Vikram's notes",
                 "sql": "update vcs set notes = 'overwritten by robot' where id = %d" % vc["id"],
                 **attempt("engine", "update vcs set notes = 'overwritten by robot' where id = $1", [vc["id"]])},
                {"who": "Signal robot (pulse_engine)", "tries": "rewrite his contact history",
                 "sql": "update vcs set contact_history = '' where id = %d" % vc["id"],
                 **attempt("engine", "update vcs set contact_history = '' where id = $1", [vc["id"]])},
                {"who": "Edit screen (pulse_founder)", "tries": "fake a follow-up score of 100",
                 "sql": "update vcs set follow_up_score = 100 where id = %d" % vc["id"],
                 **attempt("founder", "update vcs set follow_up_score = 100 where id = $1", [vc["id"]])},
            ]
            after = _db.q(_engine.FINGERPRINT)[0]
        except _db.DBError as e:
            return _http.send(self, {"error": str(e)}, 500)
        _http.send(self, {"vc": vc, "tests": tests, "fingerprint_before": before["h"], "fingerprint_after": after["h"],
                          "unchanged": before["h"] == after["h"]})

    def log_message(self, *a):
        pass
