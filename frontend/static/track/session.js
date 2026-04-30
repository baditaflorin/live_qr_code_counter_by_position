// Tracking session controls (start / stop / list / pick-for-report).
import { api, el, clear, fmtTime } from "/static/common.js";

const startForm = document.getElementById("track-start-form");
const startBtn = document.getElementById("track-start-btn");
const stopBtn = document.getElementById("track-stop-btn");
const sessionsListEl = document.getElementById("track-sessions-list");
const activeBannerEl = document.getElementById("track-active-banner");
const activeNameEl = document.getElementById("track-active-name");
const activeStatsEl = document.getElementById("track-active-stats");

let _onSelectReport = null;
let _onActiveChange = null;
let _activeId = null;

export function initSession({ onSelectReport, onActiveChange }) {
  _onSelectReport = onSelectReport;
  _onActiveChange = onActiveChange;
  startBtn.addEventListener("click", onStart);
  stopBtn.addEventListener("click", onStop);
  refresh();
}

export function refresh() {
  return Promise.all([refreshActive(), refreshList()]);
}

async function onStart() {
  const name = document.getElementById("track-name").value.trim() ||
               `Session ${new Date().toLocaleTimeString()}`;
  const proximity = parseFloat(document.getElementById("track-proximity").value) || 0.12;
  const interval = parseInt(document.getElementById("track-interval").value, 10) || 500;
  try {
    await api("/api/tracking/sessions", {
      method: "POST",
      body: { name, proximity_norm: proximity, sample_interval_ms: interval },
    });
    await refresh();
  } catch (e) { alert(e.message); }
}

async function onStop() {
  if (!_activeId) return;
  if (!confirm("Stop tracking? You can still view the report afterwards.")) return;
  try {
    await api(`/api/tracking/sessions/${_activeId}/stop`, { method: "PUT" });
    await refresh();
  } catch (e) { alert(e.message); }
}

async function refreshActive() {
  try {
    const active = await api("/api/tracking/sessions/active");
    const previous = _activeId;
    _activeId = active ? active.id : null;
    if (active) {
      activeBannerEl.hidden = false;
      activeNameEl.textContent = active.name;
      const elapsed = Math.round((Date.now() - new Date(active.started_at).getTime()) / 1000);
      activeStatsEl.textContent = `running ${formatDuration(elapsed)} · ${active.sample_count} samples · ${active.markers_seen} markers seen · proximity=${active.proximity_norm} · every ${active.sample_interval_ms}ms`;
      stopBtn.disabled = false;
      startBtn.disabled = true;
      startForm.classList.add("disabled-section");
    } else {
      activeBannerEl.hidden = true;
      stopBtn.disabled = true;
      startBtn.disabled = false;
      startForm.classList.remove("disabled-section");
    }
    if (previous !== _activeId) _onActiveChange?.(active);
  } catch (e) { console.error(e); }
}

async function refreshList() {
  try {
    const sessions = await api("/api/tracking/sessions");
    renderSessions(sessions);
  } catch (e) { sessionsListEl.textContent = "Error: " + e.message; }
}

function renderSessions(rows) {
  clear(sessionsListEl);
  if (!rows.length) {
    sessionsListEl.appendChild(el("div", { class: "muted" }, "No sessions yet."));
    return;
  }
  const tbl = el("table", {});
  tbl.appendChild(el("thead", {}, el("tr", {},
    el("th", {}, "Status"),
    el("th", {}, "Name"),
    el("th", {}, "Started"),
    el("th", {}, "Duration"),
    el("th", {}, "Samples"),
    el("th", {}, "Markers"),
    el("th", {}, "Proximity"),
    el("th", {}, "Actions"),
  )));
  const tb = el("tbody", {});
  for (const s of rows) {
    const isLive = !s.stopped_at;
    const start = new Date(s.started_at);
    const end = s.stopped_at ? new Date(s.stopped_at) : new Date();
    const dur = Math.round((end - start) / 1000);
    tb.appendChild(el("tr", {},
      el("td", {}, isLive ? el("span", { class: "status-pill ok" }, "live") : el("span", { class: "status-pill" }, "ended")),
      el("td", {}, s.name),
      el("td", { class: "muted" }, fmtTime(s.started_at)),
      el("td", {}, formatDuration(dur)),
      el("td", {}, String(s.sample_count)),
      el("td", {}, String(s.markers_seen)),
      el("td", { class: "muted" }, String(s.proximity_norm)),
      el("td", {},
        el("button", { onclick: () => _onSelectReport?.(s.id) }, "Report"),
        " ",
        el("button", {
          class: "danger",
          onclick: async () => {
            if (!confirm(`Delete "${s.name}" and all its samples?`)) return;
            try { await api(`/api/tracking/sessions/${s.id}`, { method: "DELETE" }); await refresh(); }
            catch (e) { alert(e.message); }
          },
        }, "×"),
      ),
    ));
  }
  tbl.appendChild(tb);
  sessionsListEl.appendChild(tbl);
}

export function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h) return `${h}h ${m}m ${s}s`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}
