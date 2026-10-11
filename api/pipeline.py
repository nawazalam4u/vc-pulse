"""GET /api/pipeline - Vikram's table + latest evidence + run history (read-only)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lets Vercel find the _helper modules

from http.server import BaseHTTPRequestHandler

import _http
import _db


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # one round trip to the database: all five reads in a single transaction
            vcs, sig, runs, changes, cnt = _db.tx([
                ("select * from vcs order by follow_up_score desc nulls last, name", []),
                ("select id, vc_id, url, title, source, origin, published, kind, relevance, summary, points "
                 "from signals where about_vc and points >= 4 and published >= current_date - 30 order by points desc", []),
                ("select id, trigger, started_at, finished_at, status, vcs_total, vcs_done, items_scanned, signals_kept, "
                 "hot_count, quiet_count, errors, notes_hash_before, notes_hash_after, sources from runs order by id desc limit 12", []),
                ("select vc_id, old_score, new_score, old_action, new_action from vc_changes "
                 "where run_id = (select max(id) from runs where status = 'done')", []),
                ("select count(*) as n from signals", [])])
            scanned = cnt[0]["n"]
        except _db.DBError as e:
            return _http.send(self, {"error": str(e)}, 500)
        by_vc = {}
        for s in sig:
            by_vc.setdefault(s["vc_id"], []).append(s)
        for v in vcs:
            v["signals"] = by_vc.get(v["id"], [])[:6]
        _http.send(self, {"vcs": vcs, "runs": runs, "changes": changes, "items_total": scanned,
                          "can_edit": _http.has_key(self)})

    def log_message(self, *a):
        pass
