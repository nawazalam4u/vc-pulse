"""Optional: push the twice-weekly brief to Vikram on Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)."""
import json
import os
import urllib.request

import _db

APP = os.environ.get("APP_URL", "https://vc-pulse-lime.vercel.app")


def configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def brief_text():
    hot = _db.q("select name, firm, follow_up_score, recommended_action from vcs where recommended_action like 'REACH OUT%' "
                "or recommended_action like 'NUDGE%' order by follow_up_score desc limit 8")
    warm = _db.q("select count(*) as n from vcs where recommended_action like 'WARM%'")[0]["n"]
    quiet = _db.q("select count(*) as n from vcs where recommended_action like 'PARK%'")[0]["n"]
    lines = ["VC Pulse - your pipeline is up to date", ""]
    if hot:
        lines.append("Worth reaching out this week:")
        for r in hot:
            lines.append("- %s (%s) %s/100: %s" % (r["name"], r["firm"], r["follow_up_score"],
                                                   r["recommended_action"].split(" · ", 1)[-1][:140]))
    else:
        lines.append("Nobody is a must-contact this week.")
    lines += ["", "%s warm, %s quiet (don't spend energy there)." % (warm, quiet), APP]
    return "\n".join(lines)


def send_brief(run_id=None):
    if not configured():
        return "not configured"
    body = json.dumps({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": brief_text(),
                       "disable_web_page_preview": True}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % os.environ["TELEGRAM_BOT_TOKEN"],
                                 data=body, headers={"content-type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return "sent"
    except Exception as e:
        return "failed: %s" % str(e)[:80]
