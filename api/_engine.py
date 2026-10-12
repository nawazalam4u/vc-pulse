"""The signal engine: gather -> judge (Gemini Flash) -> score (code) -> write the 4 signal columns.

Who decides what:
  * Sources decide WHAT happened and WHEN (every signal has a link and a publish date from the source).
  * Gemini Flash decides WHAT IT MEANS: is it really this VC? what kind of act? how close to logistics?
  * Code decides the SCORE and the ACTION, with fixed, explainable rules (see score()).
  * The database decides WHAT MAY BE WRITTEN: the engine login can only touch the 4 signal columns.
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import _db
import _gemini
import _sources

COMPANY = ("Haulr, a seed-stage B2B logistics SaaS from India (freight visibility, carrier management and "
           "dispatch software for mid-market shippers)")

# What a signal MEANS for Haulr decides its weight, not merely what kind of act it was. A past or new deal in the
# same category is not by itself a reason to invest again: a direct competitor is a conflict (negative), an adjacent
# company is a medium "complement" signal. The strongest signals show the investor is LOOKING for more deals like Haulr.
ANGLE_W = {"thesis": 42,      # they say/write they want this space: an open invitation
           "deploying": 34,   # actively writing new seed/early cheques now (new fund, bigger cheques, new cohort)
           "complement": 26,  # backed an adjacent, non-competing company: conviction + partnership/intro angle
           "visible": 10,     # publicly active on other topics: reachable this week, nothing more
           "overlap": 0,      # backed a direct competitor: handled as a conflict penalty
           "none": 0}
ANGLE_LABEL = {"thesis": "Thesis: they say they want this space", "deploying": "Deploying: writing new early cheques",
               "complement": "Complement: backed an adjacent company", "visible": "Visible: publicly active",
               "overlap": "Overlap: backed a direct competitor", "none": "Not useful"}
KIND_W = {"invested": 40, "wrote": 34, "said": 30, "appeared": 26, "mentioned": 14, "other": 6}  # display only
REL_M = {3: 1.0, 2: 0.6, 1: 0.3, 0: 0.0}
ACTOR_M = {"person": 1.0, "firm": 0.85}  # deals are announced in the firm's name, so firm acts count nearly fully
KIND_VERB = {"invested": "invested", "wrote": "wrote", "said": "spoke", "appeared": "appeared at an event",
             "mentioned": "was in the news"}

VIKRAM_COLS = "id, name, firm, thesis, region, status, last_contact_date, contact_history, notes, feed_url"
FINGERPRINT = ("select md5(coalesce(string_agg(concat_ws('|', %s), '~' order by id), '')) as h, count(*) as n from vcs"
               % ", ".join("coalesce(%s::text, '∅')" % c.strip() for c in VIKRAM_COLS.split(",")))

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
                "angle": {"type": "STRING", "enum": ["thesis", "deploying", "complement", "overlap", "visible", "none"]},
                "relevance": {"type": "INTEGER"},
                "event": {"type": "STRING"},
                "summary": {"type": "STRING"}},
                "required": ["i", "actor", "kind", "angle", "relevance", "event", "summary"]}},
            "overall": {"type": "STRING"},
            "hook": {"type": "STRING"},
            "hook_item": {"type": "INTEGER"},
            "why": {"type": "STRING"},
            "conflict": {"type": "STRING"},
            "geo_fit": {"type": "STRING", "enum": ["match", "mismatch", "unclear"]},
            "stage_fit": {"type": "STRING", "enum": ["match", "mismatch", "unclear"]}},
        "required": ["vc", "items", "overall", "hook", "hook_item", "why", "conflict", "geo_fit", "stage_fit"]}}

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
angle:  what the item MEANS for Haulr's chance of getting a meeting. Think like an experienced founder: a past or new
        investment in the same category is NOT by itself a reason this investor will invest again.
        "thesis"     = the investor THEMSELVES expresses appetite to back startups in Haulr's space: logistics, freight,
                       supply-chain or transport software (a post "why we're excited about freight tech", a talk on
                       logistics opportunities, a request-for-startups). General SaaS, AI, sales or fundraising advice is
                       NOT thesis, it is "visible". Only for wrote/said/appeared, never for a deal.
        "deploying"  = evidence they are actively writing NEW cheques at seed/early stage right now: a new fund, bigger
                       seed cheques, a new accelerator cohort, a fresh seed/pre-seed deal in B2B software.
        "complement" = they backed or work with a company in Haulr's ecosystem that is NOT a competitor (shippers,
                       marketplaces, defence or military logistics, warehouse robotics, supply-chain AI for other
                       segments): sector conviction plus a partnership or warm-intro angle, nothing more.
        "overlap"    = they backed a company doing the SAME job as Haulr (freight visibility, carrier management or
                       dispatch software for shippers). Usually NEGATIVE: VCs rarely fund a portfolio company's rival.
        "visible"    = publicly active (interview, podcast, event, post) on topics unrelated to Haulr: reachable now.
        "none"       = not useful (share sales, personal news, unrelated).
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
        dates like "8 Oct". Only use items with actor person/firm. Credit the PERSON only for what they did themselves
        (e.g. a blog post whose author is someone else is "a16z published ...", not "Seema wrote ...").
        If nothing qualifies, return "".
hook:   <= 22 words, written to THIS investor about THEIR OWN act (an item with actor person/firm): the specific,
        honest opening line for the founder's email, e.g. "Saw Peak XV raise Surge checks to $5M on 29 Sep."
        Never mention other people. Return "" if nothing qualifies.
hook_item: the [number] of the item the hook is based on (-1 if hook is "").
why:    <= 38 words: WHY this matters to Haulr right now, reasoning from the strongest angle, honestly. Say what it
        does and does NOT prove, and name any mismatch in stage or geography (Haulr is an Indian seed-stage company;
        the investor's region and thesis are given). Never argue "they invested in logistics before, so they will
        again". Good: "Point Nine just backed Procuros, an AI supply-chain platform for European suppliers: proof of
        appetite for supply-chain SaaS at seed, and Procuros is a complement, not a rival. Caveat: Europe-focused."
        Use ONLY the items, thesis and region given: never cite other portfolio companies, track records or facts from
        memory. Return "" if nothing qualifies.
geo_fit: "match" if the investor is India-based or the items/thesis show they invest in Indian startups; "mismatch"
        if the thesis or items show a mandate limited to another market (e.g. US-only "American Dynamism"); else "unclear".
stage_fit: "match" if they invest at seed/early stage; "mismatch" if the items/thesis show growth or late stage only;
        else "unclear".
conflict: if a qualifying item shows this investor/firm just backed a DIRECT competitor of Haulr (freight visibility,
        carrier management or dispatch software for shippers), the competitor's name exactly as written in the item;
        otherwise "". Adjacent logistics companies (defence logistics, robotics, warehousing hardware) are NOT conflicts.""" % COMPANY


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
               "blog": "from the blog feed on file for them (may be their firm's blog: check the author)", "podcast": "podcast episode that mentions them",
               "search": "from Google Search"}
        lines = ["- [%d] %s | %s | %s | %s%s%s" % (i, it["title"], it["source"], _iso(it["published"]), how.get(it["origin"], ""),
                                                  (" | author: " + it["author"]) if it.get("author") else "",
                                                  (" | " + it["snippet"][:160]) if it.get("snippet") else "")
                 for i, it in enumerate(items)]
        blocks.append("INVESTOR vc=%d: %s (%s), based in %s. Thesis: %s\n%s" % (
            vc["id"], vc["name"], vc["firm"], vc.get("region") or "?", vc.get("thesis") or "-", "\n".join(lines)))
    if not blocks:
        return {}
    out = _gemini.generate_json("\n\n".join(blocks), {"type": "OBJECT", "properties": {"investors": JUDGE_SCHEMA},
                                                       "required": ["investors"]},
                                system=JUDGE_SYSTEM, temperature=0.1, timeout=120)
    out = out.get("investors", []) if isinstance(out, dict) else out
    res = {}
    for row in out if isinstance(out, list) else []:
        try:
            res[int(row["vc"])] = {"items": {int(x["i"]): x for x in row.get("items", [])},
                                   "overall": (row.get("overall") or "").strip(),
                                   "hook": (row.get("hook") or "").strip(),
                                   "hook_item": row.get("hook_item", -1),
                                   "why": (row.get("why") or "").strip(),
                                   "conflict": (row.get("conflict") or "").strip(),
                                   "geo_fit": row.get("geo_fit", "unclear"), "stage_fit": row.get("stage_fit", "unclear")}
        except (KeyError, TypeError, ValueError):
            continue
    return res


def fallback_hook(vc, counted):
    """Factual hook built from the strongest kept item's real title: 'your' only when the partner acted personally."""
    if not counted:
        return ""
    top = max(k["points"] for k in counted)
    strong = [k for k in counted if k["points"] >= 0.6 * top]  # the partner's own act wins only if it's comparably strong
    best = sorted(strong, key=lambda k: (k["actor"] != "person" and k.get("angle") != "thesis", -k["points"]))[0]
    who = "your" if best["actor"] == "person" else re.sub(r"\s*\(.*\)", "", vc["firm"]).strip() + "'s"
    verb = {"invested": "deal coverage", "wrote": "post", "said": "interview", "appeared": "event appearance"}.get(best["kind"], "news")
    if best.get("origin") == "blog":
        verb = "post"
    if best.get("angle") == "thesis":
        verb = {"wrote": "post on", "said": "comments on", "appeared": "talk on"}.get(best["kind"], "view on")
    return 'Saw %s %s "%s" (%s)' % (who, verb, best["title"][:90], short_date(best["published"]))


# ---------------------------------------------------------------- scoring (code, explainable)

LOGISTICS_WORDS = re.compile(r"logistic|freight|supply.?chain|truck|shipping|shipper|warehous|fleet|cargo|courier|"
                             r"last.?mile|transport|3pl|carrier|dispatch|port\b|ports\b|mobility|delivery", re.I)


def verify_relevance(rel, item):
    """Code checks the AI: a 'logistics' (3) rating needs a logistics word in the source text itself."""
    if rel >= 3 and not LOGISTICS_WORDS.search(item.get("title", "") + " " + item.get("snippet", "")):
        return 2
    return rel


def firm_aliases(firm):
    """'Andreessen Horowitz (a16z)' -> ['andreessen horowitz', 'a16z']; 'Z47 (formerly Matrix Partners India)' -> ['z47']"""
    main, _, rest = firm.partition("(")
    names = [main]
    inner = rest.rstrip(")").strip()
    if inner and not inner.lower().startswith(("formerly", "india")):
        names.append(inner)
    out = []
    for n in names:
        n = re.sub(r"\b(Venture Partners|Partners|Ventures|Venture|Capital|Fund|Management)\b", "", n).strip(" ,.-")
        if len(n) >= 3:
            out.append(n.lower())
    return out


def blog_actor(vc, item, actor):
    """Firm-wide blogs (a16z, Point Nine...) have many authors: a post counts as THIS partner's only if they wrote it."""
    if item["origin"] != "blog" or actor != "person":
        return actor
    last = vc["name"].split()[-1].lower()
    author = (item.get("author") or "").lower()
    if author:
        return "person" if last in author else "firm"
    host = (item.get("url", "").split("/")[2] if "//" in item.get("url", "") else "").lower()
    return "person" if last in host.replace("-", "") else "firm"  # personal site/Substack (e.g. tomtunguz.com)


STRICT_LOGISTICS = re.compile(r"logistic|freight|supply.?chain|truck|shipping|shipper|warehous|fleet|cargo|3pl", re.I)


def names_them(vc, item, kind):
    """Code checks the evidence: the text we show Vikram must name his investor (or, for a deal, be in his space)."""
    if item["origin"] == "blog":
        return True  # the feed on file for them (authorship is checked separately in blog_actor)
    text = (item.get("title", "") + " " + item.get("snippet", "")).lower()
    last = vc["name"].split()[-1].lower()
    named = last in text or any(a in text for a in firm_aliases(vc["firm"]))
    if item["origin"] == "firm_news":
        return kind == "invested" and (named or bool(STRICT_LOGISTICS.search(text)))
    return named


ADJACENT_WORDS = re.compile(LOGISTICS_WORDS.pattern + r"|industrial|physical|manufactur|mobility|operations|infrastructure", re.I)


SALE_WORDS = re.compile(r"\bsells?\b|\bsold\b|stake sale|offload|\bexits?\b|trims stake|cuts stake|block deal", re.I)
COMMON = set("""A An The This That These Those It Its Their They He She His Her We Our Haulr Haulr's India Indian US USA
Europe European Caveat Mismatch However But While Although Direct Proof Strong Good Clear Active Actively Recent Recently
Seed Series Pre-seed AI B2B SaaS VC VCs CEO Partner Partners Fund Funds Ventures Capital Firm Oct Sep Sept Nov Aug
Jan Feb Mar Apr May Jun Jul Dec Logistics Supply Chain No Not Only Also Both Its Since Surge""".split())


def ground_why(why, evidence, vc):
    """Remove any sentence that names a company/person the evidence (or Vikram's own row) doesn't mention.
    Gemini is told not to use memory; this makes sure."""
    known = (evidence + " " + " ".join(str(vc.get(k) or "") for k in ("name", "firm", "thesis", "region"))).lower()
    keep = []
    for sent in re.split(r"(?<=[.!?])\s+", why or ""):
        words = re.findall(r"\b[A-Z][A-Za-z0-9&'\-]{2,}\b", sent)[1:]  # skip the sentence's first word
        if all(w.split("-")[0] in COMMON or w.lower().rstrip("'s") in known for w in words):
            keep.append(sent)
    return " ".join(keep).strip()


def check_angle(angle, kind, rel=3, text=None):
    """Code checks the AI's reading: a thesis is something they SAID about Haulr's space (not a deal, not off-topic);
    an overlap must be an investment."""
    angle = angle if angle in ANGLE_W else "none"
    if angle == "thesis" and kind == "invested":
        return "complement"
    if angle == "thesis" and rel <= 1:
        return "visible"
    if angle in ("deploying", "complement", "overlap") and text is not None and SALE_WORDS.search(text):
        return "none"  # selling shares or exiting is not putting money in
    if angle == "thesis" and text is not None and not ADJACENT_WORDS.search(text):
        return "visible"  # a thesis must be ABOUT Haulr's world, in the source's own words
    if angle == "overlap" and kind != "invested":
        return "complement"
    return angle


def signal_points(angle, rel, actor, days):
    """Weight by what the signal MEANS (angle) x topic fit x who acted x freshness."""
    # deploying = open allocation; it counts fully only when the new cheques are in or near Haulr's space
    topic = {3: 1.0, 2: 0.5}.get(rel, 0.0) if angle == "thesis" else REL_M[rel] if angle == "complement" else ({3: 1.0, 2: 0.8, 1: 0.6}.get(rel, 0.3) if angle == "deploying" else 1.0)
    return ANGLE_W.get(angle, 0) * topic * ACTOR_M.get(actor, 0.85) * recency(days)


def recency(days):
    return 1.0 if days <= 7 else max(0.4, 1 - 0.6 * (days - 7) / 23.0)


def geo_fit(region):
    return (10, "India-based: invests in Haulr's home market") if "india" in (region or "").lower() else (0, "")


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


def fit_penalties(vc, flags):
    """Gemini's honest caveats change the score too. Who is likely to take a meeting with an INDIAN SEED-stage company?"""
    out = []
    if not flags:
        return out
    indian = "india" in (vc.get("region") or "").lower()
    if not indian and flags.get("geo_fit") == "mismatch":
        out.append(["Gemini: mandate outside Haulr's market (India)", -15])
    elif not indian and flags.get("geo_fit") == "unclear":
        out.append(["Not India-based; no sign they back Indian startups", -5])
    if flags.get("stage_fit") == "match":
        out.append(["Gemini: invests at seed/early stage, like Haulr", 5])
    elif flags.get("stage_fit") == "mismatch":
        out.append(["Gemini: invests later than seed", -8])
    return out


def score(vc, signals, today, conflict="", flags=None):
    """Returns (score 0-100, action text, breakdown list). Pure function: same inputs, same answer."""
    breakdown = []
    pts = sorted((s["points"] for s in signals), reverse=True)
    strength = 0.0
    if pts:
        strength = min(70.0, pts[0] + 0.4 * sum(pts[1:2]) + 0.2 * sum(pts[2:3]))
        best = max(signals, key=lambda x: x["points"])
        breakdown.append(["Signal strength: best is %s (%d signal%s, last 30 days)" % (
            ANGLE_LABEL.get(best.get("angle"), "a signal").split(":")[0].lower(), len(pts), "" if len(pts) == 1 else "s"),
            round(strength)])
    else:
        breakdown.append(["No qualifying signal in the last 30 days", 0])
    fit, why = thesis_fit(vc.get("thesis"))
    breakdown.append(["Thesis fit: " + why, fit])
    geo, gwhy = geo_fit(vc.get("region"))
    if geo:
        breakdown.append([gwhy, geo])
        fit += geo

    status = vc.get("status") or "yet_to_reach_out"
    last = _d(vc.get("last_contact_date"))
    days = max(0, (today - last).days) if last else None
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

    penalty = 0
    for line in fit_penalties(vc, flags):
        breakdown.append(line)
        penalty += line[1]
    if conflict:
        penalty += -15
        breakdown.append(["Just backed %s, a likely Haulr competitor" % conflict[:40], penalty])
    total = int(round(max(0, min(100, strength + fit + timing + penalty))))
    return total, breakdown, strength, days


def action_for(vc, total, strength, days, hook, best, today, last_any, mention=None):
    status = vc.get("status") or "yet_to_reach_out"
    recheck = short_date(next_run_day(today))
    if status == "waiting_response" and days is not None and days < 14:
        wait_till = short_date(_d(vc["last_contact_date"]) + dt.timedelta(days=14))
        extra = (" Hook ready for then: " + hook) if hook and strength >= 15 else ""
        return "WAIT · You followed up %d day%s ago; give them until %s before nudging.%s" % (
            days, "" if days == 1 else "s", wait_till, extra)
    if strength <= 0:
        quiet_days = (today - mention).days if mention else None
        if quiet_days is None or quiet_days > 90:
            quiet = "Quiet for 3+ months: no news naming them with their firm since %s." % (
                short_date(mention) if mention else "at least a year")
        else:
            quiet = "Quiet: nothing in 30 days (last in the news %s)." % short_date(mention)
        strong_fit = thesis_fit(vc.get("thesis"))[0] >= 15
        if status == "waiting_response" and days is not None and days > 45:
            rel = " No reply in %d days either: don't chase this week; one light check-in next month, or move on." % days
        elif status == "waiting_response" and days is not None:
            rel = " You're waiting %d days for a reply: let it sit, no nudge without a reason." % days
        elif strong_fit:
            rel = " Strong thesis fit: keep them on the list for when they resurface."
        else:
            rel = " Not worth first-touch energy this week."
        return "PARK · %s%s Recheck %s." % (quiet, rel, recheck)
    lead = hook or (best and best.get("summary")) or "reference their recent activity"
    if total >= 55:
        # a FIRST email needs an on-topic reason; a follow-up only needs a timely one
        rel = int((best or {}).get("relevance") or 0)
        on_topic = rel >= 3 or (rel >= 2 and (best or {}).get("angle") in ("thesis", "complement"))
        if status != "waiting_response" and not on_topic:
            return "WARM · Active and a good fit, but no logistics hook yet, so not a cold-email moment. %s" % lead
        verb = "NUDGE" if status == "waiting_response" else "REACH OUT"
        return "%s · This week. %s" % (verb, lead)
    if total >= 35:
        return "WARM · If you have bandwidth this week. %s" % lead
    return "LOW · Some public activity, but weak, old or off-topic for you this week. Recheck %s." % recheck


# ---------------------------------------------------------------- the run

def run_token(run_id):
    """Ticket proving the caller started this run; required for every batch/finish call."""
    key = (os.environ.get("CRON_SECRET") or os.environ.get("DASHBOARD_KEY") or "dev").encode()
    return hmac.new(key, ("run:%s" % run_id).encode(), hashlib.sha256).hexdigest()[:32]


def check_token(run_id, token):
    return hmac.compare_digest(run_token(run_id), str(token or ""))


def start_run(trigger):
    # a run "running" for over 12 minutes died (browser closed / timeout): close it so it never blocks the next one.
    # The scheduled run always wins: it supersedes any manual run still in progress.
    _db.q("update runs set status = 'abandoned', finished_at = now() "
          "where status = 'running' and (started_at < now() - interval '12 minutes' or $1 = 'cron')", [trigger])
    live = _db.q("select id from runs where status = 'running' order by id desc limit 1")
    if live:
        return live[0]["id"], False
    fp = _db.q(FINGERPRINT)[0]
    ids = [r["id"] for r in _db.q("select id from vcs order by id")]
    try:
        rid = _db.q("insert into runs (trigger, vcs_total, notes_hash_before, sources) values ($1, $2, $3, $4::jsonb) "
                    "returning id", [trigger, len(ids), fp["h"],
                                     json.dumps({"gemini_search": _sources.SEARCH_STATE["available"]})])[0]["id"]
    except _db.DBError:  # someone else started a run in the same instant: the unique index let only one through
        live = _db.q("select id from runs where status = 'running' order by id desc limit 1")
        return (live[0]["id"] if live else 0), False
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
        kept, attributed = [], []
        judged = (v is not None or not items) and not _sources.news_failed(tally)
        for i, it in enumerate(items):
            j = (v or {}).get("items", {}).get(i)
            if not j or j.get("actor") not in ("person", "firm"):
                continue
            rel = verify_relevance(max(0, min(3, int(j.get("relevance") or 0))), it)
            kind = j.get("kind") if j.get("kind") in KIND_W else "other"
            if not names_them(vc, it, kind):
                continue
            j = dict(j, actor=blog_actor(vc, it, j["actor"]))
            angle = check_angle(j.get("angle"), kind, rel, it.get("title", "") + " " + it.get("snippet", ""))
            attributed.append(dict(it, angle=angle, kind=kind))
            days = (today - _d(it["published"])).days
            p = signal_points(angle, rel, j["actor"], days)
            if p < 4:
                continue
            kept.append(dict(it, kind=kind, angle=angle, relevance=rel, actor=j["actor"], summary=j.get("summary", "")[:200],
                             event=(j.get("event") or it["url"])[:80], points=round(p, 1)))
        kept.sort(key=lambda s: s["points"], reverse=True)
        # one real-world event = one signal, however many outlets covered it (the others are kept as "also covered")
        seen_ev = set()
        for k in kept:
            k["dup"] = k["event"] in seen_ev
            seen_ev.add(k["event"])

        prev = _db.q("select max(published) as d from signals where vc_id = $1 and about_vc and not coalesce(dup, false) "
                     "and points >= 4 and published < current_date - 30", [vc["id"]])  # older history; this run decides the rest
        last_any = _d(prev[0]["d"]) if prev and prev[0]["d"] else None
        if kept:
            newest = max(_d(s["published"]) for s in kept)
            last_any = max(last_any, newest) if last_any else newest

        conflict = (v or {}).get("conflict", "")
        overlaps = [a for a in attributed if a["angle"] == "overlap"]
        if conflict and not any(conflict.lower() in (a["title"] + " " + a.get("snippet", "")).lower() for a in overlaps):
            conflict = ""  # code check: the competitor must be named in an investment item we attributed to them
        flags = {"geo_fit": (v or {}).get("geo_fit", "unclear"), "stage_fit": (v or {}).get("stage_fit", "unclear")}
        total, breakdown, strength, days = score(vc, [k for k in kept if not k["dup"]], today, conflict, flags)
        mention = None
        if strength <= 0 and judged:
            try:
                mention = _sources.last_mention(vc)
            except Exception:
                mention = None
        counted = [k for k in kept if not k["dup"]]
        hook_src = items[v["hook_item"]] if v and isinstance(v.get("hook_item"), int) and 0 <= v["hook_item"] < len(items) else None
        hook_ok = hook_src is not None and any(k["event"] == next((x["event"] for x in kept if x["url"] == hook_src["url"]), None)
                                               for k in counted)
        hook_kept = next((k for k in counted if hook_src is not None and k["url"] == hook_src["url"]), None)
        if hook_ok and hook_kept is not None and hook_kept["actor"] == "firm" and re.search(r"\byour\b", (v or {}).get("hook", ""), re.I):
            hook_ok = False  # Gemini said "your ..." about something only the firm did
        # the hook must come from evidence our code kept; otherwise the code writes a plain factual one
        hook = ((v or {}).get("hook", "") if hook_ok else fallback_hook(vc, counted)).strip().rstrip(".… ")
        hook = hook + "." if hook else ""
        best = max((k for k in kept if not k["dup"]), key=lambda k: k["points"], default=None)
        action = action_for(vc, total, strength, days, hook, best, today, last_any, mention)
        if conflict:
            action += " ⚠ They just backed %s, which overlaps with Haulr: lead with how you're different, or skip." % conflict
        if kept:
            summary = (v or {}).get("overall") or "; ".join(
                "%s: %s" % (short_date(s["published"]), s["summary"]) for s in kept[:2])
            why = ground_why((v or {}).get("why", ""), " ".join(i["title"] + " " + i.get("snippet", "") for i in items), vc)
            if why and strength > 0:
                summary = summary.rstrip(". ") + ". Why it matters for Haulr: " + why
        else:
            checked = ["news", "firm deals"] + (["their blog"] if vc.get("feed_url") else []) + ["podcasts"] + (
                ["web search"] if _sources.SEARCH_STATE["available"] else [])
            summary = "No qualifying public activity in the last 30 days (checked %s). %s" % (
                ", ".join(checked), ("Last news naming them with their firm: %s." % short_date(mention)) if mention
                else "No news naming them with their firm in the past year.")
        if not judged:
            # Gemini failed for this VC: keep yesterday's verdict instead of wrongly calling them quiet
            report.append({"id": vc["id"], "name": vc["name"], "skipped": True, "tally": tally})
            continue

        # this run's view is the current state: drop last-30-day evidence from earlier runs that this run no longer
        # sees (older history is kept for "last signal seen")
        stmts = [("delete from signals where vc_id = $1 and coalesce(run_id, 0) <> $2 and published >= current_date - 30",
                  [vc["id"], run_id])]
        for s in items:
            k = next((x for x in kept if x["url"] == s["url"]), None)
            stmts.append(("insert into signals (vc_id, url, title, source, origin, published, kind, relevance, about_vc, "
                          "summary, points, run_id, event, dup, angle) values ($1,$2,$3,$4,$5,$6::date,$7,$8,$9,$10,$11,$12,$13,$14,$15) "
                          "on conflict (vc_id, url) do update set kind = excluded.kind, relevance = excluded.relevance, "
                          "about_vc = excluded.about_vc, summary = excluded.summary, points = excluded.points, "
                          "run_id = excluded.run_id, event = excluded.event, dup = excluded.dup, angle = excluded.angle",
                          [vc["id"], s["url"], s["title"], s["source"], s["origin"], _iso(s["published"]),
                           k["kind"] if k else None, k["relevance"] if k else 0, bool(k),
                           k["summary"] if k else None, k["points"] if k else 0, run_id,
                           k["event"] if k else None, bool(k and k["dup"]),
                           k["angle"] if k else next((a["angle"] for a in attributed if a["url"] == s["url"]), None)]))
        stmts.append(("insert into vc_changes (run_id, vc_id, old_score, new_score, old_action, new_action, flags) "
                      "values ($1,$2,$3,$4,$5,$6,$7::jsonb) on conflict do nothing",
                      [run_id, vc["id"], vc.get("follow_up_score"), total, vc.get("recommended_action"), action,
                       json.dumps(dict(flags, conflict=conflict))]))
        # THE ONLY WRITE TO VIKRAM'S TABLE: four signal columns, nothing else (and the login can't do more anyway).
        stmts.append(("update vcs set last_signal_date = $2::date, signal_summary = $3, follow_up_score = $4, "
                      "recommended_action = $5 where id = $1",
                      [vc["id"], _iso(last_any), summary[:900], total, action[:500]]))
        try:
            _db.tx(stmts)
        except Exception as e:  # one investor's write failing must not stop the other nine
            _log(run_id, {"error": "write %s: %s" % (vc["name"], str(e)[:150])})
            report.append({"id": vc["id"], "name": vc["name"], "skipped": True, "tally": tally})
            continue
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
    src = _db.q("select sources from runs where id = $1", [run_id])
    src = (src[0]["sources"] if src else None) or {}
    src = json.loads(src) if isinstance(src, str) else src
    cost = sum(float((v or {}).get("usd", 0)) for k, v in src.items() if k.startswith("cost_batch"))
    tokens = sum(int((v or {}).get("tokens", 0)) for k, v in src.items() if k.startswith("cost_batch"))
    per = _db.q("select origin, count(*) as n, count(*) filter (where about_vc and not coalesce(dup, false) and points >= 4) as kept "
                "from signals where run_id = $1 group by origin", [run_id])
    errs = _db.q("select count(*) as n from jsonb_array_elements(coalesce((select log from runs where id = $1), '[]'::jsonb))",
                 [run_id])[0]["n"]
    _db.q("update runs set status = case when vcs_done >= vcs_total then 'done' else 'partial' end, "
          "finished_at = now(), notes_hash_after = $2, "
          "hot_count = (select count(*) from vcs where recommended_action like 'REACH OUT%' or recommended_action like 'NUDGE%'), "
          "quiet_count = (select count(*) from vcs where recommended_action like 'PARK%' or recommended_action like 'LOW%'), "
          "sources = coalesce(sources, '{}'::jsonb) || $3::jsonb where id = $1",
          [run_id, fp["h"], json.dumps({"gemini_search": _sources.SEARCH_STATE["available"],
                                        "model": _gemini.LAST["model"], "models_used": _gemini.USED,
                                        "per_source": {r["origin"]: [int(r["n"]), int(r["kept"])] for r in per},
                                        "log_entries": int(errs), "cost_usd": round(cost, 5), "tokens": tokens})])
    return _db.q("select * from runs where id = $1", [run_id])[0]


def run_all(trigger="cron"):
    rid, fresh = start_run(trigger)
    if not fresh:
        return {"run_id": rid, "status": "already running"}
    _gemini.USED.clear()
    _gemini.COST.update(usd=0.0, tokens=0)
    ids = [r["id"] for r in _db.q("select id from vcs order by id")]
    chunks = [ids[i:i + 10] for i in range(0, len(ids), 10)]
    started, report = time.time(), []

    def work(chunk):
        if time.time() - started > 200:  # time budget: Vercel stops us at 300s; finish cleanly instead
            return []
        return process(rid, chunk, workers=10, judge_size=10)

    with ThreadPoolExecutor(max_workers=5) as ex:  # all 5 batches at once: a full run takes about a minute
        for r in ex.map(work, chunks):
            report += r
    _db.q("update runs set sources = coalesce(sources, '{}'::jsonb) || $2::jsonb where id = $1",
          [rid, json.dumps({"cost_batch_cron": dict(_gemini.COST), "models_used_batch_cron": dict(_gemini.USED)})])
    run = finish_run(rid)
    return {"run_id": rid, "run": run, "report": report}
