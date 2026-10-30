const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => [...el.querySelectorAll(s)];
let STATE = null;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(await r.text());
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  setTimeout(() => t.hidden = true, 2400);
}

function pill(bucket) {
  return `<span class="pill ${bucket}">${bucket}</span>`;
}

function renderOverview() {
  const c = STATE.counts;
  const critical = [...(STATE.buckets.overdue||[]), ...(STATE.buckets.critical||[])];
  const upcoming = STATE.buckets.upcoming || [];
  $("#view-overview").innerHTML = `
    <div class="grid">
      <div class="card"><h3>Files</h3><div class="big">${c.files}</div></div>
      <div class="card"><h3>Obligations</h3><div class="big">${c.obligations}</div></div>
      <div class="card"><h3>Critical</h3><div class="big">${c.critical}</div></div>
      <div class="card"><h3>Needs review</h3><div class="big">${c.needs_review}</div></div>
    </div>
    <div class="list">
      <h2>Act soon</h2>
      ${[...critical, ...upcoming].slice(0, 8).map(itemRow).join("") || emptyState("No upcoming deadlines")}
    </div>`;
}

function itemRow(it) {
  return `<div class="item" data-sha="${it.sha256}" data-id="${it.id}">
    <div class="date">${it.action_date}</div>
    <div>
      <div><strong>${it.counterparty || it.name}</strong> · ${it.kind_title}</div>
      <div class="meta">${it.action_label} · ${it.display_path}${it.notice_days ? ` · notice ${it.notice_days}d` : ""}</div>
    </div>
    ${pill(it.bucket)}
  </div>`;
}

function emptyState(msg) {
  return `<div class="empty"><svg width="64" height="64" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="30" stroke="#99f6e4" stroke-width="3"/><path d="M20 34l8 8 16-18" stroke="#0f766e" stroke-width="4" fill="none" stroke-linecap="round"/></svg><div>${msg}</div></div>`;
}

function renderTimeline() {
  const items = STATE.items || [];
  $("#view-timeline").innerHTML = `<h2>Timeline</h2><div class="timeline">${
    items.map(it => {
      const notice = it.notice_days ? `<div class="notice-window" title="notice window"><span>notice ${it.notice_days}d → act ${it.action_date}</span></div>` : "";
      return `<div class="t-item" data-sha="${it.sha256}" data-id="${it.id}">
        <div><strong>${it.action_date}</strong> ${pill(it.bucket)}</div>
        ${notice}
        <div>${it.counterparty || it.name} · ${it.kind_title}</div>
        <div class="meta">obligation ${it.obligation_date} · ${it.days_remaining}d · ${it.display_path}</div>
      </div>`;
    }).join("") || emptyState("No obligations yet")
  }</div>`;
}

function renderVault() {
  const rows = (STATE.files || []).map(f => `<tr data-sha="${f.sha256}" style="cursor:pointer">
    <td>${f.display_path}</td><td>${f.doc_type}</td><td>${f.counterparty || "—"}</td>
    <td>${f.status}</td><td>${f.reference_id || "—"}</td></tr>`).join("");
  $("#view-vault").innerHTML = `<h2>Vault ledger</h2>
    <table><thead><tr><th>Path</th><th>Type</th><th>Counterparty</th><th>Status</th><th>Ref</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderReview() {
  const items = STATE.review || [];
  $("#view-review").innerHTML = `
    <div class="card" style="margin-bottom:16px">
      <h3>Rules</h3>
      <p>Items land here when evidence is missing, confidence is low, the file is damaged, or no date can be read. ChronoVault never invents a date.</p>
    </div>
    <div class="list">${items.map(r => `
      <div class="item" data-sha="${r.sha256}">
        <div class="date">review</div>
        <div><strong>${r.display_path}</strong><div class="meta">${r.reason}</div></div>
        ${pill("review")}
      </div>`).join("") || emptyState("Nothing needs review")}
    </div>`;
}

async function renderDigest() {
  const md = await api("/api/digest");
  $("#view-digest").innerHTML = `<h2>Action digest</h2><pre class="card" style="white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:13px">${escapeHtml(md)}</pre>`;
}

function renderPrivacy() {
  $("#view-privacy").innerHTML = `
    <h2>Privacy & Skill mapping</h2>
    <div class="card">
      <ul>
        <li>Source folders are read-only and named by you.</li>
        <li>No cloud API, no API key, no telemetry. Dashboard binds to 127.0.0.1 only.</li>
        <li>Account numbers are masked in the digest.</li>
        <li>After every run the pipeline re-hashes sources and reports byte-identity.</li>
      </ul>
    </div>
    <table class="privacy-table" style="margin-top:16px">
      <thead><tr><th>Stage</th><th>On the NAS (Skill)</th><th>In this prototype</th></tr></thead>
      <tbody>
        <tr><td>Inventory</td><td>file-agent · ug-filesystem / ug-filemgr</td><td>pathlib + hashlib</td></tr>
        <tr><td>Documents</td><td>document-agent · ug-document extract</td><td>pypdf + grounded rules</td></tr>
        <tr><td>Photos</td><td>photo-agent · ug-photo vision-ocr</td><td>RapidOCR (ONNX)</td></tr>
        <tr><td>Digest</td><td>knowledge-agent · ug-knowledge save-text (approval)</td><td>SQLite + Markdown</td></tr>
        <tr><td>Tags</td><td>file-agent · ug-filemgr tag-add-file (opt-in)</td><td>not implemented</td></tr>
      </tbody>
    </table>`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function openDrawer(sha, id) {
  const it = (STATE.items || []).find(x => x.sha256 === sha && (!id || String(x.id) === String(id)))
    || (STATE.files || []).find(x => x.sha256 === sha);
  const rev = (STATE.review || []).find(x => x.sha256 === sha);
  const d = $("#drawer");
  if (!it && !rev && !it) {
    // file-only
  }
  const file = (STATE.files || []).find(x => x.sha256 === sha) || {};
  const ob = it || null;
  const evidence = (ob && ob.evidence) || [];
  const math = ob && ob.notice_days ? `<div class="math"><strong>Deadline math</strong><br/>
    ${ob.obligation_date} − ${ob.notice_days} days notice = <strong>act by ${ob.action_date}</strong></div>` : "";
  const img = (file.ext || "").match(/^\.(png|jpe?g|webp)$/i)
    ? `<img class="receipt-preview" src="/source/${sha}" alt="source"/>` : "";
  d.hidden = false;
  d.innerHTML = `
    <button class="ghost" style="color:#0f172a;border-color:#cbd5e1" id="closeDrawer">Close</button>
    <h2>${(ob && ob.counterparty) || file.counterparty || file.name || "File"}</h2>
    <div class="meta">${file.display_path || (ob && ob.display_path) || ""}</div>
    ${math}
    ${ob ? `<p><strong>${ob.kind_title}</strong> · ${pill(ob.bucket)} · ${ob.days_remaining}d</p>` : ""}
    ${rev ? `<p class="pill review">${rev.reason}</p>` : ""}
    ${evidence.map(e => `<div class="evidence">“${escapeHtml(e)}”</div>`).join("")}
    ${img}
    <p class="meta">status: ${file.status || "—"} · method: ${file.method || "—"} · ref: ${file.reference_id || (ob && ob.reference_id) || "—"}</p>`;
  $("#closeDrawer").onclick = () => { d.hidden = true; };
}

function bindClicks(root) {
  root.addEventListener("click", e => {
    const row = e.target.closest("[data-sha]");
    if (row) openDrawer(row.dataset.sha, row.dataset.id);
  });
}

async function showView(name) {
  $$(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.view === name));
  $$(".view").forEach(v => v.classList.toggle("on", v.id === "view-" + name));
  if (name === "overview") renderOverview();
  if (name === "timeline") renderTimeline();
  if (name === "vault") renderVault();
  if (name === "review") renderReview();
  if (name === "digest") await renderDigest();
  if (name === "privacy") renderPrivacy();
}

async function refresh() {
  STATE = await api("/api/state");
  const on = $(".tabs button.on")?.dataset.view || "overview";
  await showView(on);
}

async function runScan() {
  const modal = $("#modal");
  const log = $("#scanLog");
  const fill = $("#scanFill");
  modal.hidden = false; log.innerHTML = ""; fill.style.width = "5%";
  const pace = window.SCAN_PACE || 420;
  const stages = [
    "1 · Fingerprinting authorized folders…",
    "2 · Extracting fields with evidence…",
    "3 · Ranking deadlines and writing digest…",
  ];
  for (let i = 0; i < stages.length; i++) {
    const li = document.createElement("li");
    li.textContent = stages[i];
    log.appendChild(li);
    fill.style.width = `${((i + 1) / stages.length) * 70}%`;
    await new Promise(r => setTimeout(r, pace));
  }
  const res = await api("/api/scan", { method: "POST" });
  STATE = res.state;
  fill.style.width = "100%";
  (res.report.log || []).slice(-6).forEach(e => {
    const li = document.createElement("li");
    li.textContent = e.msg;
    log.appendChild(li);
  });
  await new Promise(r => setTimeout(r, pace));
  modal.hidden = true;
  toast("Scan complete");
  await showView("overview");
}

$("#tabs").addEventListener("click", e => {
  const b = e.target.closest("button[data-view]");
  if (b) showView(b.dataset.view);
});
$("#btnScan").onclick = () => runScan().catch(err => { $("#modal").hidden = true; toast(String(err)); });
$("#btnReset").onclick = async () => {
  await api("/api/reset", { method: "POST" });
  toast("Vault cleared");
  await refresh();
};
bindClicks(document);
refresh().catch(err => toast(String(err)));
