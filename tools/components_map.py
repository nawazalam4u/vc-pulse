"""Draws the Components Map (swimlanes: actors x Trigger/Input/Context/Processing/AI/Output) as SVG + HTML.
Usage: python3 -I tools/components_map.py   -> docs/components-map.svg, docs/components-map-grid.html"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W0, CW, HY, RY, RH = 180, 236, 74, 132, 150
COLS = ["Trigger", "Input", "Context", "Processing", "AI", "Output"]
ROWS = [("Founder", "(Vikram · User)", "#eef4ff"), ("Scheduler", "(Vercel Cron)", "#f4f0ff"),
        ("System", "(Python backend on Vercel)", "#fff8e6"), ("Live data", "(News RSS · blogs · podcasts)", "#eafaf1"),
        ("AI Model", "(Gemini Flash)", "#fdeef5"), ("Database", "(Neon Postgres)", "#eaf6fb")]
W = W0 + CW * 6 + 20
H = RY + RH * 6 + 70
BW, BH = 204, 104
h, v = BW / 2, BH / 2
out = []


def cx(c):
    return W0 + CW * c + CW / 2


def cy(r):
    return RY + RH * r + RH / 2


def box(c, r, lines, stroke, fill):
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s" stroke="%s" stroke-width="2.4"/>'
               % (cx(c) - h, cy(r) - v, BW, BH, fill, stroke))
    y0 = cy(r) - (len(lines) - 1) * 9.5
    for k, t in enumerate(lines):
        out.append('<text x="%d" y="%.1f" text-anchor="middle" font-size="13.4"%s fill="#14122b">%s</text>'
                   % (cx(c), y0 + k * 19 + 4, ' font-weight="700"' if k == 0 else '', t))


def arrow(pts, label=None, lx=0, ly=0):
    d = "M" + " L".join("%.1f %.1f" % p for p in pts)
    out.append('<path d="%s" fill="none" stroke="#1d2a5b" stroke-width="2" stroke-dasharray="7 5" marker-end="url(#a)"/>' % d)
    if label:
        out.append('<text x="%d" y="%d" font-size="12" font-style="italic" fill="#3b4a7a">%s</text>' % (lx, ly, label))


out += ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'font-family="-apple-system,Helvetica,Arial,sans-serif">' % (W, H, W, H),
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
        '<path d="M0 0L10 5L0 10z" fill="#1d2a5b"/></marker></defs>', '<rect width="100%" height="100%" fill="#fff"/>',
        '<text x="%d" y="44" text-anchor="middle" font-size="28" font-weight="700" fill="#16224f">'
        'VC Pulse · VC Fundraising Pipeline Intelligence — Components Map</text>' % (W / 2),
        '<rect x="10" y="%d" width="%d" height="58" rx="8" fill="#16224f"/>' % (HY, W - 20),
        '<text x="%d" y="%d" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">Actor</text>' % (10 + (W0 - 10) / 2, HY + 36)]
for i, c in enumerate(COLS):
    out.append('<text x="%d" y="%d" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">%s</text>' % (cx(i), HY + 36, c))
for j, (a, sub, bg) in enumerate(ROWS):
    y = RY + RH * j
    out += ['<rect x="%d" y="%d" width="%d" height="%d" fill="%s"/>' % (W0, y, CW * 6, RH, bg),
            '<rect x="10" y="%d" width="%d" height="%d" fill="#16224f"/>' % (y, W0 - 10, RH),
            '<text x="%d" y="%d" text-anchor="middle" font-size="19" font-weight="700" fill="#fff">%s</text>' % (10 + (W0 - 10) / 2, y + RH / 2 - 4, a),
            '<text x="%d" y="%d" text-anchor="middle" font-size="12.5" fill="#c9d3f2">%s</text>' % (10 + (W0 - 10) / 2, y + RH / 2 + 18, sub),
            '<line x1="10" y1="%d" x2="%d" y2="%d" stroke="#fff" stroke-width="2"/>' % (y, W - 10, y)]
for i in range(1, 6):
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#fff" stroke-width="2"/>' % (W0 + CW * i, RY, W0 + CW * i, RY + RH * 6))

P, B, G, O, K, R, T = (("#8b6cf6", "#efeaff"), ("#3b82f6", "#e8f0ff"), ("#22a565", "#e7f8ee"), ("#f59e0b", "#fff4dd"),
                       ("#e0408a", "#fde8f1"), ("#ef4444", "#ffe9e9"), ("#0e9fb8", "#e3f7fb"))
box(0, 0, ["Clicks “Refresh", "signals now”", "(optional, any time)"], *P)
box(0, 1, ["Cron fires", "Mon + Thu, 07:00 IST", "/api/cron (secret)", "one run at a time"], *P)
box(1, 0, ["Edits own columns:", "status, last contact,", "notes, contact history", "(pulse_founder login)"], *B)
box(1, 5, ["Reads Vikram's table", "50 VCs: name, firm,", "thesis, status,", "last contact date"], *B)
box(2, 3, ["Fetches last 30 days", "Google News: person", "Google News: firm deals", "blog RSS · podcasts"], *G)
box(3, 2, ["Filters & checks", "real link + date ≤ 30d", "de-dup · per-source caps", "outage → keep verdict"], *O)
box(4, 4, ["Gemini Flash judges", "who acted · what kind", "logistics fit 0-3 · event", "WHY it matters + hook"], *K)
box(4, 2, ["Code verifies AI", "names them? author?", "logistics word? conflict?", "1 event = 1 signal"], *O)
box(5, 2, ["Score 0-100 + action", "signal × fit × freshness", "+ thesis + timing", "REACH OUT … PARK"], *O)
box(5, 5, ["UPDATE only 4 columns", "last_signal_date · summary", "follow_up_score · action", "notes locked (pulse_engine)"], *T)
box(5, 0, ["Dashboard: who to", "pitch this week + why", "+ clickable evidence", "HUMAN GATE: Vikram sends"], *R)
box(5, 4, ["Email draft on request", "cites the real signal", "no invented traction", "(draft only, never sent)"], *K)

gap = CW / 2 - h - 7  # free lane between a box and the column border
arrow([(cx(0), cy(0) + v), (cx(0), cy(1) - v)], "manual run", cx(0) + 6, cy(0) + v + 26)
arrow([(cx(0) + h, cy(1)), (cx(1) - 40, cy(1)), (cx(1) - 40, cy(5) - v)], "auto run", cx(0) + h + 8, cy(1) - 8)
arrow([(cx(1) + 40, cy(0) + v), (cx(1) + 40, cy(5) - v)], "his edits only", cx(1) + 46, cy(2) - 40)
arrow([(cx(1) + h, cy(5)), (cx(2), cy(5)), (cx(2), cy(3) + v)], "50 investors", cx(1) + h + 8, cy(5) - 8)
arrow([(cx(2) + h, cy(3)), (cx(3) - 40, cy(3)), (cx(3) - 40, cy(2) + v)], "~400 items", cx(2) + h + 6, cy(3) - 8)
arrow([(cx(3) + 40, cy(2) + v), (cx(3) + 40, cy(4)), (cx(4) - h, cy(4))], "10 VCs per call", cx(3) + 46, cy(4) - 8)
arrow([(cx(4), cy(4) - v), (cx(4), cy(2) + v)], "JSON verdicts", cx(4) + 6, cy(3) + 4)
arrow([(cx(4) + h, cy(2)), (cx(5) - h, cy(2))])
arrow([(cx(5) + 40, cy(2) + v), (cx(5) + 40, cy(3)), (cx(5) + h + gap, cy(3)), (cx(5) + h + gap, cy(5) - v - 16),
       (cx(5) + 60, cy(5) - v - 16), (cx(5) + 60, cy(5) - v)], "writes", cx(5) + 46, cy(3) - 8)
arrow([(cx(5), cy(2) - v), (cx(5), cy(0) + v)], "shows", cx(5) + 6, cy(1))
arrow([(cx(5) - 50, cy(0) + v), (cx(5) - 50, cy(0) + v + 22), (cx(5) - h - gap, cy(0) + v + 22),
       (cx(5) - h - gap, cy(4) - v - 16), (cx(5) - 50, cy(4) - v - 16), (cx(5) - 50, cy(4) - v)],
      "clicks “Draft email”", cx(5) - 46, cy(4) - v - 22)
ly = RY + RH * 6 + 32
out += ['<text x="20" y="%d" font-size="13" fill="#3b4a7a">Dashed arrows = data flow. Only the founder login can change '
        'Vikram\'s columns; only the engine login can change the 4 signal columns (enforced by Postgres). '
        'Nothing is ever emailed automatically.</text>' % ly,
        '<text x="20" y="%d" font-size="13" fill="#3b4a7a">Live: vc-pulse-lime.vercel.app · Code: github.com/nawazalam4u/vc-pulse · '
        'Gemini 3.5 Flash → 3.5 Flash-Lite → 3.1 Flash-Lite (automatic fallback)</text>' % (ly + 22), '</svg>']
svg = "\n".join(out)
open(os.path.join(ROOT, "docs/components-map.svg"), "w").write(svg)
open(os.path.join(ROOT, "docs/components-map-grid.html"), "w").write(
    '<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;background:#fff}</style></head><body>%s</body></html>' % svg)
print("written", W, H)
