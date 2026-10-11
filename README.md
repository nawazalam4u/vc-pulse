# VC Pulse: VC fundraising pipeline intelligence

**Live:** https://vc-pulse-lime.vercel.app · **How it works / course brief:** https://vc-pulse-lime.vercel.app/brief

Vikram is raising a Seed round for a B2B logistics SaaS and tracks 50 VCs in a table. Twice a week (Monday and Thursday, 07:00 IST) VC Pulse checks every investor against **live public data from the last 30 days**: news, interviews, deals, blog posts and podcasts. **Gemini Flash** judges each item, and plain code turns that into a follow-up score and a recommended action. It updates **only four signal columns** in his table. His contact history and notes are protected by the database itself.

```
Vercel Cron (Mon/Thu 07:00 IST) or "Refresh now"
  -> Vikram's table (Neon Postgres, 50 investors)
  -> 5 live sources per investor (Google News x2, their blog RSS, Apple Podcasts, Gemini search when available)
  -> keep items with a link + source date <= 30 days
  -> Gemini Flash (JSON schema): is it really them? invested / wrote / spoke / event? fit to logistics 0-3? hook
  -> code: follow-up score 0-100 + action (REACH OUT, NUDGE, WARM, WAIT, LOW, PARK)
  -> UPDATE vcs SET last_signal_date, signal_summary, follow_up_score, recommended_action   (login: pulse_engine)
  -> dashboard + evidence + Gemini email draft (Vikram sends it himself)
```

## The notes guarantee
| Login | May update | Used by |
|---|---|---|
| `pulse_engine` | `last_signal_date, signal_summary, follow_up_score, recommended_action` | the signal engine (cron + Refresh) |
| `pulse_founder` | `name, firm, thesis, region, status, last_contact_date, contact_history, notes, feed_url` | Vikram's edit screen |
| owner | everything | setup scripts only; **not** stored on Vercel |

See `db/roles.sql`. Every run stores an MD5 fingerprint of Vikram's columns before and after. The **Notes guard** tab has a live "attack my own database" button.

## Project layout
```
api/_engine.py    gather -> judge -> score -> write (the core)
api/_sources.py   the live public sources (no logins, no LinkedIn/X scraping)
api/_gemini.py    Gemini Flash over HTTPS (JSON schema, model fallback, retries)
api/_db.py        Neon SQL-over-HTTP with the two least-privilege logins
api/run.py        "Refresh now", driven in batches by the browser (live progress)
api/cron.py       Vercel Cron entry point (all 50 investors, then optional Telegram brief)
api/pipeline.py, vc.py, proof.py, draft.py, health.py
db/schema.sql, db/roles.sql     plain Postgres: runs the same on Neon or Supabase
public/           the dashboard (index.html) and the course brief (brief.html)
tests/            scoring rules (offline) and permissions (live database)
tools/            setup_db.py (tables + logins), seed.py (Vikram's 50 investors)
```

## Run it yourself
```bash
python3 -I tools/setup_db.py     # needs DATABASE_URL (owner) in .env; creates tables + the two logins
python3 -I tools/seed.py         # loads the 50 investors through the founder login
python3 dev_server.py            # http://localhost:3000
python3 -I tests/test_scoring.py && python3 -I tests/test_guard.py
```

**Vercel environment variables:** `GEMINI_API_KEY`, `ENGINE_DATABASE_URL`, `FOUNDER_DATABASE_URL`, `DASHBOARD_KEY` (Vikram's editor key: open `/#key=...` once), `CRON_SECRET` (Vercel Cron sends it), optional `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, optional `GEMINI_MODEL`.

The investors, firms and theses are real (verified Oct 2026) and all signals are live. Vikram, his company "Haulr" and his contact notes are illustrative. Built for MESA Cohort C4, *AI and its Applications*: all AI is Gemini Flash.
