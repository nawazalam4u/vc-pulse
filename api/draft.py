"""POST /api/draft {id} - Gemini Flash drafts Vikram's opener from the evidence. A draft only: nothing is sent,
and nothing is written to his table. He edits and sends it himself (the human stays in charge of the relationship)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lets Vercel find the _helper modules

from http.server import BaseHTTPRequestHandler

import _db
import _engine
import _gemini
import _http
import pitch as _profile


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            b = _http.body(self)
            vid = int((b if isinstance(b, dict) else {}).get("id") or 0)
            vc = _db.q("select * from vcs where id = $1", [vid])[0]
            sig = _db.q("select title, source, published, kind, summary, url from signals where vc_id = $1 and about_vc "
                        "and not coalesce(dup, false) and points >= 4 and published >= current_date - 30 order by points desc limit 3", [vid])
        except (TypeError, ValueError, IndexError, _db.DBError):
            return _http.send(self, {"error": "investor not found"}, 404)
        editor = _http.has_key(self)
        if not editor and int(_db.q("select count(*) as n from drafts where not editor and created_at > now() - interval '1 hour'")[0]["n"]) >= 30:
            return _http.send(self, {"error": "Demo limit: 30 AI drafts an hour for visitors (keeps the free Gemini quota "
                                              "for the twice-weekly runs). Try again later."}, 429)
        if not sig:
            return _http.send(self, {"error": "No fresh signal for this investor, so there is no honest hook to write "
                                              "about. That is the point: park them for now."}, 409)
        waiting = vc["status"] == "waiting_response"
        lead = (vc.get("recommended_action") or "").split(" · ", 1)[-1]
        lead = re.sub(r"^(This week\.|If you have bandwidth this week\.|Active and a good fit, but no logistics hook yet, so not a cold-email moment\.)\s*", "", lead)
        why = (vc.get("signal_summary") or "").split("Why it matters for Haulr: ")[-1] if "Why it matters" in (vc.get("signal_summary") or "") else ""
        ev = "\n".join("- %s (%s, %s): %s" % (s["title"], s["source"], s["published"], s["summary"] or "") for s in sig)
        pf = _profile.load()
        company = pf.get("one_liner") or _engine.COMPANY
        traction = pf.get("traction", "").strip()
        ask = pf.get("ask", "").strip() or "a 20-minute call"
        prompt = ("Write a short email from Vikram, founder of %s, to %s (%s).\n%s\n"
                  "Open with this exact signal (the strongest one): %s\nWhy it matters (our analysis; use it, don't overclaim): %s\n"
                  "Other public activity (background only, use ONLY these facts):\n%s\n"
                  "Vikram's own context (private, may inform tone; never quote it): status=%s; history=%s; notes=%s\n"
                  "Rules: under 110 words, plain and specific, no flattery clichés, no claims about the investor's portfolio or "
                  "strategy beyond the facts above. Never argue 'you invested in X, so you'll like "
                  "us'; connect their specific signal to Haulr honestly (a complement, their stated thesis, or their active "
                  "early-stage investing). NEVER invent facts about Haulr: no traction, "
                  "customers, growth, revenue or stage claims; instead write the placeholder [your one-line traction here] "
                  "for Vikram to fill in. Don't repeat his private notes word for word. One clear ask. "
                  "Also write linkedin_note: a LinkedIn connection note under 280 characters that cites the same signal, "
                  "no links, no traction claims beyond the facts given, signed 'Vikram'. The body ends with the sign-off 'Vikram'.\n%s\nThe ask: %s."
                  % (company, vc["name"], vc["firm"],
                     "This is a polite follow-up: Vikram already pitched them and is waiting for a reply." if waiting
                     else "This is a first-touch email.", lead[:300], why[:400], ev, vc["status"], vc["contact_history"] or "-", vc["notes"] or "-",
                     ("Traction (Vikram's own words, use exactly as written instead of the placeholder): " + traction)
                     if traction else "No traction line given: use the placeholder [your one-line traction here].", ask))
        if traction:
            prompt = prompt.replace("instead write the placeholder [your one-line traction here] for Vikram to fill in",
                                    "use only Vikram's own traction line given below")
        try:
            # drafts use the Lite models first, saving the main model's small free daily quota for judging
            out = _gemini.generate_json(prompt, {"type": "OBJECT", "properties": {
                "subject": {"type": "STRING"}, "body": {"type": "STRING"}, "linkedin_note": {"type": "STRING"}},
                "required": ["subject", "body", "linkedin_note"]}, temperature=0.6, timeout=50, models=_gemini.DRAFT_MODELS)
            text = "Subject: %s\n\n%s" % (out.get("subject", "").strip(), out.get("body", "").strip())
            note = out.get("linkedin_note", "").strip()[:300]
        except Exception as e:
            return _http.send(self, {"error": "Gemini is busy, try again in a minute (%s)" % str(e)[:80]}, 503)
        try:
            _db.q("insert into drafts (vc_id, model, editor) values ($1, $2, $3)", [vid, _gemini.LAST["model"], editor])
        except _db.DBError:
            pass
        _http.send(self, {"draft": text.strip(), "subject": out.get("subject", "").strip(), "body": out.get("body", "").strip(),
                          "linkedin_note": note, "model": _gemini.LAST["model"], "based_on": sig})

    def log_message(self, *a):
        pass
