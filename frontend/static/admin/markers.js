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

function makeCard(m) {
  const card = el("div", { class: "marker-card" });
  card.appendChild(el("img", { src: `/api/markers/${m.aruco_id}/image`, alt: "marker " + m.aruco_id }));
  card.appendChild(el("div", { class: "id" }, "#" + m.aruco_id));
  card.appendChild(el("div", { class: "person" }, m.person_name || "(unassigned)"));

  const actions = el("div", { class: "actions" });
  const cb = el("input", { type: "checkbox" });
  cb.checked = selectedIds.has(m.aruco_id);
  cb.addEventListener("change", () => {
    if (cb.checked) selectedIds.add(m.aruco_id); else selectedIds.delete(m.aruco_id);
  });
  actions.appendChild(el("label", { style: { fontSize: "12px" } }, cb, " select"));
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
    try {
      await api("/api/markers/batch", { method: "POST", body: { count } });
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
