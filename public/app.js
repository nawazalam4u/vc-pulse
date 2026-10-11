/* VC Pulse front end: plain JavaScript, no build step. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- Vikram's key: a magic link like /#key=XXXX unlocks editing (stored only in this browser)
let KEY = "";
try {
  const m = location.hash.match(/key=([^&]+)/);
  if (m) { localStorage.setItem("pulseKey", decodeURIComponent(m[1])); history.replaceState(null, "", location.pathname); }
  KEY = localStorage.getItem("pulseKey") || "";
} catch (e) { /* private window: no editing */ }

async function api(path, opts = {}) {
  const headers = { "content-type": "application/json" };
  if (KEY) headers["x-pulse-key"] = KEY;
  const r = await fetch(path, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  let data = {};
  try { data = await r.json(); } catch (e) { data = { error: "Server returned " + r.status }; }
  if (!r.ok) throw Object.assign(new Error(data.error || "Request failed"), { status: r.status, data });
  return data;
}
function toast(msg, ms = 3200) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("on");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("on"), ms);
}

// ---------- helpers
const KIND = { invested: "💸 Invested", wrote: "✍️ Wrote", said: "🎙 Spoke", appeared: "🎤 Event", mentioned: "📰 In news", other: "• Other" };
const ORIGIN = { news: "News", firm_news: "Firm deals", blog: "Their blog", podcast: "Podcast", search: "Web search" };
const LANES = [
  { id: "hot", title: "🔥 Reach out this week", sub: "Fresh, on-topic signal + good timing", match: (a) => a === "REACH OUT" || a === "NUDGE" },
  { id: "warm", title: "🌤 Warm", sub: "Active. Worth it if you have bandwidth", match: (a) => a === "WARM" },
  { id: "wait", title: "⏳ Wait", sub: "You followed up recently: let it breathe", match: (a) => a === "WAIT" },
  { id: "park", title: "💤 Park", sub: "Quiet or off-topic: don't spend energy", match: (a) => a === "PARK" || a === "LOW" || !a },
];
const actTag = (a) => (a || "").split(" · ")[0];
const actText = (a) => (a || "Not scored yet. Press Refresh.").split(" · ").slice(1).join(" · ") || a;
function fmtDate(d) {
  if (!d) return "";
  const x = new Date(String(d).slice(0, 10) + "T00:00:00");
  return x.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
function ago(ts) {
  if (!ts) return "never";
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago";
  return Math.round(s / 86400) + " days ago";
}
function daysSince(d) { return d ? Math.floor((Date.now() - new Date(String(d).slice(0, 10) + "T00:00:00")) / 864e5) : null; }
function ring(score) {
  const v = Math.max(0, Math.min(100, score ?? 0)), c = 2 * Math.PI * 17;
  const col = v >= 55 ? "#ff5a36" : v >= 35 ? "#f5a400" : v >= 20 ? "#6d4aff" : "#a3a6b8";
  return `<div class="ring"><svg width="42" height="42"><circle cx="21" cy="21" r="17" stroke="#eeedf6" stroke-width="5" fill="none"/>
    <circle cx="21" cy="21" r="17" stroke="${col}" stroke-width="5" fill="none" stroke-linecap="round" stroke-dasharray="${(c * v) / 100} ${c}"/></svg><b>${score ?? "–"}</b></div>`;
}
function nextRun() {
  // Mon & Thu 07:00 IST = 01:30 UTC
  const now = new Date();
  for (let k = 0; k < 8; k++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + k, 1, 30));
    if ((d.getUTCDay() === 1 || d.getUTCDay() === 4) && d > now) return d;
  }
}

// ---------- state
let S = { vcs: [], runs: [], changes: {}, can_edit: false };
let filter = "all";

async function load(flashIds = []) {
  try {
    const d = await api("/api/pipeline");
    S = { ...d, changes: Object.fromEntries((d.changes || []).map((c) => [c.vc_id, c])) };
  } catch (e) {
    $("#board").innerHTML = `<div class="empty">Couldn't load the pipeline: ${esc(e.message)}</div>`;
    return;
  }
  $("#editPill").hidden = !S.can_edit;
  $("#csvInLbl").hidden = !S.can_edit;
  $("#editHint").textContent = S.can_edit ? "Editor mode: click your blue cells to edit. Changes save to the database instantly through the founder login."
    : "Read-only view. Vikram edits his blue columns through his private magic link.";
  renderHeader(); renderBoard(); renderTable(flashIds); renderRuns(); renderGuardRuns();
}

function renderHeader() {
  const h = +new Date().toLocaleString("en-GB", { hour: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });  // Vikram is in India
  $("#greet").textContent = (h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening") + ", Vikram.";
  $("#nVcs").textContent = S.vcs.length;
  const tags = S.vcs.map((v) => actTag(v.recommended_action));
  $("#sHot").textContent = tags.filter((t) => t === "REACH OUT" || t === "NUDGE").length;
  $("#sWarm").textContent = tags.filter((t) => t === "WARM").length;
  $("#sWait").textContent = tags.filter((t) => t === "WAIT").length;
  $("#sPark").textContent = tags.filter((t) => t === "PARK" || t === "LOW").length;
  $("#sScan").textContent = S.items_total ?? "–";
  const last = S.runs.find((r) => r.status === "done");
  $("#sSafe").textContent = last ? (last.notes_hash_before === last.notes_hash_after ? "100%" : "check") : "–";
  const nr = nextRun();
  $("#runMeta").innerHTML = (last ? `Updated ${ago(last.finished_at)} (${last.trigger === "cron" ? "auto run" : "manual run"})` : "Not run yet")
    + ` · next auto run ${nr.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })}, 7:00 IST`;
}

function sigChip(s) {
  return `<span class="chip ${esc(s.kind)}" title="${esc(s.title)}">${KIND[s.kind] || "•"} · ${fmtDate(s.published)}</span>`;
}
function deltaBadge(v) {
  const c = S.changes[v.id];
  if (!c || c.new_score == null) return "";
  if (c.old_score == null) return `<span class="delta new">new</span>`;
  const d = c.new_score - c.old_score;
  return d > 0 ? `<span class="delta up">▲${d}</span>` : d < 0 ? `<span class="delta down">▼${-d}</span>` : "";
}
function renderBoard() {
  const sorted = [...S.vcs].sort((a, b) => (b.follow_up_score ?? -1) - (a.follow_up_score ?? -1));
  $("#board").innerHTML = LANES.map((L) => {
    const items = sorted.filter((v) => L.match(actTag(v.recommended_action)));
    const show = L.id === "park" ? items.slice(0, 12) : items;
    return `<div class="lane"><h3>${L.title}<small>${items.length}</small></h3><div class="sub">${L.sub}</div>
      ${show.map((v) => `<div class="card ${L.id}" data-id="${v.id}">
        <div class="hd">${ring(v.follow_up_score)}<div style="min-width:0"><div class="nm">${esc(v.name)} ${deltaBadge(v)}</div><div class="fm">${esc(v.firm)}</div></div></div>
        <div class="act">${esc(actText(v.recommended_action))}</div>
        ${v.signals?.length ? `<div class="ev">${v.signals.slice(0, 3).map(sigChip).join("")}</div>` : ""}
      </div>`).join("") || `<div class="empty" style="padding:14px">Nobody here right now.</div>`}
      ${items.length > show.length ? `<div class="more">+ ${items.length - show.length} more in the Pipeline table</div>` : ""}
    </div>`;
  }).join("");
}

// ---------- table
const MINE = [["status", "Status"], ["last_contact_date", "Last contact"], ["contact_history", "Contact history"], ["notes", "Your notes"]];
function renderTable(flashIds = []) {
  const q = $("#q").value.trim().toLowerCase();
  let rows = [...S.vcs].sort((a, b) => (b.follow_up_score ?? -1) - (a.follow_up_score ?? -1));
  if (q) rows = rows.filter((v) => [v.name, v.firm, v.thesis, v.notes, v.contact_history, v.signal_summary].join(" ").toLowerCase().includes(q));
  if (filter === "hot") rows = rows.filter((v) => ["REACH OUT", "NUDGE"].includes(actTag(v.recommended_action)));
  else if (filter === "waiting_response") rows = rows.filter((v) => v.status === "waiting_response");
  else if (filter === "PARK") rows = rows.filter((v) => ["PARK", "LOW"].includes(actTag(v.recommended_action)));
  else if (filter !== "all") rows = rows.filter((v) => actTag(v.recommended_action) === filter);
  const ed = S.can_edit;
  $("#tbl").innerHTML = `<thead><tr class="grp"><th class="mine" colspan="6">🔒 Vikram's columns: the engine cannot write here</th><th class="sig" colspan="4">⚡ Signal columns: updated by VC Pulse every run</th></tr>
    <tr class="cols"><th class="mine">Investor</th><th class="mine">Thesis</th>${MINE.map(([, l]) => `<th class="mine">${l}</th>`).join("")}
    <th class="sig">Last signal</th><th class="sig">Signal summary</th><th class="sig">Score</th><th class="sig">Recommended action</th></tr></thead>
    <tbody>${rows.map((v) => `<tr data-id="${v.id}" class="${flashIds.includes(v.id) ? "flash" : ""}">
      <td class="mine nm" data-open="${v.id}">${esc(v.name)}<small>${esc(v.firm)}</small></td>
      <td class="mine"><div class="clip" style="max-width:200px">${esc(v.thesis)}</div></td>
      <td class="mine">${ed ? `<select data-f="status"><option value="yet_to_reach_out" ${v.status === "yet_to_reach_out" ? "selected" : ""}>Yet to reach out</option><option value="waiting_response" ${v.status === "waiting_response" ? "selected" : ""}>Waiting for response</option></select>`
        : (v.status === "waiting_response" ? "⏳ Waiting for response" : "✉️ Yet to reach out")}</td>
      <td class="mine" style="white-space:nowrap">${ed ? `<input type="date" data-f="last_contact_date" value="${esc((v.last_contact_date || "").slice(0, 10))}">` : (fmtDate(v.last_contact_date) || "–")}</td>
      <td class="mine"><div class="clip" ${ed ? `contenteditable="true" data-f="contact_history"` : ""}>${esc(v.contact_history)}</div></td>
      <td class="mine"><div class="clip" ${ed ? `contenteditable="true" data-f="notes"` : ""}>${esc(v.notes)}</div></td>
      <td class="sig" style="white-space:nowrap">${fmtDate(v.last_signal_date) || "–"}</td>
      <td class="sig"><div class="clip">${esc(v.signal_summary)}</div></td>
      <td class="sig"><span class="score">${v.follow_up_score ?? "–"}</span> ${deltaBadge(v)}</td>
      <td class="sig"><span class="tag ${esc(actTag(v.recommended_action).split(" ")[0])}">${esc(actTag(v.recommended_action) || "–")}</span><div class="clip" style="margin-top:4px">${esc(actText(v.recommended_action))}</div></td>
    </tr>`).join("")}</tbody>`;
}
async function saveCell(el) {
  const tr = el.closest("tr"), id = +tr.dataset.id, f = el.dataset.f;
  const value = el.tagName === "DIV" ? el.innerText.trim() : el.value;
  const v = S.vcs.find((x) => x.id === id);
  if ((v[f] ?? "") === value) return;
  try {
    await api("/api/vc", { method: "PATCH", body: JSON.stringify({ id, fields: { [f]: value } }) });
    v[f] = value;
    toast("Saved ✓ (founder login, your column only)");
  } catch (e) { toast("Not saved: " + e.message); }
}
$("#tbl").addEventListener("focusout", (e) => { if (e.target.matches("[contenteditable][data-f]")) saveCell(e.target); });
$("#tbl").addEventListener("change", (e) => { if (e.target.matches("select[data-f], input[data-f]")) saveCell(e.target); });
$("#tbl").addEventListener("click", (e) => { const o = e.target.closest("[data-open]"); if (o) openVc(+o.dataset.open); });
$("#q").addEventListener("input", () => renderTable());
$$(".fchip").forEach((b) => b.addEventListener("click", () => { $$(".fchip").forEach((x) => x.classList.remove("on")); b.classList.add("on"); filter = b.dataset.f; renderTable(); }));

// CSV export / import (Vikram's spreadsheet in and out)
const CSV_COLS = ["name", "firm", "thesis", "region", "status", "last_contact_date", "contact_history", "notes", "feed_url", "last_signal_date", "signal_summary", "follow_up_score", "recommended_action"];
$("#csvOut").addEventListener("click", () => {
  const q = (x) => `"${String(x ?? "").replace(/"/g, '""')}"`;
  const csv = [CSV_COLS.join(","), ...S.vcs.map((v) => CSV_COLS.map((c) => q(v[c])).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "vc-pipeline-" + new Date().toISOString().slice(0, 10) + ".csv"; a.click();
});
function parseCsv(text) {
  const rows = []; let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch; }
    else if (ch === '"') q = true; else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const head = rows.shift().map((h) => h.trim().toLowerCase().replace(/\s+/g, "_"));
  return rows.filter((r) => r.some((c) => c.trim())).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}
$("#csvIn").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const rows = parseCsv(await f.text());
    const r = await api("/api/vc", { method: "POST", body: JSON.stringify({ rows }) });
    toast(`Imported. ${r.added} rows sent; existing investors are never overwritten.`); load();
  } catch (err) { toast("Import failed: " + err.message); }
  e.target.value = "";
});

// ---------- drawer: one investor
async function openVc(id) {
  const dr = $("#drawer");
  $("#scrim").classList.add("on"); dr.classList.add("on");
  dr.innerHTML = `<div class="dh"><h2>Loading…</h2><button class="x" onclick="closeVc()">×</button></div><div class="db"><div class="skel"></div><div class="skel"></div></div>`;
  let d;
  try { d = await api("/api/vc?id=" + id); } catch (e) { dr.innerHTML = `<div class="db">${esc(e.message)}</div>`; return; }
  const v = d.vc, kept = d.signals.filter((s) => s.about_vc && !s.dup && +s.points >= 4), rej = d.signals.filter((s) => !(s.about_vc && +s.points >= 4));
  const also = d.signals.filter((s) => s.about_vc && s.dup);
  const fresh = kept.filter((s) => daysSince(s.published) <= 30);
  const max = Math.max(...d.breakdown.map((b) => Math.abs(b[1])), 1);
  const hist = [...d.history].reverse();
  const spark = hist.length > 1 ? (() => {
    const w = 540, h = 46, pts = hist.map((x, i) => [10 + (i * (w - 20)) / (hist.length - 1), h - 6 - ((x.new_score ?? 0) / 100) * (h - 12)]);
    return `<svg class="spark" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="#6d4aff" stroke-width="2.5" points="${pts.map((p) => p.join(",")).join(" ")}"/>${pts.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="#6d4aff"/>`).join("")}</svg>`;
  })() : `<p class="meta" style="color:var(--ink2);margin:0">History builds up with every run (twice a week).</p>`;
  dr.innerHTML = `<div class="dh">${ring(v.follow_up_score)}<div><h2>${esc(v.name)}</h2><div class="fm" style="color:var(--ink2)">${esc(v.firm)} · ${esc(v.region || "")}</div></div><button class="x" onclick="closeVc()">×</button></div>
  <div class="db">
    <div class="box"><h4><span class="tag ${esc(actTag(v.recommended_action).split(" ")[0])}">${esc(actTag(v.recommended_action))}</span> Recommended action</h4>
      <div style="font-size:15px">${esc(actText(v.recommended_action))}</div>
      <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary sm" id="draftBtn" ${fresh.length ? "" : "disabled title='No fresh signal = no honest hook'"}>✉️ Draft the email with Gemini</button></div>
      <div id="draftOut"></div></div>
    <div class="box"><h4>⚡ Signal summary</h4><div>${esc(v.signal_summary || "–")}</div></div>
    <div class="box"><h4>🧮 Why ${v.follow_up_score ?? "–"}/100: the score maths</h4>
      ${d.breakdown.map(([label, pts]) => `<div class="bar"><div class="t">${esc(label)}<div class="fill ${pts < 0 ? "neg" : ""}" style="width:${(Math.abs(pts) / max) * 100}%"></div></div><b>${pts > 0 ? "+" : ""}${pts}</b></div>`).join("")}
      <details style="margin-top:8px"><summary>How each signal is worth points</summary><p style="font-size:12.5px;color:var(--ink2)">points = type weight (invested 40, wrote 34, spoke 30, event 26, in news 14) × topic fit (logistics 1.0, adjacent B2B 0.6, general 0.3) × who acted (the partner 1.0, only their firm 0.85) × freshness (full for 7 days, fading to 0.4 at day 30). Best signal + 40% of the 2nd + 20% of the 3rd, capped at 70. Then thesis fit (up to +15) and timing from <i>your</i> status and last-contact date (−30 to +10). Gemini judges what each item is; plain code does the arithmetic, so the same evidence always gives the same score.</p></details></div>
    <div class="box"><h4>🔎 Evidence (last 30 days): ${fresh.length} signal${fresh.length === 1 ? "" : "s"}</h4>
      ${fresh.length ? fresh.map((s) => `<div class="evi"><div class="d">${fmtDate(s.published)}<br><span class="chip ${esc(s.kind)}" style="margin-top:4px">${KIND[s.kind] || ""}</span></div><div><a class="t" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)} ↗</a><div class="s">${esc(s.summary || "")}</div><div class="s">${esc(s.source)} · via ${ORIGIN[s.origin] || s.origin} · fit ${s.relevance}/3 · ${(+s.points).toFixed(1)} pts</div></div></div>`).join("")
        : `<p style="margin:0;color:var(--ink2)">No qualifying public activity in the last 30 days. That's useful too: don't spend energy here this week.</p>`}
      ${also.length ? `<details style="margin-top:8px"><summary>Same events, other outlets: ${also.length} (counted once)</summary>${also.slice(0, 20).map((s) => `<div class="evi rej"><div class="d">${fmtDate(s.published)}</div><div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a><div class="s">${esc(s.source)}</div></div></div>`).join("")}</details>` : ""}
      ${rej.length ? `<details style="margin-top:8px"><summary>Filtered out by Gemini: ${rej.length} item${rej.length === 1 ? "" : "s"} (not about them, or not relevant)</summary>${rej.slice(0, 25).map((s) => `<div class="evi rej"><div class="d">${fmtDate(s.published)}</div><div><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a><div class="s">${esc(s.source)} · via ${ORIGIN[s.origin] || s.origin}</div></div></div>`).join("")}</details>` : ""}
    </div>
    <div class="box"><h4>🔒 Your columns (never touched by the engine)</h4><div class="kv">
      <span>Status</span><div>${v.status === "waiting_response" ? "⏳ Waiting for response" : "✉️ Yet to reach out"}</div>
      <span>Last contact</span><div>${fmtDate(v.last_contact_date) || "–"}${v.last_contact_date ? ` (${daysSince(v.last_contact_date)} days ago)` : ""}</div>
      <span>Contact history</span><div>${esc(v.contact_history || "–")}</div>
      <span>Your notes</span><div>${esc(v.notes || "–")}</div>
      <span>Thesis</span><div>${esc(v.thesis || "–")}</div>
      ${v.feed_url ? `<span>Blog feed</span><div><a href="${esc(v.feed_url)}" target="_blank" rel="noopener">${esc(v.feed_url)}</a></div>` : ""}
    </div></div>
    <div class="box"><h4>📈 Score across runs</h4>${spark}</div>
  </div>`;
  const db = $("#draftBtn");
  if (db) db.addEventListener("click", async () => {
    db.disabled = true; db.textContent = "Gemini is writing…";
    try {
      const r = await api("/api/draft", { method: "POST", body: JSON.stringify({ id }) });
      $("#draftOut").innerHTML = `<div class="draft" style="margin-top:10px">${esc(r.draft)}</div><div style="display:flex;gap:8px;margin-top:8px;align-items:center"><button class="btn ghost sm" id="cpy">Copy</button><span class="meta" style="color:var(--ink2)">Draft only: nothing is sent. You edit and send it yourself. (${esc(r.model)})</span></div>`;
      $("#cpy").onclick = () => { navigator.clipboard.writeText(r.draft); toast("Copied"); };
    } catch (e) { $("#draftOut").innerHTML = `<p style="color:var(--bad)">${esc(e.message)}</p>`; }
    db.disabled = false; db.textContent = "✉️ Draft again";
  });
}
function closeVc() { $("#scrim").classList.remove("on"); $("#drawer").classList.remove("on"); }
$("#scrim").addEventListener("click", closeVc);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeVc(); });
$("#board").addEventListener("click", (e) => { const c = e.target.closest(".card"); if (c) openVc(+c.dataset.id); });

// ---------- runs
function renderRuns() {
  $("#runs").innerHTML = S.runs.map((r) => {
    const dur = r.finished_at ? Math.round((new Date(r.finished_at) - new Date(r.started_at)) / 1000) + "s" : "";
    const safe = r.notes_hash_after ? (r.notes_hash_before === r.notes_hash_after ? `<span class="pill" style="background:var(--ok2);color:var(--ok)">🔒 notes untouched</span>` : `<span class="pill" style="background:var(--warm2);color:#9a6700">notes edited during run</span>`) : `<span class="pill" style="background:var(--park2)">${esc(r.status)}</span>`;
    return `<div class="run"><div><b>Run #${r.id}</b><span>${new Date(r.started_at).toLocaleString("en-IN", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · ${r.trigger === "cron" ? "⏰ auto" : "👆 manual"} ${dur}</span></div>
      <div><b>${r.vcs_done}/${r.vcs_total}</b><span>investors</span></div><div><b>${r.items_scanned}</b><span>items checked</span></div>
      <div><b>${r.signals_kept}</b><span>signals kept</span></div><div><b style="color:var(--hot)">${r.hot_count}</b><span>reach out</span></div>
      <div><b style="color:var(--park)">${r.quiet_count}</b><span>quiet</span></div><div>${safe}</div></div>`;
  }).join("") || `<div class="empty">No runs yet.</div>`;
}
function renderGuardRuns() {
  $("#gRuns").innerHTML = S.runs.filter((r) => r.notes_hash_after).slice(0, 6).map((r) =>
    `<div class="attempt ${r.notes_hash_before === r.notes_hash_after ? "blocked" : "open"}"><div class="ic">${r.notes_hash_before === r.notes_hash_after ? "✅" : "✏️"}</div><div><b>Run #${r.id}</b> · ${ago(r.finished_at)}<div class="hash">before ${esc(r.notes_hash_before)}<br>after&nbsp; ${esc(r.notes_hash_after)}</div></div></div>`).join("") || `<p class="meta">No completed runs yet.</p>`;
}

// ---------- guard
async function loadGuard() {
  try {
    const d = await api("/api/proof");
    const all = ["name", "firm", "thesis", "region", "status", "last_contact_date", "contact_history", "notes", "feed_url", "last_signal_date", "signal_summary", "follow_up_score", "recommended_action"];
    const draw = (can) => all.map((c) => `<span class="col ${can.includes(c) ? "yes" : "no"}">${c}</span>`).join("");
    $("#gEng").innerHTML = draw(d.engine_can_update); $("#gFou").innerHTML = draw(d.founder_can_update);
  } catch (e) { $("#gEng").textContent = e.message; }
}
$("#tamperBtn").addEventListener("click", async () => {
  const b = $("#tamperBtn"); b.disabled = true; b.textContent = "Attacking…";
  const pick = S.vcs.find((v) => v.notes) || S.vcs[0];
  try {
    const d = await api("/api/proof", { method: "POST", body: JSON.stringify({ id: pick?.id }) });
    $("#tamperOut").innerHTML = `<p style="margin:14px 0 4px">Target: <b>${esc(d.vc.name)}</b>. Vikram's note: <i>"${esc(d.vc.notes || "(empty)")}"</i></p>` +
      d.tests.map((t) => `<div class="attempt ${t.blocked ? "blocked" : "open"}"><div class="ic">${t.blocked ? "🛡" : "⚠️"}</div><div><b>${esc(t.who)}</b> tries to ${esc(t.tries)}<br><code>${esc(t.sql)}</code><br>
        <span style="color:${t.blocked ? "var(--ok)" : "var(--bad)"};font-weight:700">${t.blocked ? "BLOCKED by Postgres: " : ""}${esc(t.message)}</span></div></div>`).join("") +
      `<p class="big-ok" style="margin-top:12px">${d.unchanged ? "✅ Fingerprint unchanged: every note is exactly as Vikram left it." : "⚠️ Fingerprint changed"}</p>`;
  } catch (e) { $("#tamperOut").innerHTML = `<p style="color:var(--bad)">${esc(e.message)}</p>`; }
  b.disabled = false; b.textContent = "Attack it again";
});

// ---------- run now (browser drives small batches so you can watch)
$("#runBtn").addEventListener("click", runNow);
async function runNow() {
  const btn = $("#runBtn"); btn.disabled = true;
  const feed = $("#mFeed"); feed.innerHTML = ""; $("#mBar").style.width = "0";
  $("#radar").classList.remove("done"); $("#mClose").hidden = true;
  $("#mTitle").textContent = "Scanning your pipeline…";
  $("#mSub").textContent = "Fetching news, deals, blogs and podcasts for each investor; Gemini Flash judges every item.";
  $("#runModal").classList.add("on");
  const line = (html) => { feed.insertAdjacentHTML("afterbegin", `<div class="ln">${html}</div>`); };
  let start;
  try { start = await api("/api/run", { method: "POST", body: JSON.stringify({ action: "start" }) }); }
  catch (e) {
    $("#mTitle").textContent = e.status === 429 ? "Already fresh ✨" : "Couldn't start";
    $("#mSub").textContent = e.status === 429 ? "Tip: Vikram's magic link can refresh any time." : "";
    line(`<span>${esc(e.message)}</span>`); $("#radar").classList.add("done"); $("#mClose").hidden = false; btn.disabled = false; return;
  }
  if (!start.fresh) {
    $("#mTitle").textContent = "A run is already in progress"; line(`<span>Run #${start.run} is being processed (probably the scheduled one). Check back in a minute.</span>`);
    $("#radar").classList.add("done"); $("#mClose").hidden = false; btn.disabled = false; return;
  }
  const ids = start.ids, batches = [];
  for (let i = 0; i < ids.length; i += 10) batches.push(ids.slice(i, i + 10));
  let done = 0, hot = 0, kept = 0, scanned = 0; const touched = [];
  $("#mSub").textContent = `Run #${start.run} · ${ids.length} investors · 5 live sources each · Gemini Flash judges every item`;
  const worker = async () => {
    while (batches.length) {
      const b = batches.shift();
      line(`<span>📡 Scanning ${b.map((i) => esc(start.names[i])).join(", ")}</span><small>…</small>`);
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const r = await api("/api/run", { method: "POST", body: JSON.stringify({ action: "batch", run: start.run, ids: b }) });
          r.report.forEach((x) => {
            touched.push(x.id);
            if (x.skipped) { line(`<span>${esc(x.name)}: AI busy, kept last verdict</span><small>skipped</small>`); return; }
            scanned += x.scanned; kept += x.kept; if (["REACH OUT", "NUDGE"].includes(x.action)) hot++;
            const d = x.old == null ? "" : x.score > x.old ? ` ▲${x.score - x.old}` : x.score < x.old ? ` ▼${x.old - x.score}` : "";
            line(`<span><b>${esc(x.name)}</b> <small>${esc(x.firm)} · ${x.scanned} items → ${x.kept} signal${x.kept === 1 ? "" : "s"}</small></span><span><span class="tag ${esc(x.action.split(" ")[0])}">${esc(x.action)}</span> <b>${x.score}</b><small>${d}</small></span>`);
          });
          break;
        } catch (e) { if (attempt) line(`<span style="color:var(--bad)">Batch failed: ${esc(e.message)}</span>`); }
      }
      done += b.length;
      $("#mBar").style.width = (done / ids.length) * 100 + "%";
      $("#mTitle").textContent = `Scanning… ${done}/${ids.length}`;
    }
  };
  await Promise.all([worker(), worker(), worker()]);  // 5 batches of 10, 3 at a time
  try {
    const f = await api("/api/run", { method: "POST", body: JSON.stringify({ action: "finish", run: start.run }) });
    const safe = f.run.notes_hash_before === f.run.notes_hash_after;
    $("#mTitle").textContent = `Done: ${f.run.hot_count} to reach out this week`;
    $("#mSub").textContent = `${scanned} public items checked · ${kept} kept as signals · ${f.run.quiet_count} quiet`;
    $("#mFoot").innerHTML = safe ? "🔒 Notes fingerprint before = after: none of your columns changed." : "Your columns changed during the run (you edited something), which is fine.";
  } catch (e) { line(`<span style="color:var(--bad)">${esc(e.message)}</span>`); }
  $("#radar").classList.add("done"); $("#mClose").hidden = false; btn.disabled = false;
  load(touched);
}
$("#mClose").addEventListener("click", () => $("#runModal").classList.remove("on"));

// ---------- tabs
$$(".tab[data-view]").forEach((t) => t.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.remove("on")); t.classList.add("on");
  $$(".view").forEach((v) => v.classList.remove("on")); $("#v-" + t.dataset.view).classList.add("on");
  if (t.dataset.view === "guard") loadGuard();
  try { history.replaceState(null, "", "#" + t.dataset.view); } catch (e) {}
}));
const startTab = location.hash.replace("#", "");
if (["table", "guard", "runs"].includes(startTab)) $(`.tab[data-view="${startTab}"]`).click();
load();
