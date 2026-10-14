"""Loads Vikram's starting spreadsheet (50 real investors) through the FOUNDER login.
Never overwrites a row that already exists (on conflict do nothing), so re-running is safe.
The investors, firms and theses are real (verified Oct 2026). Vikram, Vikram's startup and his contact notes are illustrative.
Usage: python3 -I tools/seed.py"""
import datetime as dt
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
for line in open(os.path.join(ROOT, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ.setdefault(k, v)
import _db  # noqa: E402

TODAY = dt.date(2026, 10, 11)
rng = random.Random(7)
vcs = json.load(open(os.path.join(ROOT, "data/vcs_research.json")))

INTROS = ["Warm intro via Rohan (IIT-B batchmate, now at Delhivery)", "Met at SaaSBoomi Annual, Chennai",
          "Cold email after their podcast", "Intro from our angel, Meera (ex-Rivigo)", "LinkedIn DM, they replied same day",
          "Intro via Ankit at Antler cohort demo day", "Met at TiE Mumbai logistics roundtable",
          "Intro from Shiprocket founder", "Applied via website form", "Twitter/X conversation about freight rates"]
MEETINGS = ["30-min Zoom with the partner. Asked about CAC payback and pilot-to-paid conversion.",
            "Coffee meeting. Liked the carrier network data; worried about SMB churn.",
            "First call with associate; partner meeting pending.",
            "Sent deck + data room. They asked for cohort retention by shipper size.",
            "Partner call went well; they want to see 2 more months of MRR growth.",
            "Associate call. Asked how we differ from FreightTiger and Fleetx."]
NOTES_WAIT = ["Promised to revert after their Monday partner meeting.", "Send Q3 MRR update when chasing.",
              "Partner is travelling till mid-Oct per auto-reply.", "Ask about their co-investor network for the round.",
              "They liked the ULIP integration - mention new API customers.", "Follow up with the Tata Steel pilot result.",
              "Sensitive: they backed a competitor in 2023 - be careful with roadmap details.",
              "Good chemistry with the partner; push for a 2nd meeting."]
NOTES_NEW = ["Need a warm intro - check who in our network knows them.", "Read their thesis post before reaching out.",
             "Stretch target: global logistics specialist.", "Maybe later for Series A rather than seed.",
             "Portfolio has two shipper-side companies - potential customers too.", "Ask Meera for an intro.",
             "Good fit on paper; cheque size might be large for seed.", ""]

rows = []
for i, v in enumerate(vcs):
    waiting = i % 5 in (0, 2) or v["name"] in ("Santosh Sankar", "Rajan Anandan")
    region = v["region"]
    if waiting:
        days = rng.choice([3, 5, 9, 12, 16, 19, 23, 28, 34, 41, 52, 63])
        last = TODAY - dt.timedelta(days=days)
        first = last - dt.timedelta(days=rng.choice([12, 20, 31, 44]))
        history = "%s: %s. %s: %s Followed up %s." % (
            first.strftime("%d %b"), rng.choice(INTROS), (first + dt.timedelta(days=6)).strftime("%d %b"),
            rng.choice(MEETINGS), last.strftime("%d %b"))
        notes = rng.choice(NOTES_WAIT)
        status = "waiting_response"
    else:
        last, history, status = None, "", "yet_to_reach_out"
        notes = rng.choice(NOTES_NEW)
    rows.append(("insert into vcs (name, firm, thesis, region, status, last_contact_date, contact_history, notes, feed_url) "
                 "values ($1,$2,$3,$4,$5,$6::date,$7,$8,$9) on conflict (name, firm) do nothing",
                 [v["name"], v["firm"], v["thesis"], region, status, last.isoformat() if last else None,
                  history, notes, v.get("feed")]))
_db.tx(rows, role="founder")
print(_db.q("select status, count(*) from vcs group by status", role="founder"))
