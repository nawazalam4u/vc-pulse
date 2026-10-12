"""Live database test: the engine login cannot touch Vikram's columns, the founder login cannot touch signal columns.
Needs ENGINE_DATABASE_URL and FOUNDER_DATABASE_URL in .env. Run: python3 -I tests/test_guard.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
for line in open(os.path.join(ROOT, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ.setdefault(k, v)
import _db  # noqa: E402

VIKRAM = ["name", "firm", "thesis", "region", "status", "last_contact_date", "contact_history", "notes", "feed_url",
          "linkedin_url"]
SIGNAL = ["last_signal_date", "signal_summary", "follow_up_score", "recommended_action"]
VAL = {"status": "'waiting_response'", "last_contact_date": "current_date", "follow_up_score": "1", "last_signal_date": "current_date"}
vid = _db.q("select min(id) as id from vcs")[0]["id"]
fails = 0


def try_update(role, col):
    try:  # forced rollback (1/0) so nothing ever changes, even if a permission were missing
        _db.tx([("update vcs set %s = %s where id = $1" % (col, VAL.get(col, "'x'")), [vid]), ("select 1/0", [])], role=role)
    except _db.DBError as e:
        return "division by zero" in str(e)  # True = the update itself was allowed
    return True


for role, allowed in (("engine", SIGNAL), ("founder", VIKRAM)):
    for col in VIKRAM + SIGNAL:
        ok = try_update(role, col) == (col in allowed)
        fails += not ok
        print("PASS" if ok else "FAIL", "-", role, "update", col, "->", "allowed" if col in allowed else "blocked")
print("all permissions correct" if not fails else "%d permission problems" % fails)
sys.exit(1 if fails else 0)
