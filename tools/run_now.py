"""Runs a full refresh on the live site exactly like the browser's "Refresh now" (needs DASHBOARD_KEY in .env).
Usage: python3 -I tools/run_now.py [base_url]"""
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dict(l.rstrip("\n").split("=", 1) for l in open(os.path.join(ROOT, ".env")) if "=" in l and not l.startswith("#"))
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://vc-pulse-lime.vercel.app").rstrip("/") + "/api/run"


def post(d):
    req = urllib.request.Request(BASE, data=json.dumps(d).encode(),
                                 headers={"content-type": "application/json", "x-pulse-key": env["DASHBOARD_KEY"]})
    return json.load(urllib.request.urlopen(req, timeout=300))


t = time.time()
s = post({"action": "start"})
ids = s["ids"]
print("run", s["run"], "investors", len(ids))
with ThreadPoolExecutor(3) as ex:
    list(ex.map(lambda b: post({"action": "batch", "run": s["run"], "ids": b}), [ids[i:i + 10] for i in range(0, len(ids), 10)]))
f = post({"action": "finish", "run": s["run"]})["run"]
print("%ds | done %s | items %s | signals %s | reach out %s | quiet %s | errors %s | notes untouched: %s | %s" % (
    time.time() - t, f["vcs_done"], f["items_scanned"], f["signals_kept"], f["hot_count"], f["quiet_count"], f["errors"],
    f["notes_hash_before"] == f["notes_hash_after"], (f.get("sources") or {}).get("models_used")))
