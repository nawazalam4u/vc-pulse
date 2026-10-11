"""Scoring rules are plain code, so they can be tested without internet or AI. Run: python3 -I tests/test_scoring.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
import _engine as e  # noqa: E402

T = dt.date(2026, 10, 11)
LOGI = {"thesis": "Seed B2B supply chain and logistics software", "status": "yet_to_reach_out", "last_contact_date": None}
GEN = {"thesis": "Consumer brands", "status": "yet_to_reach_out", "last_contact_date": None}


def sig(kind, rel, days, actor="person"):
    return {"points": e.KIND_W[kind] * e.REL_M[rel] * e.ACTOR_M[actor] * e.recency(days)}


def act(vc, signals, hook="Saw your post"):
    total, bd, strength, days = e.score(vc, signals, T)
    return total, e.action_for(vc, total, strength, days, hook, None, T, None)


checks = []
def check(name, cond):
    checks.append((name, cond))

t, a = act(LOGI, [sig("invested", 3, 2)])
check("fresh logistics deal + logistics thesis + not contacted -> REACH OUT", a.startswith("REACH OUT") and t >= 55)
t, a = act(LOGI, [])
check("no signal -> PARK, and mentions strong thesis fit", a.startswith("PARK") and "thesis fit" in a)
t, a = act(dict(LOGI, status="waiting_response", last_contact_date="2026-10-08"), [sig("invested", 3, 1)])
check("followed up 3 days ago -> WAIT even with a hot signal", a.startswith("WAIT") and "Hook ready" in a)
t, a = act(dict(LOGI, status="waiting_response", last_contact_date="2026-09-01"), [sig("wrote", 3, 3)])
check("waiting 40 days + fresh on-topic post -> NUDGE", a.startswith("NUDGE"))
t, a = act(GEN, [sig("mentioned", 1, 20, "firm")])
check("weak, off-topic firm mention -> LOW or PARK, score < 35", t < 35 and (a.startswith("LOW") or a.startswith("PARK")))
check("freshness: day 1 worth more than day 25", e.recency(1) > e.recency(25) >= 0.4)
check("same evidence -> same score (deterministic)", e.score(LOGI, [sig("said", 2, 5)], T)[0] == e.score(LOGI, [sig("said", 2, 5)], T)[0])
check("score is always within 0-100", all(0 <= e.score(v, s, T)[0] <= 100 for v in (LOGI, GEN, dict(LOGI, status="waiting_response", last_contact_date="2026-10-10"))
                                          for s in ([], [sig("invested", 3, 0)] * 5)))
check("next run after Sunday 11 Oct is Monday 12 Oct", e.next_run_day(T) == dt.date(2026, 10, 12))

check("AI says logistics but text has no logistics word -> capped at 2",
      e.verify_relevance(3, {"title": "Fifth Wall's partner on spotting real estate's next hot tech"}) == 2)
check("AI says logistics and the text agrees -> stays 3",
      e.verify_relevance(3, {"title": "Dynamo leads seed in a freight visibility startup"}) == 3)

V = {"name": "Rahul Chowdhri", "firm": "Stellaris Venture Partners"}
check("deal headline without the firm's name or logistics -> not a signal",
      not e.names_them(V, {"origin": "firm_news", "title": "Lumio maker Circuit House raises $12M Series A"}, "invested"))
check("logistics deal found by the firm search -> signal",
      e.names_them(V, {"origin": "firm_news", "title": "Gallatin raises $50M to digitize military logistics"}, "invested"))
check("firm named in a deal headline -> signal",
      e.names_them(V, {"origin": "firm_news", "title": "Stellaris leads seed in SaaS startup"}, "invested"))
check("person news must name them", not e.names_them(V, {"origin": "news", "title": "Weekly funding roundup"}, "said")
      and e.names_them(V, {"origin": "news", "title": "Rahul Chowdhri on B2B SaaS"}, "said"))
check("firm aliases parse brackets", e.firm_aliases("Andreessen Horowitz (a16z)") == ["andreessen horowitz", "a16z"]
      and e.firm_aliases("Z47 (formerly Matrix Partners India)") == ["z47"])

t, a = act(dict(LOGI, status="waiting_response", last_contact_date="2026-10-02"), [sig("invested", 3, 1)] * 3)
check("followed up 9 days ago + hot signal -> WAIT (no 'nudge this week' contradiction)", a.startswith("WAIT"))
t, a = act(dict(LOGI, status="waiting_response", last_contact_date="2026-10-20"), [])
check("future last-contact date is treated as today, never 'followed up -9 days ago'", "-" not in a.split("·")[1][:40])
B = {"name": "Sajith Pai", "firm": "Blume Ventures"}
check("'quick delivery' deal not naming the firm -> not a logistics signal",
      not e.names_them(B, {"origin": "firm_news", "title": "Zepto raises $450M to speed up quick delivery"}, "invested"))
check("quiet + waiting 60 days -> PARK says don't chase / move on",
      "move on" in act(dict(GEN, status="waiting_response", last_contact_date="2026-08-12"), [])[1])

H = e.fallback_hook({"firm": "Andreessen Horowitz (a16z)"}, [
    {"actor": "firm", "points": 20, "kind": "wrote", "title": "Investing in TypeSafe AI", "published": T},
    {"actor": "person", "points": 5, "kind": "wrote", "title": "My own post", "published": T}])
check("fallback hook prefers the partner's own act and only says 'your' for it", H.startswith('Saw your post "My own post"'))
check("fallback hook for a firm act names the firm, not 'your'",
      e.fallback_hook({"firm": "Point Nine"}, [{"actor": "firm", "points": 9, "kind": "invested", "title": "Procuros raises EUR 20M",
                                                "published": T}]).startswith("Saw Point Nine's deal coverage"))

for n, ok in checks:
    print("PASS" if ok else "FAIL", "-", n)
print("%d/%d passed" % (sum(ok for _, ok in checks), len(checks)))
sys.exit(0 if all(ok for _, ok in checks) else 1)
