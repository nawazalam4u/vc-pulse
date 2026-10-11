"""POST /api/draft {id} - Gemini Flash drafts Vikram's opener from the evidence. A draft only: nothing is sent,
and nothing is written to his table. He edits and sends it himself (the human stays in charge of the relationship)."""
from http.server import BaseHTTPRequestHandler

import _db
import _engine
import _gemini
import _http


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            vid = int(_http.body(self).get("id") or 0)
            vc = _db.q("select * from vcs where id = $1", [vid])[0]
            sig = _db.q("select title, source, published, kind, summary, url from signals where vc_id = $1 and about_vc "
                        "and points >= 4 and published >= current_date - 30 order by points desc limit 3", [vid])
        except (ValueError, IndexError, _db.DBError):
            return _http.send(self, {"error": "investor not found"}, 404)
        if not sig:
            return _http.send(self, {"error": "No fresh signal for this investor, so there is no honest hook to write "
                                              "about. That is the point: park them for now."}, 409)
        waiting = vc["status"] == "waiting_response"
        ev = "\n".join("- %s (%s, %s): %s" % (s["title"], s["source"], s["published"], s["summary"] or "") for s in sig)
        prompt = ("Write a short email from Vikram, founder of %s, to %s (%s).\n%s\n"
                  "Their recent public activity (use ONLY this, cite the first item naturally in the first line):\n%s\n"
                  "Vikram's own context (private, may inform tone; never quote it): status=%s; history=%s; notes=%s\n"
                  "Rules: under 110 words, plain and specific, no flattery clichés, no invented metrics or names, "
                  "one clear ask (a 20-minute call). Output: 'Subject: ...' line, blank line, body, sign-off 'Vikram'."
                  % (_engine.COMPANY, vc["name"], vc["firm"],
                     "This is a polite follow-up: Vikram already pitched them and is waiting for a reply." if waiting
                     else "This is a first-touch email.", ev, vc["status"], vc["contact_history"] or "-", vc["notes"] or "-"))
        try:
            text, _ = _gemini.generate(prompt, temperature=0.6, timeout=50)
        except Exception as e:
            return _http.send(self, {"error": "Gemini is busy, try again in a minute (%s)" % str(e)[:80]}, 503)
        _http.send(self, {"draft": text.strip(), "model": _gemini.LAST["model"], "based_on": sig})

    def log_message(self, *a):
        pass
