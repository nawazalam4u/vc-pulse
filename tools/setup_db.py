"""One-time database setup (safe to re-run): tables, the two least-privilege logins, their grants.
Reads DATABASE_URL (owner) from .env; appends ENGINE_/FOUNDER_DATABASE_URL to .env if they are new.
Usage: python3 -I tools/setup_db.py"""
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))


def load_env():
    p = os.path.join(ROOT, ".env")
    for line in open(p):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            os.environ.setdefault(k, v)


def split_sql(text):
    lines = [l for l in text.splitlines() if not l.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


load_env()
import _db  # noqa: E402

for s in split_sql(open(os.path.join(ROOT, "db/schema.sql")).read()):
    _db.q(s, role="owner")
print("tables ready")

new_env = []
owner = os.environ["DATABASE_URL"]
for role, var in (("pulse_engine", "ENGINE_DATABASE_URL"), ("pulse_founder", "FOUNDER_DATABASE_URL")):
    exists = _db.q("select 1 from pg_roles where rolname = $1", [role], role="owner")
    if exists and os.environ.get(var):
        continue
    pw = secrets.token_urlsafe(24)
    if exists:
        _db.q("alter role %s with login password '%s'" % (role, pw), role="owner")
    else:
        _db.q("create role %s with login password '%s'" % (role, pw), role="owner")
    scheme, rest = owner.split("://", 1)
    new_env.append("%s=%s://%s:%s@%s" % (var, scheme, role, pw, rest.split("@", 1)[1]))
    print("login ready:", role)

for s in split_sql(open(os.path.join(ROOT, "db/roles.sql")).read()):
    _db.q(s, role="owner")
print("grants applied")

if new_env:
    with open(os.path.join(ROOT, ".env"), "a") as f:
        f.write("\n".join(new_env) + "\n")
    print("wrote", ", ".join(l.split("=")[0] for l in new_env), "to .env")
