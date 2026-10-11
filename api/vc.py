"""/api/vc
GET    ?id=N          one investor: all evidence (kept AND rejected), score breakdown, score history
PATCH  {id, fields}   Vikram edits his own columns            (needs key; FOUNDER login)
POST   {rows: [...]}  add investors / import his spreadsheet  (needs key; FOUNDER login)
DELETE ?id=N          remove an investor                       (needs key; FOUNDER login)"""
from http.server import BaseHTTPRequestHandler

import _db
import _engine
import _http
import _sources

FOUNDER_FIELDS = ["name", "firm", "thesis", "region", "status", "last_contact_date", "contact_history", "notes", "feed_url"]


def clean(row):
    out = {}
    for f in FOUNDER_FIELDS:
        if f in row:
            v = row[f]
            v = None if v in ("", None) else str(v).strip()[:2000]
            if f == "status" and v not in ("yet_to_reach_out", "waiting_response"):
                v = "yet_to_reach_out"
            out[f] = v
    return out


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            vid = int(_http.query(self).get("id", 0))
            vc = _db.q("select * from vcs where id = $1", [vid])
            if not vc:
                return _http.send(self, {"error": "not found"}, 404)
            vc = vc[0]
            sig = _db.q("select * from signals where vc_id = $1 order by published desc, points desc limit 60", [vid])
            hist = _db.q("select c.run_id, r.started_at, r.trigger, c.old_score, c.new_score, c.new_action from vc_changes c "
                         "join runs r on r.id = c.run_id where c.vc_id = $1 order by c.run_id desc limit 12", [vid])
        except (ValueError, _db.DBError) as e:
            return _http.send(self, {"error": str(e)}, 400)
        today = _sources.today()
        live = [s for s in sig if s["about_vc"] and float(s["points"] or 0) >= 4 and s["published"] >= _sources.cutoff().isoformat()]
        for s in live:
            s["points"] = float(s["points"])
        total, breakdown, strength, days = _engine.score(vc, live, today)
        _http.send(self, {"vc": vc, "signals": sig, "breakdown": breakdown, "score_now": total, "history": hist,
                          "weights": {"kind": _engine.KIND_W, "relevance": _engine.REL_M, "actor": _engine.ACTOR_M}})

    def do_PATCH(self):
        if not _http.has_key(self):
            return _http.send(self, {"error": "Editing needs Vikram's key (open the magic link once)."}, 401)
        b = _http.body(self)
        fields = clean(b.get("fields") or {})
        if not fields:
            return _http.send(self, {"error": "nothing to change"}, 400)
        sets = ", ".join("%s = $%d%s" % (f, i + 2, "::date" if f == "last_contact_date" else "") for i, f in enumerate(fields))
        try:
            _db.q("update vcs set %s where id = $1" % sets, [int(b.get("id"))] + list(fields.values()), role="founder")
        except _db.DBError as e:
            return _http.send(self, {"error": str(e)}, 400)
        _http.send(self, {"ok": True, "saved": list(fields)})

    def do_POST(self):
        if not _http.has_key(self):
            return _http.send(self, {"error": "Adding investors needs Vikram's key."}, 401)
        rows = [clean(r) for r in (_http.body(self).get("rows") or [])][:200]
        rows = [r for r in rows if r.get("name") and r.get("firm")]
        stmts = []
        for r in rows:
            cols = [f for f in FOUNDER_FIELDS if f in r]
            stmts.append(("insert into vcs (%s) values (%s) on conflict (name, firm) do nothing" % (
                ", ".join(cols), ", ".join("$%d%s" % (i + 1, "::date" if c == "last_contact_date" else "")
                                           for i, c in enumerate(cols))), [r[c] for c in cols]))
        try:
            _db.tx(stmts, role="founder")
        except _db.DBError as e:
            return _http.send(self, {"error": str(e)}, 400)
        _http.send(self, {"ok": True, "added": len(stmts)})

    def do_DELETE(self):
        if not _http.has_key(self):
            return _http.send(self, {"error": "Removing investors needs Vikram's key."}, 401)
        try:
            _db.q("delete from vcs where id = $1", [int(_http.query(self).get("id", 0))], role="founder")
        except (ValueError, _db.DBError) as e:
            return _http.send(self, {"error": str(e)}, 400)
        _http.send(self, {"ok": True})

    def log_message(self, *a):
        pass
