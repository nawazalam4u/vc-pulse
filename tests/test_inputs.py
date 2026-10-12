"""What Vikram (or a CSV) may put into his own columns. Offline. Run: python3 -I tests/test_inputs.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
import vc  # noqa: E402

checks = [
    ("a real LinkedIn profile link is kept", vc.clean({"linkedin_url": "https://www.linkedin.com/in/rajan-anandan/"})["linkedin_url"]),
    ("a regional LinkedIn link is kept", vc.clean({"linkedin_url": "https://in.linkedin.com/in/sajithpai"})["linkedin_url"]),
    ("javascript: links are rejected", vc.clean({"linkedin_url": "javascript:alert(1)"})["linkedin_url"] is None),
    ("look-alike domains are rejected", vc.clean({"linkedin_url": "https://linkedin.com.evil.io/in/x"})["linkedin_url"] is None),
    ("company pages are rejected (people only)", vc.clean({"linkedin_url": "https://www.linkedin.com/company/peak-xv"})["linkedin_url"] is None),
    ("'Waiting for response' becomes waiting_response", vc.clean({"status": "Waiting for response"})["status"] == "waiting_response"),
    ("Indian date 07/09/2026 becomes 2026-09-07", vc.clean({"last_contact_date": "07/09/2026"})["last_contact_date"] == "2026-09-07"),
    ("signal columns can't be smuggled in", "follow_up_score" not in vc.clean({"name": "A", "firm": "B", "follow_up_score": 99})),
    ("CSV headers are case/space tolerant", vc.clean({"Last Contact Date": "2026-09-01"})["last_contact_date"] == "2026-09-01"),
]
for n, ok in checks:
    print("PASS" if ok else "FAIL", "-", n)
print("%d/%d passed" % (sum(bool(ok) for _, ok in checks), len(checks)))
sys.exit(0 if all(ok for _, ok in checks) else 1)
