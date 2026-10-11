"""POST /api/run  {"action": "start" | "batch" | "finish", "run": id, "ids": [...]}
The browser drives a run in small batches so Vikram sees live progress (each call stays well under Vercel's limit).
Anyone may start a run if the last one finished 10+ minutes ago; with Vikram's key, any time."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lets Vercel find the _helper modules

from http.server import BaseHTTPRequestHandler

import _http
import _db
import _engine
import _gemini
import json


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        b = _http.body(self)
        act = b.get("action")
        try:
            if act == "start":
                if not _http.has_key(self):
                    recent = _db.q("select id from runs where status = 'done' and finished_at > now() - interval '10 minutes' "
                                   "limit 1")
                    if recent:
                        return _http.send(self, {"error": "The pipeline was refreshed less than 10 minutes ago. "
                                                          "Signals don't change that fast, so the table is already current."}, 429)
                rid, fresh = _engine.start_run("manual")
                ids = [r["id"] for r in _db.q("select id from vcs order by id")] if fresh else []
                names = {r["id"]: r["name"] for r in _db.q("select id, name from vcs")}
                return _http.send(self, {"run": rid, "fresh": fresh, "ids": ids, "names": names})
            rid = int(b.get("run") or 0)
            run = _db.q("select id, status from runs where id = $1", [rid])
            if not run or run[0]["status"] != "running":
                return _http.send(self, {"error": "run is not active"}, 409)
            if act == "batch":
                ids = [int(x) for x in (b.get("ids") or [])][:10]
                rep = _engine.process(rid, ids, workers=10, judge_size=10)
                _db.q("update runs set sources = coalesce(sources, '{}'::jsonb) || $2::jsonb where id = $1",
                      [rid, json.dumps({"models_used_batch_%d" % ids[0]: _gemini.USED})]) if ids else None
                return _http.send(self, {"report": rep})
            if act == "finish":
                return _http.send(self, {"run": _engine.finish_run(rid)})
        except _db.DBError as e:
            return _http.send(self, {"error": "database: %s" % e}, 500)
        except Exception as e:
            return _http.send(self, {"error": str(e)[:300]}, 500)
        _http.send(self, {"error": "unknown action"}, 400)

    def log_message(self, *a):
        pass
