"""The signal engine: gather -> judge (Gemini Flash) -> score (code) -> write the 4 signal columns.

Who decides what:
  * Sources decide WHAT happened and WHEN (every signal has a link and a publish date from the source).
  * Gemini Flash decides WHAT IT MEANS: is it really this VC? what kind of act? how close to logistics?
  * Code decides the SCORE and the ACTION, with fixed, explainable rules (see score()).
  * The database decides WHAT MAY BE WRITTEN: the engine login can only touch the 4 signal columns.
"""
import datetime as dt
import json
import re
from concurrent.futures import ThreadPoolExecutor

import _db
import _gemini
import _sources

COMPANY = ("Haulr, a seed-stage B2B logistics SaaS from India (freight visibility, carrier management and "
           "dispatch software for mid-market shippers)")

KIND_W = {"invested": 40, "wrote": 34, "said": 30, "appeared": 26, "mentioned": 14, "other": 6}
REL_M = {3: 1.0, 2: 0.6, 1: 0.3, 0: 0.0}
ACTOR_M = {"person": 1.0, "firm": 0.7}
KIND_VERB = {"invested": "invested", "wrote": "wrote", "said": "spoke", "appeared": "appeared at an event",
             "mentioned": "was in the news"}

VIKRAM_COLS = "id, name, firm, thesis, region, status, last_contact_date, contact_history, notes, feed_url"
FINGERPRINT = ("select md5(coalesce(string_agg(concat_ws('|', %s), '~' order by id), '')) as h, count(*) as n from vcs"
               % VIKRAM_COLS)

JUDGE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "vc": {"type": "INTEGER"},
            "items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "i": {"type": "INTEGER"},
                "actor": {"type": "STRING", "enum": ["person", "firm", "no"]},
                "kind": {"type": "STRING", "enum": ["invested", "wrote", "said", "appeared", "mentioned", "other"]},
                "relevance": {"type": "INTEGER"},
                "event": {"type": "STRING"},
                "summary": {"type": "STRING"}},
                "required": ["i", "actor", "kind", "relevance", "event", "summary"]}},
            "overall": {"type": "STRING"},
            "hook": {"type": "STRING"}},
        "required": ["vc", "items", "overall", "hook"]}}

JUDGE_SYSTEM = """You are the research analyst for a founder raising a Seed round. His company: %s.
For each investor you get a numbered list of public items (headline, source, date) found in the last 30 days.
Judge every item using ONLY the text given. Never add facts, names, numbers or dates that are not in the item.

actor:  "person" if the investor named is the one who acted (wrote it, was interviewed or quoted, spoke, led the deal);
        "firm" if their firm acted (the firm invested, published, hosted) but the person is not named. Each item says
        how it was found: a funding-round headline "found by searching the firm's exact name" means the firm is named
        in that article about the round, so treat it as actor "firm", kind "invested" (all articles about that round
        alike), unless the headline itself credits other investors only;
        "no" if it is about someone else (a different person with the same name, a company merely in the same story,
        a deal by another investor, generic market news).
kind:   invested (new investment / led a round) | wrote (post, article, op-ed, newsletter) | said (interview, podcast,
        quote) | appeared (spoke at / attended an event, panel, demo day) | mentioned (in the news, no clear act) | other
relevance to the founder's space, 0-3 (be strict, judge only what the text says):
        3 = the item itself explicitly mentions logistics, freight, trucking, shipping, warehousing, supply chain,
            fleet or transport operations;
        2 = adjacent but not explicit: industrial / physical-economy tech, manufacturing, B2B SaaS, vertical software,
            commerce or SMB infrastructure, AI for operations;
        1 = general startup, venture, fundraising or India-ecosystem activity; real estate; fintech; climate;
        0 = unrelated (consumer brands, public-market share sales, personal news).
event:  short kebab-case id of the real-world event behind the item, identical for every article covering the same
        event, e.g. "8vc-gallatin-series-a", "anandan-liftoff-nation-book", "tunguz-post-ai-commoditization".
summary: <= 18 words, plain fact, e.g. "Led Rs 40 Cr Series A in FreightTiger, a trucking SaaS".
overall: <= 35 words: what this investor has been doing in the last 30 days that matters for the founder, citing
        dates like "8 Oct". Only use items with actor person/firm. If nothing qualifies, return "".
hook:   <= 22 words, written to THIS investor about THEIR OWN act (an item with actor person/firm): the specific,
        honest opening line for the founder's email, e.g. "Saw Peak XV raise Surge checks to $5M on 29 Sep...".
        Never mention other people. Return "" if nothing qualifies.""" % COMPANY


def _iso(d):
    return d.isoformat() if isinstance(d, (dt.date, dt.datetime)) else d


def _d(v):
    if v is None or isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v)[:10])


def short_date(d):
    d = _d(d)
    return "%d %s" % (d.day, d.strftime("%b")) if d else ""


# ---------------------------------------------------------------- judging (Gemini)

def judge(batch):
    """batch: [(vc, items)] -> {vc_id: {"items": {i: verdict}, "overall", "hook"}}"""
    blocks = []
    for vc, items in batch:
        if not items:
            continue
        how = {"news": "found by searching the person's exact name",
               "firm_news": "found by searching the firm's exact name + logistics words, so the firm IS named in the article",
               "blog": "from their own blog feed", "podcast": "podcast episode that mentions them",
               "search": "from Google Search"}
        lines = ["- [%d] %s | %s | %s | %s%s" % (i, it["title"], it["source"], _iso(it["published"]), how.get(it["origin"], ""),
                                                  (" | " + it["snippet"][:160]) if it.get("snippet") else "")
                 for i, it in enumerate(items)]
        blocks.append("INVESTOR vc=%d: %s (%s). Thesis: %s\n%s" % (vc["id"], vc["name"], vc["firm"],
                                                                   vc.get("thesis") or "-", "\n".join(lines)))
    if not blocks:
        return {}
    out = _gemini.generate_json("\n\n".join(blocks), JUDGE_SCHEMA, system=JUDGE_SYSTEM, temperature=0.1, timeout=90)
    res = {}
    for row in out if isinstance(out, list) else []:
        try:
            res[int(row["vc"])] = {"items": {int(x["i"]): x for x in row.get("items", [])},
                                   "overall": (row.get("overall") or "").strip(),
                                   "hook": (row.get("hook") or "").strip()}
        except (KeyError, TypeError, ValueError):
            continue
    return res


# ---------------------------------------------------------------- scoring (code, explainable)

LOGISTICS_WORDS = re.compile(r"logistic|freight|supply.?chain|truck|shipping|shipper|warehous|fleet|cargo|courier|"
                             r"last.?mile|transport|3pl|carrier|dispatch|port\b|ports\b|mobility|delivery", re.I)


def verify_relevance(rel, item):
    """Code checks the AI: a 'logistics' (3) rating needs a logistics word in the source text itself."""
    if rel >= 3 and not LOGISTICS_WORDS.search(item.get("title", "") + " " + item.get("snippet", "")):
        return 2
    return rel


def recency(days):
    return 1.0 if days <= 7 else max(0.4, 1 - 0.6 * (days - 7) / 23.0)


def thesis_fit(thesis):
    t = (thesis or "").lower()
    if re.search(r"logistic|supply.?chain|freight|transport|mobility|trucking|warehous|fleet", t):
        return 15, "thesis covers logistics / supply chain"
    if re.search(r"b2b|saas|enterprise|software|industrial|commerce infra|smb|vertical", t):
        return 8, "thesis covers B2B software"
    return 3, "generalist thesis"


def next_run_day(today):
    for k in range(1, 8):
        d = today + dt.timedelta(days=k)
        if d.weekday() in (0, 3):  # Monday, Thursday
            return d
    return today + dt.timedelta(days=3)


def score(vc, signals, today):
    """Returns (score 0-100, action text, breakdown list). Pure function: same inputs, same answer."""
    breakdown = []
    pts = sorted((s["points"] for s in signals), reverse=True)
    strength = 0.0
    if pts:
        strength = min(70.0, pts[0] + 0.4 * sum(pts[1:2]) + 0.2 * sum(pts[2:3]))
        breakdown.append(["Signal strength (best %d signal%s, last 30 days)" % (len(pts), "" if len(pts) == 1 else "s"),
                          round(strength)])
    else:
        breakdown.append(["No qualifying signal in the last 30 days", 0])
    fit, why = thesis_fit(vc.get("thesis"))
    breakdown.append(["Thesis fit: " + why, fit])

    status = vc.get("status") or "yet_to_reach_out"
    last = _d(vc.get("last_contact_date"))
    days = (today - last).days if last else None
    timing = 0
    if status == "waiting_response" and days is not None:
        if days < 7:
            timing = -30
            breakdown.append(["You followed up %d days ago: too soon to chase" % days, timing])
        elif days < 14:
            timing = -10
            breakdown.append(["Last touch %d days ago: give it a little longer" % days, timing])
        elif strength >= 15:
            timing = 10
            breakdown.append(["Waiting %d days + fresh signal = natural nudge" % days, timing])
        elif days > 45:
            timing = 5
            breakdown.append(["Silent for %d days: worth a light re-warm" % days, timing])
    elif status == "yet_to_reach_out" and strength >= 15:
        timing = 10
        breakdown.append(["Not contacted yet + timely hook for a first email", timing])

    total = int(round(max(0, min(100, strength + fit + timing))))
    return total, breakdown, strength, days


def action_for(vc, total, strength, days, hook, best, today, last_any):
    status = vc.get("status") or "yet_to_reach_out"
    recheck = short_date(next_run_day(today))
    if status == "waiting_response" and days is not None and days < 7:
        wait_till = short_date(_d(vc["last_contact_date"]) + dt.timedelta(days=7))
        extra = (" Save this hook for then: " + hook) if hook and strength >= 15 else ""
        return "WAIT · You followed up %d days ago; give them until %s.%s" % (days, wait_till, extra)
    if strength <= 0:
        since = (" Last signal seen %s." % short_date(last_any)) if last_any else ""
        fit = " Strong thesis fit, so keep them on the list; don't chase now." if thesis_fit(vc.get("thesis"))[0] >= 15 else ""
        return "PARK · Quiet: no posts, deals, talks or interviews in 30 days.%s%s Recheck %s." % (since, fit, recheck)
    lead = hook or (best and best.get("summary")) or "reference their recent activity"
    if total >= 55:
        verb = "NUDGE" if status == "waiting_response" else "REACH OUT"
        return "%s · This week. %s" % (verb, lead)
    if total >= 35:
        return "WARM · If you have bandwidth this week. %s" % lead
    return "LOW · Active, but not on your space right now. Recheck %s." % recheck


# ---------------------------------------------------------------- the run

def start_run(trigger):
    # a run that has been "running" for over 8 minutes died (timeout); close it so it never blocks the next one
    _db.q("update runs set status = 'abandoned', finished_at = now() "
          "where status = 'running' and started_at < now() - interval '8 minutes'")
    live = _db.q("select id from runs where status = 'running' order by id desc limit 1")
    if live:
        return live[0]["id"], False
    fp = _db.q(FINGERPRINT)[0]
    ids = [r["id"] for r in _db.q("select id from vcs order by id")]
    rid = _db.q("insert into runs (trigger, vcs_total, notes_hash_before, sources) values ($1, $2, $3, $4::jsonb) "
                "returning id", [trigger, len(ids), fp["h"],
                                 json.dumps({"gemini_search": _sources.SEARCH_STATE["available"]})])[0]["id"]
    return rid, True


def _log(run_id, entry):
    _db.q("update runs set log = log || $2::jsonb where id = $1", [run_id, json.dumps([entry])])


def process(run_id, vc_ids, workers=8, judge_size=10):
    """Gather, judge, score and write a set of VCs. Returns a short report per VC."""
    if not vc_ids:
        return []
    vcs = _db.q("select * from vcs where id = any($1::int[]) order by id", [list(vc_ids)])
    today = _sources.today()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        gathered = list(ex.map(lambda v: (v,) + _sources.gather(v, _gemini), vcs))

    batches = [gathered[i:i + judge_size] for i in range(0, len(gathered), judge_size)]
    verdicts, errors = {}, 0
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(judge, [(v, items) for v, items, _ in b]) for b in batches]
        for f in futs:
            try:
                verdicts.update(f.result())
            except Exception as e:
                errors += 1
                _log(run_id, {"error": "judge: %s" % str(e)[:200]})

    report = []
    for vc, items, tally in gathered:
        v = verdicts.get(vc["id"])
        kept = []
        judged = v is not None or not items
        for i, it in enumerate(items):
            j = (v or {}).get("items", {}).get(i)
            if not j or j.get("actor") not in ("person", "firm"):
                continue
            rel = verify_relevance(max(0, min(3, int(j.get("relevance") or 0))), it)
            kind = j.get("kind") if j.get("kind") in KIND_W else "other"
            days = (today - _d(it["published"])).days
            p = KIND_W[kind] * REL_M[rel] * ACTOR_M[j["actor"]] * recency(days)
            if p < 4:
                continue
            kept.append(dict(it, kind=kind, relevance=rel, actor=j["actor"], summary=j.get("summary", "")[:200],
                             event=(j.get("event") or it["url"])[:80], points=round(p, 1)))
        kept.sort(key=lambda s: s["points"], reverse=True)
        # one real-world event = one signal, however many outlets covered it (the others are kept as "also covered")
        seen_ev = set()
        for k in kept:
            k["dup"] = k["event"] in seen_ev
            seen_ev.add(k["event"])

        prev = _db.q("select max(published) as d from signals where vc_id = $1 and about_vc and points >= 4", [vc["id"]])
        last_any = _d(prev[0]["d"]) if prev and prev[0]["d"] else None
        if kept:
            newest = max(_d(s["published"]) for s in kept)
            last_any = max(last_any, newest) if last_any else newest

        total, breakdown, strength, days = score(vc, [k for k in kept if not k["dup"]], today)
        hook = (v or {}).get("hook", "") if kept else ""
        action = action_for(vc, total, strength, days, hook, kept[0] if kept else None, today, last_any)
        if kept:
            summary = (v or {}).get("overall") or "; ".join(
                "%s: %s" % (short_date(s["published"]), s["summary"]) for s in kept[:2])
        else:
            checked = ["news", "firm deals"] + (["their blog"] if vc.get("feed_url") else []) + ["podcasts"] + (
                ["web search"] if _sources.SEARCH_STATE["available"] else [])
            summary = "No qualifying public activity in the last 30 days (checked %s)." % ", ".join(checked)
        if not judged:
            # Gemini failed for this VC: keep yesterday's verdict instead of wrongly calling them quiet
            report.append({"id": vc["id"], "name": vc["name"], "skipped": True, "tally": tally})
            continue

        stmts = []
        for s in items:
            k = next((x for x in kept if x["url"] == s["url"]), None)
            stmts.append(("insert into signals (vc_id, url, title, source, origin, published, kind, relevance, about_vc, "
                          "summary, points, run_id, event, dup) values ($1,$2,$3,$4,$5,$6::date,$7,$8,$9,$10,$11,$12,$13,$14) "
                          "on conflict (vc_id, url) do update set kind = excluded.kind, relevance = excluded.relevance, "
                          "about_vc = excluded.about_vc, summary = excluded.summary, points = excluded.points, "
                          "run_id = excluded.run_id, event = excluded.event, dup = excluded.dup",
                          [vc["id"], s["url"], s["title"], s["source"], s["origin"], _iso(s["published"]),
                           k["kind"] if k else None, k["relevance"] if k else 0, bool(k),
                           k["summary"] if k else None, k["points"] if k else 0, run_id,
                           k["event"] if k else None, bool(k and k["dup"])]))
        stmts.append(("insert into vc_changes (run_id, vc_id, old_score, new_score, old_action, new_action) "
                      "values ($1,$2,$3,$4,$5,$6) on conflict do nothing",
                      [run_id, vc["id"], vc.get("follow_up_score"), total, vc.get("recommended_action"), action]))
        # THE ONLY WRITE TO VIKRAM'S TABLE: four signal columns, nothing else (and the login can't do more anyway).
        stmts.append(("update vcs set last_signal_date = $2::date, signal_summary = $3, follow_up_score = $4, "
                      "recommended_action = $5 where id = $1",
                      [vc["id"], _iso(last_any), summary[:600], total, action[:400]]))
        _db.tx(stmts)
        report.append({"id": vc["id"], "name": vc["name"], "firm": vc["firm"], "score": total, "old": vc.get("follow_up_score"),
                       "action": action.split(" · ")[0], "scanned": len(items), "kept": len([k for k in kept if not k["dup"]]), "tally": tally,
                       "breakdown": breakdown})

    done = [r for r in report if not r.get("skipped")]
    _db.q("update runs set vcs_done = vcs_done + $2, items_scanned = items_scanned + $3, signals_kept = signals_kept + $4, "
          "errors = errors + $5 where id = $1",
          [run_id, len(report), sum(r.get("scanned", 0) for r in done), sum(r.get("kept", 0) for r in done),
           errors + len(report) - len(done)])
    return report


def finish_run(run_id):
    fp = _db.q(FINGERPRINT)[0]
    _db.q("update runs set status = 'done', finished_at = now(), notes_hash_after = $2, "
          "hot_count = (select count(*) from vcs where recommended_action like 'REACH OUT%' or recommended_action like 'NUDGE%'), "
          "quiet_count = (select count(*) from vcs where recommended_action like 'PARK%'), "
          "sources = coalesce(sources, '{}'::jsonb) || $3::jsonb where id = $1",
          [run_id, fp["h"], json.dumps({"gemini_search": _sources.SEARCH_STATE["available"],
                                        "model": _gemini.LAST["model"], "models_used": _gemini.USED})])
    return _db.q("select * from runs where id = $1", [run_id])[0]


def run_all(trigger="cron"):
    rid, fresh = start_run(trigger)
    if not fresh:
        return {"run_id": rid, "status": "already running"}
    ids = [r["id"] for r in _db.q("select id from vcs order by id")]
    report = process(rid, ids, workers=10, judge_size=10)
    run = finish_run(rid)
    return {"run_id": rid, "run": run, "report": report}
