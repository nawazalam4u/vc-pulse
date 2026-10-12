"""Gemini Flash through the institute's OpenRouter gateway (OPENROUTER_API_KEY).

Rules (from the course's key sheet): only google/ models; Google's own infrastructure serves every request
(provider.only = google-vertex / google-ai-studio, no fallbacks to other vendors); key only in an environment
variable; retry 429/5xx with backoff up to 3 times; stop on 402 (out of credits).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "google/gemini-3.7-flash,google/gemini-3.8-flash,google/gemini-3.5-flash-lite").split(",") if m.strip()]
DRAFT_MODELS = ["google/gemini-3.5-flash-lite", "google/gemini-3.7-flash"]  # cheapest model that writes a good email
PROVIDER = {"only": ["google-vertex", "google-ai-studio"], "allow_fallbacks": False}
LAST = {"model": None}
EXHAUSTED = set()   # kept for compatibility (OpenRouter has no per-model daily cap on this key)
USED = {}           # model -> successful calls (stored in the run log)
COST = {"usd": 0.0, "tokens": 0}  # summed from OpenRouter's usage field


class OutOfCredits(RuntimeError):
    pass


def configured():
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def _schema(s):
    """Gemini-style schema (OBJECT/ARRAY/STRING) -> strict JSON Schema for OpenRouter structured outputs."""
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            out[k] = v.lower() if k == "type" and isinstance(v, str) else _schema(v)
        if out.get("type") == "object":
            out["additionalProperties"] = False
            out.setdefault("required", list(out.get("properties", {})))
        return out
    if isinstance(s, list):
        return [_schema(x) for x in s]
    return s


def _call(body, timeout):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json",
        "HTTP-Referer": "https://vc-pulse-lime.vercel.app", "X-Title": "VC Pulse"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def generate(prompt, schema=None, system=None, temperature=0.2, timeout=90, tools=None, models=None):
    """Returns (text, raw_response). Tries each Google model in turn; backoff retries on 429/5xx."""
    if tools:
        raise RuntimeError("Google Search grounding is not available through this gateway")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    last = None
    for model in models or MODELS:
        body = {"model": model, "messages": messages, "temperature": temperature, "provider": PROVIDER,
                "reasoning": {"effort": "low"}, "usage": {"include": True}}
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "result", "strict": True, "schema": _schema(schema)}}
        for attempt in range(4):  # first try + 3 retries
            try:
                resp = _call(body, timeout)
                if resp.get("error"):
                    raise RuntimeError("%s: %s" % (model, str(resp["error"])[:160]))
                text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                if not text.strip():
                    raise RuntimeError("%s: empty reply" % model)
                u = resp.get("usage") or {}
                # with the institute's bring-your-own-key setup the real Google cost is in cost_details
                COST["usd"] += float(u.get("cost") or (u.get("cost_details") or {}).get("upstream_inference_cost") or 0)
                COST["tokens"] += int(u.get("total_tokens") or 0)
                LAST["model"] = model
                USED[model] = USED.get(model, 0) + 1
                return text, resp
            except urllib.error.HTTPError as e:
                detail = e.read().decode()[:200]
                last = "%s %s: %s" % (model, e.code, detail)
                if e.code == 402:
                    raise OutOfCredits("OpenRouter credits are used up (402). Top up the key, then run again.")
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(2 ** attempt * 2)  # 2s, 4s, 8s
                    continue
                break  # 400/401/403/404: try the next model
            except OutOfCredits:
                raise
            except Exception as e:  # timeout, network, empty reply
                last = "%s: %s" % (model, str(e)[:160])
                if attempt < 1:
                    continue
                break
    raise RuntimeError(last or "no Google model available on OpenRouter")


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
