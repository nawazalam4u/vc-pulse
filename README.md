# VC Pulse: VC fundraising pipeline intelligence

**Live:** https://vc-pulse-lime.vercel.app · **How it works / course brief:** https://vc-pulse-lime.vercel.app/brief

Vikram is raising a Seed round for a B2B logistics SaaS and tracks 50 VCs in a table. Twice a week (Monday and Thursday, 07:00 IST) VC Pulse checks every investor against **live public data from the last 30 days**: news, interviews, deals, blog posts and podcasts. **Gemini Flash** judges each item, and plain code turns that into a follow-up score and a recommended action. It updates **only four signal columns** in his table. His contact history and notes are protected by the database itself.

```
Vercel Cron (Mon/Thu 07:00 IST) or "Refresh now"
  -> Vikram's table (Neon Postgres, 50 investors)
  -> 5 live sources per investor (Google News x2, their blog RSS, Apple Podcasts, Gemini search when available)
  -> keep items with a link + source date <= 30 days
  -> Gemini Flash (JSON schema): is it really them? what does it MEAN for Vikram's startup (thesis / deploying / complement / visible / overlap)? why it matters, geography/stage fit, hook
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

## Quality: measured, tested, audited
- **Accuracy** (`tests/eval_judge.py`, 57 hand-labelled live items in `data/eval_gold.json`): attribution precision **100%**, recall **85-89%** (varies by run), accuracy **93-95%**; logistics label 100%. Measured on the fallback model (worst case).
- **Tests:** `tests/test_scoring.py` (22 rule checks, offline) · `tests/test_inputs.py` (9 input rules) · `tests/test_guard.py` (28 live permission checks).
- **Safeguards:** evidence must name the investor; blog posts are author-checked; one event = one signal; hooks only from kept evidence; any source/AI failure keeps the last verdict (run marked `partial`); one run at a time (unique index) with HMAC run tickets; cron has priority and a 200 s budget; CSP and http(s)-only links; rate limits on public AI actions.

## Personalisation
- **LinkedIn without scraping:** an "in" button per investor opens the profile link Vikram saved (his own protected column, validated as `linkedin.com/in/...`) or LinkedIn's people search in his browser. Nothing is fetched from LinkedIn.
- **Your pitch** (`/api/pitch`): one-liner, traction and ask, saved through the founder login and used by every draft.
- **Drafts** return an email (Copy / Open in Gmail, never sent automatically) and a LinkedIn note under 300 characters.

## Project layout
```
api/_engine.py    gather -> judge -> score -> write (the core)
api/_sources.py   the live public sources (no logins, no LinkedIn/X scraping)
api/_gemini.py    Gemini Flash via the institute's OpenRouter gateway (Google models + Google infrastructure only, JSON schema, retries, cost)
api/_db.py        Neon SQL-over-HTTP with the two least-privilege logins
api/run.py        "Refresh now", driven in batches by the browser (live progress)
api/cron.py       Vercel Cron entry point (all 50 investors, then optional Telegram brief)
api/pipeline.py, vc.py, proof.py, draft.py, health.py
db/schema.sql, db/roles.sql     plain Postgres: runs the same on Neon or Supabase
public/           the dashboard (index.html) and the course brief (brief.html)
tests/            scoring rules (offline), permissions (live database), AI accuracy evaluation
docs/             components map, nine checks, study guide (PDF)
tools/            setup_db.py (tables + logins), seed.py (Vikram's 50 investors)
```

## Run it yourself
```bash
python3 -I tools/setup_db.py     # needs DATABASE_URL (owner) in .env; creates tables + the two logins
python3 -I tools/seed.py         # loads the 50 investors through the founder login
python3 dev_server.py            # http://localhost:3000
python3 -I tests/test_scoring.py && python3 -I tests/test_guard.py
```

**Vercel environment variables:** `OPENROUTER_API_KEY` (the institute's key; Google models only), `ENGINE_DATABASE_URL`, `FOUNDER_DATABASE_URL`, `DASHBOARD_KEY` (Vikram's editor key: open `/#key=...` once), `CRON_SECRET` (Vercel Cron sends it), optional `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, optional `GEMINI_MODEL`.

The investors, firms and theses are real (verified Oct 2026) and all signals are live. Vikram and his contact notes are illustrative (the brief doesn't name his company, so we call it "Vikram's startup"). Built for MESA Cohort C4, *AI and its Applications*: all AI is Gemini Flash.
