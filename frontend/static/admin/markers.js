import { api, el, clear } from "/static/common.js";

const gridEl = document.getElementById("markers-grid");
const filterEl = document.getElementById("marker-filter");

let cache = [];
const selectedIds = new Set();

export async function loadMarkers() {
  try {
    cache = await api("/api/markers");
    render();
  } catch (e) { gridEl.textContent = "Error: " + e.message; }
}

function render() {
  clear(gridEl);
  const filter = (filterEl.value || "").toLowerCase();
  const filtered = cache.filter((m) =>
    !filter || String(m.aruco_id).includes(filter) || (m.person_name || "").toLowerCase().includes(filter)
  );
  if (!filtered.length) {
    gridEl.appendChild(el("div", { class: "muted" }, "No markers."));
    return;
  }
  for (const m of filtered) {
    gridEl.appendChild(makeCard(m));
  }
}

const PLACEMENTS = ["hat", "chest", "back", "wrist", "accessory"];

function makeCard(m) {
  const card = el("div", { class: "marker-card" });
  card.appendChild(el("img", { src: `/api/markers/${m.aruco_id}/image`, alt: "marker " + m.aruco_id }));
  card.appendChild(el("div", { class: "id" }, "#" + m.aruco_id));
  card.appendChild(el("div", { class: "person" }, m.person_name || "(unassigned)"));

  // ADR 0049 — body placement chip, inline-editable.
  const placementSel = el("select", { title: "Body placement (ADR 0049)" });
  for (const p of PLACEMENTS) {
    const opt = el("option", { value: p }, p);
    if (p === (m.placement || "hat")) opt.setAttribute("selected", "selected");
    placementSel.appendChild(opt);
  }
  placementSel.addEventListener("change", async () => {
    try {
      await api(`/api/markers/${m.aruco_id}/assign`, {
        method: "PUT",
        body: { person_id: m.person_id, placement: placementSel.value },
      });
      m.placement = placementSel.value;
    } catch (e) { alert(e.message); }
  });
  card.appendChild(el("div", { class: "muted", style: { fontSize: "12px", marginTop: "4px" } },
    "placement: ", placementSel));

  const actions = el("div", { class: "actions" });
  const cb = el("input", { type: "checkbox" });
  cb.checked = selectedIds.has(m.aruco_id);
  cb.addEventListener("change", () => {
    if (cb.checked) selectedIds.add(m.aruco_id); else selectedIds.delete(m.aruco_id);
  });
  actions.appendChild(el("label", { style: { fontSize: "12px" } }, cb, " select"));
  actions.appendChild(el("button", {
    title: "Preview a styled badge",
    onclick: () => badgeDialog(m),
  }, "🎨"));
  actions.appendChild(el("button", {
    title: "Show QR for opening this marker on a phone",
    onclick: () => phoneShareDialog(m),
  }, "📱"));
  actions.appendChild(el("button", { onclick: () => assignDialog(m) }, "Assign"));
  actions.appendChild(el("button", {
    class: "danger",
    onclick: async () => {
      if (!confirm(`Delete marker #${m.aruco_id}?`)) return;
      try { await api(`/api/markers/${m.aruco_id}`, { method: "DELETE" }); await loadMarkers(); }
      catch (e) { alert(e.message); }
    },
  }, "×"));
  card.appendChild(actions);
  return card;
}

function phoneShareDialog(m) {
  const host = location.host;
  const onLocalhost = /^(localhost|127\.|0\.0\.0\.0)/.test(host);
  const url = `${location.protocol}//${host}/m/${m.aruco_id}`;

  const dlg = document.createElement("dialog");
  dlg.style.maxWidth = "440px";
  dlg.innerHTML = `
    <h3 style="margin-top:0;">Share marker #${m.aruco_id} to a phone</h3>
    <p class="muted" style="margin: 4px 0 12px;">Scan this with the phone's camera, then keep the page open.</p>
    <div style="text-align:center; padding: 8px 0;">
      <img alt="QR" style="width: 260px; height: 260px; background: white; border-radius: 8px;" />
    </div>
    <div style="font-family: ui-monospace, SF Mono, Menlo, monospace; word-break: break-all; padding: 8px; background: #0a1124; border-radius: 6px; font-size: 13px; margin-bottom: 8px;"></div>
    ${onLocalhost ? `
      <div style="background:#3b2a08; border:1px solid #f59e0b; border-radius:6px; padding:8px 10px; font-size:13px; margin-bottom:10px;">
        <strong>Heads up:</strong> you're on <code>localhost</code>. Phones on Wi-Fi can't reach this. Open admin via your LAN IP first.
      </div>` : ""}
    <div style="display:flex; gap:8px; justify-content:flex-end;">
      <button data-action="copy">Copy link</button>
      <button data-action="open">Open here</button>
      <button data-action="close" class="primary">Done</button>
    </div>`;
  dlg.querySelector("img").src = `/api/qr?text=${encodeURIComponent(url)}&size=8`;
  dlg.querySelector("div[style*='monospace']").textContent = url;
  dlg.querySelector('[data-action="copy"]').addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(url); } catch (_) {}
  });
  dlg.querySelector('[data-action="open"]').addEventListener("click", () => window.open(url, "_blank"));
  dlg.querySelector('[data-action="close"]').addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

// ---------- badge designer dialog ----------
let _badgeStylesCache = null;
async function loadBadgeStyles() {
  if (_badgeStylesCache) return _badgeStylesCache;
  _badgeStylesCache = await api("/api/badge-styles");
  return _badgeStylesCache;
}

async function badgeDialog(m) {
  const styles = await loadBadgeStyles();
  const dlg = document.createElement("dialog");
  dlg.style.maxWidth = "880px";
  dlg.style.width = "880px";
  dlg.innerHTML = `
    <h3 style="margin-top:0;">Badge designer — marker #${m.aruco_id}</h3>
    <p class="muted" style="margin: 4px 0 12px;">
      Stack a template, a palette, a cell ornament, and a generative frame.
      Detection is verified before rendering — combinations that would break the marker are rejected.
    </p>
    <div style="display:grid; grid-template-columns: 1fr 360px; gap: 16px;">
      <div style="background:white; border-radius: 8px; padding: 8px; min-height: 480px; display:flex; align-items:center; justify-content:center;">
        <img id="badge-preview" style="max-width:100%; max-height:600px;" />
      </div>
      <div style="display:flex; flex-direction:column; gap: 10px;">
        <label>Template
          <select id="bd-template"></select>
        </label>
        <label>Palette
          <select id="bd-palette"></select>
        </label>
        <div id="bd-palette-swatch" style="display:flex; gap:4px; height:18px; border-radius:4px; overflow:hidden;"></div>
        <label>Cell ornament
          <select id="bd-cell"></select>
        </label>
        <label>Generative frame
          <select id="bd-frame"></select>
        </label>
        <label>Sigil (corner emoji / initials, optional)
          <input id="bd-sigil" type="text" maxlength="6" placeholder="e.g. ⚜︎" />
        </label>
        <div class="muted" style="font-size:12px;" id="bd-status"></div>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button id="bd-download">Download PNG</button>
          <span style="flex:1"></span>
          <button id="bd-close" class="primary">Done</button>
        </div>
        <div class="muted" style="font-size:11px; word-break:break-all;" id="bd-url"></div>
      </div>
    </div>
  `;

  const $ = (sel) => dlg.querySelector(sel);
  const tmpl = $("#bd-template");
  const pal = $("#bd-palette");
  const cell = $("#bd-cell");
  const frame = $("#bd-frame");
  const sigil = $("#bd-sigil");
  const swatch = $("#bd-palette-swatch");
  const preview = $("#badge-preview");
  const status = $("#bd-status");
  const urlEl = $("#bd-url");

  styles.templates.forEach((t) => tmpl.appendChild(el("option", { value: t }, t)));
  styles.palettes.forEach((p) => pal.appendChild(el("option", { value: p.name }, `${p.name}  (${p.contrast_ratio}:1)`)));
  styles.cell_styles.forEach((c) => {
    const min_px = styles.cell_min_px?.[c];
    cell.appendChild(el("option", { value: c }, min_px ? `${c}  (≥${min_px}px)` : c));
  });
  styles.frames.forEach((f) => frame.appendChild(el("option", { value: f }, f)));

  function refresh() {
    const params = new URLSearchParams({
      template: tmpl.value,
      palette: pal.value,
      cell_style: cell.value,
      frame: frame.value,
      sigil: sigil.value,
    });
    const url = `/api/markers/${m.aruco_id}/badge?${params}`;
    preview.src = url + "&_t=" + Date.now();  // bust browser cache on parameter change
    urlEl.textContent = url;
    // Swatch
    const p = styles.palettes.find((x) => x.name === pal.value);
    if (p) {
      swatch.innerHTML = "";
      [p.paper, p.ink, p.accent].forEach((c) => {
        const div = document.createElement("div");
        div.style.flex = "1"; div.style.background = c;
        swatch.appendChild(div);
      });
    }
  }

  preview.addEventListener("load", () => { status.textContent = `Detection-verified ✓`; });
  preview.addEventListener("error", async () => {
    // Fetch detail
    try {
      const r = await fetch(preview.src.replace(/&?_t=\d+/, "") + "&verify=true");
      const j = await r.json();
      status.textContent = "⚠️ " + (j.detail || `HTTP ${r.status}`);
    } catch { status.textContent = "⚠️ render failed"; }
  });

  [tmpl, pal, cell, frame, sigil].forEach((e) => e.addEventListener("change", refresh));
  sigil.addEventListener("input", refresh);

  $("#bd-download").addEventListener("click", () => window.open(preview.src.replace(/&?_t=\d+/, ""), "_blank"));
  $("#bd-close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
  refresh();
}

async function assignDialog(m) {
  const people = await api("/api/people");
  const choices = ["(unassign)"].concat(people.map((p) => `${p.id}: ${p.name}`));
  const ans = prompt(
    `Assign marker #${m.aruco_id} to which person?\n\n` + choices.join("\n") + "\n\nEnter person id (blank = unassign):",
    m.person_id != null ? String(m.person_id) : ""
  );
  if (ans == null) return;
  const personId = ans.trim() === "" ? null : Number(ans.trim());
  if (personId !== null && !Number.isInteger(personId)) { alert("Invalid id"); return; }
  await api(`/api/markers/${m.aruco_id}/assign`, { method: "PUT", body: { person_id: personId } });
  await loadMarkers();
}

export function initMarkers() {
  document.getElementById("batch-create-btn").addEventListener("click", async () => {
    const count = Number(document.getElementById("batch-count").value);
    if (!count || count < 1) return;
    const placementEl = document.getElementById("batch-placement");
    const placement = (placementEl && placementEl.value) || "hat";
    try {
      await api("/api/markers/batch", { method: "POST", body: { count, placement } });
      await loadMarkers();
    } catch (e) { alert(e.message); }
  });
  document.getElementById("download-all-pdf").addEventListener("click", () => window.open("/api/markers/pdf", "_blank"));
  document.getElementById("download-selected-pdf").addEventListener("click", () => {
    if (selectedIds.size === 0) { alert("Select some markers first."); return; }
    window.open(`/api/markers/pdf?ids=${[...selectedIds].join(",")}`, "_blank");
  });
  filterEl.addEventListener("input", render);
}
