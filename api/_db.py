"""Neon Postgres over HTTPS (Neon's SQL-over-HTTP endpoint), so no database driver is needed.

Three logins, each with only the rights it needs (see db/roles.sql):
  engine  -> ENGINE_DATABASE_URL   the signal robot: may write ONLY the 4 signal columns
  founder -> FOUNDER_DATABASE_URL  Vikram's edit screen: may write ONLY his own columns
  owner   -> DATABASE_URL          setup scripts only, never used by the web app
"""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

ENV = {"engine": "ENGINE_DATABASE_URL", "founder": "FOUNDER_DATABASE_URL", "owner": "DATABASE_URL"}


class DBError(RuntimeError):
    pass


def configured(role="engine"):
    return bool(os.environ.get(ENV[role]))


def _post(role, payload):
    cs = os.environ[ENV[role]]
    req = urllib.request.Request(
        "https://%s/sql" % urlparse(cs).hostname,
        data=json.dumps(payload, default=str).encode(),
        headers={"Neon-Connection-String": cs, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            msg = json.loads(body).get("message", body)
        except ValueError:
            msg = body
        raise DBError(msg[:300])


def q(sql, params=(), role="engine"):
    """Run one statement, return rows as dicts."""
    return _post(role, {"query": sql, "params": list(params)}).get("rows", [])


def tx(statements, role="engine"):
    """Run several statements in ONE transaction: all succeed or none do."""
    if not statements:
        return []
    res = _post(role, {"queries": [{"query": s, "params": list(p)} for s, p in statements]})
    return [r.get("rows", []) for r in res.get("results", [])]
