"""Live, public, official sources. No logins, no LinkedIn/X scraping, no paid scrapers.

  news       Google News RSS search for the person            (articles, interviews, quotes)
  firm_news  Google News RSS: the firm + logistics keywords   (deals in Vikram's space)
  blog       the VC's own blog / Substack RSS feed            (things they wrote)
  podcast    Apple Podcasts search API                        (shows they spoke on)
  search     Gemini + Google Search grounding (optional)      (talks, events, panels)

Every item carries a URL and a publish date from the source itself. Nothing older than WINDOW days.
"""
import datetime as dt
import email.utils
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

WINDOW = 30
UA = "Mozilla/5.0 (compatible; VCPulse/1.0; +https://github.com/nawazalam4u/vc-pulse)"
SPACE = '(logistics OR "supply chain" OR freight OR warehousing OR trucking OR shipping OR fleet)'


def today():
    return dt.datetime.now(dt.timezone.utc).date()


def cutoff():
    return today() - dt.timedelta(days=WINDOW)


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return email.utils.parsedate_to_datetime(s).date()
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")[:25]).date()
    except ValueError:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return dt.date.fromisoformat(m.group(1)) if m else None


def _clean(s, n=400):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def _fresh(d):
    return d is not None and cutoff() <= d <= today() + dt.timedelta(days=1)


def _local(n):
    return n.split("}")[-1]


def _feed_items(xml_bytes):
    """RSS 2.0 or Atom -> [{title, url, published, snippet, source}]"""
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag not in ("item", "entry"):
            continue
        f = {"title": "", "url": "", "date": None, "snippet": "", "source": ""}
        for c in el:
            t = _local(c.tag)
            if t == "title":
                f["title"] = _clean(c.text, 220)
            elif t == "link":
                f["url"] = (c.text or c.attrib.get("href") or f["url"]).strip() if (c.text or c.attrib.get("rel", "alternate") == "alternate") else f["url"]
            elif t in ("pubDate", "published", "updated", "date") and not f["date"]:
                f["date"] = _date(c.text)
            elif t in ("description", "summary", "encoded", "content") and not f["snippet"]:
                f["snippet"] = _clean(c.text)
            elif t == "source":
                f["source"] = _clean(c.text, 80)
        if f["title"] and f["url"]:
            out.append(f)
    return out


def google_news(query, region="India"):
    india = "india" in (region or "").lower()
    params = {"q": query + " when:%dd" % WINDOW, "hl": "en-IN" if india else "en-US",
              "gl": "IN" if india else "US", "ceid": "IN:en" if india else "US:en"}
    items = _feed_items(_get("https://news.google.com/rss/search?" + urllib.parse.urlencode(params)))
    out = []
    for f in items:
        title = f["title"]
        if f["source"] and title.endswith(" - " + f["source"]):
            title = title[: -len(f["source"]) - 3]
        if _fresh(f["date"]):
            out.append({"title": title, "url": f["url"], "published": f["date"], "source": f["source"] or "Google News",
                        "snippet": ""})
    return out[:12]


def blog(feed_url):
    out = []
    for f in _feed_items(_get(feed_url)):
        if _fresh(f["date"]):
            host = urllib.parse.urlparse(f["url"]).hostname or "blog"
            out.append({"title": f["title"], "url": f["url"], "published": f["date"],
                        "source": host.replace("www.", ""), "snippet": f["snippet"][:300]})
    return out[:6]


def podcasts(name):
    d = json.loads(_get("https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": name, "entity": "podcastEpisode", "limit": 50})))
    last = name.split()[-1].lower()
    out = []
    for r in d.get("results", []):
        when = _date(r.get("releaseDate"))
        text = (r.get("trackName", "") + " " + r.get("description", "")).lower()
        if _fresh(when) and last in text:
            out.append({"title": r.get("trackName", "")[:200], "url": r.get("trackViewUrl") or r.get("episodeUrl", ""),
                        "published": when, "source": r.get("collectionName", "Podcast")[:80],
                        "snippet": _clean(r.get("description", ""), 300)})
    return out[:5]


import os
# Google Search grounding is not part of the free Gemini plan. Set GEMINI_SEARCH=1 on Vercel once billing is on.
SEARCH_STATE = {"available": None if os.environ.get("GEMINI_SEARCH") == "1" else False}


def web_search(vc, gemini):
    """Gemini with Google Search grounding. Only links Google actually returned are kept."""
    if SEARCH_STATE["available"] is False:
        return []
    prompt = ("Today is %s. Find public activity by %s (%s) dated between %s and %s: posts or articles they wrote, "
              "interviews or podcasts, investments their firm announced, events or panels they spoke at. "
              "Return ONLY a JSON array (max 5) of {\"date\":\"YYYY-MM-DD\",\"title\":\"...\",\"url\":\"...\"}. "
              "Return [] if nothing is found. Never guess a date."
              % (today(), vc["name"], vc["firm"], cutoff(), today()))
    try:
        text, resp = gemini.generate(prompt, tools=[{"google_search": {}}], timeout=40, models=gemini.MODELS[:1])
        SEARCH_STATE["available"] = True
    except Exception as e:
        if " 429" in str(e) or " 403" in str(e) or " 400" in str(e):
            SEARCH_STATE["available"] = False
        return []
    meta = ((resp.get("candidates") or [{}])[0]).get("groundingMetadata") or {}
    domains = {(c.get("web") or {}).get("title", "").lower() for c in meta.get("groundingChunks", [])}
    try:
        rows = gemini.parse_json(text)
    except ValueError:
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        d, url = _date(str(r.get("date", ""))), str(r.get("url", ""))
        host = (urllib.parse.urlparse(url).hostname or "").replace("www.", "").lower()
        if _fresh(d) and host and any(host.endswith(x) or x.endswith(host) for x in domains if x):
            out.append({"title": str(r.get("title", ""))[:200], "url": url, "published": d, "source": host, "snippet": ""})
    return out[:5]


def short_firm(firm):
    return re.sub(r"\b(Partners|Ventures|Capital|Venture Partners|Fund|Management|Advisors)\b", "", firm).strip() or firm


def gather(vc, gemini=None):
    """All candidate items for one VC + a per-source tally. Failures of one source never stop the others."""
    jobs = [("news", lambda: google_news('"%s"' % vc["name"], vc.get("region"))),
            ("firm_news", lambda: google_news('"%s" %s' % (vc["firm"], SPACE), vc.get("region"))),
            ("podcast", lambda: podcasts(vc["name"]))]
    if vc.get("feed_url"):
        jobs.append(("blog", lambda: blog(vc["feed_url"])))
    if gemini is not None and gemini.configured():
        jobs.append(("search", lambda: web_search(vc, gemini)))
    items, tally, seen = [], {}, set()
    for origin, fn in jobs:
        try:
            got = fn()
            tally[origin] = len(got)
        except Exception as e:
            got, tally[origin] = [], "error: %s" % str(e)[:60]
        for it in got:
            key = re.sub(r"\W+", "", it["title"].lower())[:70]
            if it["url"] in seen or key in seen:
                continue
            seen.update((it["url"], key))
            it["origin"] = origin
            items.append(it)
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:18], tally
