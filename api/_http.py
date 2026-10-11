import datetime as dt
import decimal
import hmac
import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _default(o):
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return float(o)
    return str(o)


def query(h):
    return {k: v[0] for k, v in parse_qs(urlparse(h.path).query).items()}


def body(h):
    n = int(h.headers.get("content-length") or 0)
    if n > 200_000:
        return {}
    try:
        return json.loads((h.rfile.read(n) if n else b"{}").decode() or "{}")
    except ValueError:
        return {}


def send(h, obj, status=200):
    b = json.dumps(obj, default=_default).encode()
    h.send_response(status)
    h.send_header("content-type", "application/json")
    h.send_header("cache-control", "no-store")
    h.send_header("content-length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


def has_key(h):
    """Vikram's key (DASHBOARD_KEY) unlocks editing. Sent as header x-pulse-key."""
    want = os.environ.get("DASHBOARD_KEY", "")
    got = h.headers.get("x-pulse-key", "")  # header only: keys never appear in URLs or logs
    return bool(want) and hmac.compare_digest(want.encode(), got.encode())


def is_cron(h):
    """Vercel Cron sends 'Authorization: Bearer <CRON_SECRET>'."""
    want = os.environ.get("CRON_SECRET", "")
    got = h.headers.get("authorization", "")
    return bool(want) and hmac.compare_digest(("Bearer " + want).encode(), got.encode())
