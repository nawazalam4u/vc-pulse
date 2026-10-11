"""Gemini Flash over plain HTTPS. JSON-only answers, model fallback and polite retries on rate limits."""
import json
import os
import re
import time
import urllib.error
import urllib.request

MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",") if m.strip()]
URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
LAST = {"model": None}
EXHAUSTED = set()   # models that hit their free daily limit: skip them for the rest of this process
USED = {}           # model -> successful calls (stored in the run log so you can see which model judged)
# Gemini 3.5 Flash "thinks" before answering; low keeps it careful but ~3x faster (25s vs 80s for 5 investors)
THINKING = {"gemini-3.5-flash": "low"}


def configured():
    return bool(os.environ.get("GEMINI_API_KEY"))


def _call(model, body, timeout):
    if model in THINKING:
        body = dict(body, generationConfig=dict(body["generationConfig"], thinkingConfig={"thinkingLevel": THINKING[model]}))
    req = urllib.request.Request(URL % model, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json",
                                          "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _text(resp):
    c = (resp.get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", []) if not p.get("thought"))


def generate(prompt, schema=None, system=None, temperature=0.2, timeout=60, tools=None, models=None):
    """Returns (text, raw_response). Tries each model; waits and retries once on 429/503."""
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema
    if tools:
        body["tools"] = tools
    last = None
    for model in models or MODELS:
        if model in EXHAUSTED:
            continue
        for attempt in range(2):
            try:
                resp = _call(model, body, timeout)
                LAST["model"] = model
                USED[model] = USED.get(model, 0) + 1
                return _text(resp), resp
            except urllib.error.HTTPError as e:
                detail = e.read().decode()
                last = "%s %s: %s" % (model, e.code, detail[:160])
                if e.code == 429 and "PerDay" in detail:
                    EXHAUSTED.add(model)  # free daily quota used up: asking again today is pointless
                    break
                if e.code in (429, 500, 503) and attempt == 0 and not tools:
                    time.sleep(5)
                    continue
                break  # 400/403/404 or second failure: next model
            except Exception as e:  # timeout, network
                last = "%s: %s" % (model, e)
                break
    raise RuntimeError(last or "all Gemini Flash models are at their free daily limit")


def generate_json(prompt, schema, **kw):
    text, _ = generate(prompt, schema=schema, **kw)
    return parse_json(text)


def parse_json(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"(\[.*\]|\{.*\})", text, re.S)
        if m:
            return json.loads(m.group(1))
        raise
