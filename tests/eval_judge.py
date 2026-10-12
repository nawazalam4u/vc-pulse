"""Accuracy check of the AI judge + code rules against hand labels (data/eval_gold.json, 58 real items).
Question 1 (attribution): is this item really about the investor or their firm acting?
Question 2 (topic): is it about logistics / supply chain?
Run: python3 -I tests/eval_judge.py   (needs GEMINI_API_KEY in .env; uses 2 Gemini calls)"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
for line in open(os.path.join(ROOT, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ.setdefault(k, v)
import _engine as e  # noqa: E402
import _gemini  # noqa: E402

gold = json.load(open(os.path.join(ROOT, "data/eval_gold.json")))
by_vc = {}
for g in gold:
    g["published"] = dt.date.fromisoformat(g["published"][:10])
    by_vc.setdefault(g["vc_id"], {"vc": {"id": g["vc_id"], "name": g["name"], "firm": g["firm"], "thesis": g["thesis"]},
                                  "items": []})["items"].append(g)
groups = list(by_vc.values())
verdicts = {}
for i in range(0, len(groups), 10):
    verdicts.update(e.judge([(x["vc"], x["items"]) for x in groups[i:i + 10]]))

tp = fp = fn = tn = 0
ltp = lfp = lfn = 0
mistakes = []
for x in groups:
    v = verdicts.get(x["vc"]["id"], {"items": {}})
    for i, it in enumerate(x["items"]):
        j = v["items"].get(i, {"actor": "no", "kind": "other", "relevance": 0})
        rel = e.verify_relevance(max(0, min(3, int(j.get("relevance") or 0))), it)
        pred = j["actor"] in ("person", "firm") and e.names_them(x["vc"], it, j.get("kind"))
        truth = bool(it["attribution"])
        tp += pred and truth; fp += pred and not truth; fn += (not pred) and truth; tn += (not pred) and not truth
        if pred != truth:
            mistakes.append("%s %s | %s | %s" % ("FALSE+" if pred else "MISSED", x["vc"]["name"], it["origin"], it["title"][:80]))
        if pred and truth:
            lp, lt = rel >= 3, bool(it["logistics"])
            ltp += lp and lt; lfp += lp and not lt; lfn += (not lp) and lt

prec = tp / max(1, tp + fp)
rec = tp / max(1, tp + fn)
res = {"items": len(gold), "model": _gemini.LAST["model"], "reasoning": _gemini.REASONING,
       "cost_usd": round(_gemini.COST["usd"], 5), "tokens": _gemini.COST["tokens"], "attribution": {
    "precision": round(prec, 3), "recall": round(rec, 3), "accuracy": round((tp + tn) / len(gold), 3),
    "tp": tp, "fp": fp, "fn": fn, "tn": tn},
    "logistics_label": {"precision": round(ltp / max(1, ltp + lfp), 3), "recall": round(ltp / max(1, ltp + lfn), 3)},
    "mistakes": mistakes, "date": str(dt.date.today())}
json.dump(res, open(os.path.join(ROOT, "data/eval_results.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "mistakes"}, indent=1))
print("\n".join(mistakes))
