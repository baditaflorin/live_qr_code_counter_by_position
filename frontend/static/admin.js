import { api, el, clear, fmtTime } from "/static/common.js";

// ---------- tabs ----------
const tabs = document.querySelectorAll(".tabs button");
tabs.forEach((b) => b.addEventListener("click", () => {
  tabs.forEach((x) => x.classList.toggle("active", x === b));
  ["people", "markers", "zones", "questions"].forEach((t) => {
    document.getElementById("tab-" + t).hidden = b.dataset.tab !== t;
  });
  if (b.dataset.tab === "people") loadPeople();
  if (b.dataset.tab === "markers") loadMarkers();
  if (b.dataset.tab === "zones") loadZones();
  if (b.dataset.tab === "questions") loadQuestions();
}));

// ---------- system info ----------
api("/api/system").then((s) => {
  const e = document.getElementById("dict-info");
  if (e) e.textContent = `dictionary: ${s.dictionary}`;
}).catch(() => {});

// ---------- people ----------
const peopleListEl = document.getElementById("people-list");

async function loadPeople() {
  try {
    const people = await api("/api/people");
    renderPeople(people);
  } catch (e) {
    peopleListEl.textContent = "Error: " + e.message;
  }
}

function renderPeople(people) {
  clear(peopleListEl);
  if (!people.length) {
    peopleListEl.appendChild(el("div", { class: "muted" }, "No people yet."));
    return;
  }
  const tbl = el("table", {});
  tbl.appendChild(el("thead", {}, el("tr", {},
    el("th", {}, "Name"),
    el("th", {}, "Notes"),
    el("th", {}, "Markers"),
    el("th", {}, "Created"),
    el("th", {}, "Actions"),
  )));
  const tb = el("tbody", {});
  for (const p of people) {
    tb.appendChild(el("tr", {},
      el("td", {}, p.name),
      el("td", { class: "muted" }, p.notes || ""),
      el("td", {}, p.marker_ids.length ? p.marker_ids.map((id) => "#" + id).join(", ") : "—"),
      el("td", { class: "muted" }, fmtTime(p.created_at)),
      el("td", {},
        el("button", { onclick: () => assignMarker(p) }, "Assign new marker"),
        " ",
        el("button", {
          onclick: async () => {
            if (!p.marker_ids.length) { alert("No markers to print."); return; }
            window.open(`/api/markers/pdf?ids=${p.marker_ids.join(",")}`, "_blank");
          },
        }, "Download PDF"),
        " ",
        el("button", { onclick: () => editPerson(p) }, "Edit"),
        " ",
        el("button", { class: "danger", onclick: () => deletePerson(p) }, "Delete"),
      ),
    ));
  }
  tbl.appendChild(tb);
  peopleListEl.appendChild(tbl);
}

async function assignMarker(person) {
  try {
    const arr = await api("/api/markers/batch", { method: "POST", body: { count: 1, person_id: person.id } });
    await loadPeople();
    alert(`Created marker #${arr[0].aruco_id} for ${person.name}.`);
  } catch (e) { alert(e.message); }
}

async function editPerson(p) {
  const name = prompt("Name", p.name);
  if (name == null) return;
  const notes = prompt("Notes", p.notes || "");
  try {
    await api(`/api/people/${p.id}`, { method: "PUT", body: { name, notes } });
    await loadPeople();
  } catch (e) { alert(e.message); }
}

async function deletePerson(p) {
  if (!confirm(`Delete ${p.name}? Markers will be unassigned.`)) return;
  try {
    await api(`/api/people/${p.id}`, { method: "DELETE" });
    await loadPeople();
  } catch (e) { alert(e.message); }
}

document.getElementById("add-person-btn").addEventListener("click", async () => {
  const name = document.getElementById("person-name").value.trim();
  const notes = document.getElementById("person-notes").value.trim();
  const withMarkers = Number(document.getElementById("person-with-markers").value || 0);
  if (!name) { alert("Name required"); return; }
  try {
    const p = await api("/api/people", { method: "POST", body: { name, notes } });
    if (withMarkers > 0) {
      await api("/api/markers/batch", { method: "POST", body: { count: withMarkers, person_id: p.id } });
    }
    document.getElementById("person-name").value = "";
    document.getElementById("person-notes").value = "";
    await loadPeople();
  } catch (e) { alert(e.message); }
});

// ---------- markers ----------
const markersGridEl = document.getElementById("markers-grid");
let markersCache = [];
let selectedMarkerIds = new Set();

async function loadMarkers() {
  try {
    markersCache = await api("/api/markers");
    renderMarkers();
  } catch (e) {
    markersGridEl.textContent = "Error: " + e.message;
  }
}

function renderMarkers() {
  clear(markersGridEl);
  const filter = (document.getElementById("marker-filter").value || "").toLowerCase();
  const filtered = markersCache.filter((m) => {
    if (!filter) return true;
    return String(m.aruco_id).includes(filter) ||
      (m.person_name || "").toLowerCase().includes(filter);
  });
  if (!filtered.length) {
    markersGridEl.appendChild(el("div", { class: "muted" }, "No markers."));
    return;
  }
  for (const m of filtered) {
    const card = el("div", { class: "marker-card" });
    card.appendChild(el("img", { src: `/api/markers/${m.aruco_id}/image`, alt: "marker " + m.aruco_id }));
    card.appendChild(el("div", { class: "id" }, "#" + m.aruco_id));
    card.appendChild(el("div", { class: "person" }, m.person_name || "(unassigned)"));
    const actions = el("div", { class: "actions" });
    const cb = el("input", { type: "checkbox" });
    cb.checked = selectedMarkerIds.has(m.aruco_id);
    cb.addEventListener("change", () => {
      if (cb.checked) selectedMarkerIds.add(m.aruco_id);
      else selectedMarkerIds.delete(m.aruco_id);
    });
    const lbl = el("label", { style: { fontSize: "12px" } }, cb, " select");
    actions.appendChild(lbl);
    actions.appendChild(el("button", {
      onclick: () => sharePhoneDialog(m),
      title: "Show QR code to open this marker on a phone",
    }, "📱"));
    actions.appendChild(el("button", {
      onclick: () => assignMarkerDialog(m),
    }, "Assign"));
    actions.appendChild(el("button", {
      class: "danger",
      onclick: async () => {
        if (!confirm(`Delete marker #${m.aruco_id}?`)) return;
        try { await api(`/api/markers/${m.aruco_id}`, { method: "DELETE" }); await loadMarkers(); }
        catch (e) { alert(e.message); }
      },
    }, "×"));
    card.appendChild(actions);
    markersGridEl.appendChild(card);
  }
}

function sharePhoneDialog(m) {
  // Build URL using location.host. Warn if user is on localhost (phones can't reach it).
  const host = location.host;
  const onLocalhost = /^(localhost|127\.|0\.0\.0\.0)/.test(host);
  const url = `${location.protocol}//${host}/m/${m.aruco_id}`;

  const dlg = document.createElement("dialog");
  dlg.style.maxWidth = "440px";
  dlg.innerHTML = `
    <h3 style="margin-top:0;">Share marker #${m.aruco_id} to a phone</h3>
    <p class="muted" style="margin: 4px 0 12px;">Scan this with the phone's camera, then keep the page open. The marker fills the screen so the room camera can detect it.</p>
    <div style="text-align:center; padding: 8px 0;">
      <img alt="QR" style="width: 260px; height: 260px; background: white; border-radius: 8px;" />
    </div>
    <div style="font-family: ui-monospace, SF Mono, Menlo, monospace; word-break: break-all; padding: 8px; background: #0a1124; border-radius: 6px; font-size: 13px; margin-bottom: 8px;"></div>
    ${onLocalhost ? `
      <div style="background:#3b2a08; border:1px solid #f59e0b; border-radius:6px; padding:8px 10px; font-size:13px; margin-bottom:10px;">
        <strong>Heads up:</strong> you're on <code>localhost</code>. Phones on your Wi-Fi can't reach this. Find your Mac's LAN IP with
        <code>ipconfig getifaddr en0</code> in Terminal, then open <code>http://&lt;your-ip&gt;:8000/admin</code> from there and try again.
      </div>` : ""}
    <div style="display:flex; gap:8px; justify-content:flex-end;">
      <button data-action="copy">Copy link</button>
      <button data-action="open">Open here</button>
      <button data-action="close" class="primary">Done</button>
    </div>
  `;
  dlg.querySelector("img").src = `/api/qr?text=${encodeURIComponent(url)}&size=8`;
  dlg.querySelector("div[style*='monospace']").textContent = url;
  dlg.querySelector('[data-action="copy"]').addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(url); } catch (_) {}
  });
  dlg.querySelector('[data-action="open"]').addEventListener("click", () => {
    window.open(url, "_blank");
  });
  dlg.querySelector('[data-action="close"]').addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

async function assignMarkerDialog(m) {
  const people = await api("/api/people");
  const choices = ["(unassign)"].concat(people.map((p) => `${p.id}: ${p.name}`));
  const ans = prompt(
    `Assign marker #${m.aruco_id} to which person?\n\n` + choices.join("\n") + "\n\nEnter person id (blank = unassign):",
    m.person_id != null ? String(m.person_id) : ""
  );
  if (ans == null) return;
  const personId = ans.trim() === "" ? null : Number(ans.trim());
  if (personId !== null && !Number.isInteger(personId)) { alert("Invalid id"); return; }
  try {
    await api(`/api/markers/${m.aruco_id}/assign`, { method: "PUT", body: { person_id: personId } });
    await loadMarkers();
  } catch (e) { alert(e.message); }
}

document.getElementById("batch-create-btn").addEventListener("click", async () => {
  const count = Number(document.getElementById("batch-count").value);
  if (!count || count < 1) return;
  try {
    await api("/api/markers/batch", { method: "POST", body: { count } });
    await loadMarkers();
  } catch (e) { alert(e.message); }
});

document.getElementById("download-all-pdf").addEventListener("click", () => {
  window.open("/api/markers/pdf", "_blank");
});

document.getElementById("download-selected-pdf").addEventListener("click", () => {
  if (selectedMarkerIds.size === 0) { alert("Select some markers first."); return; }
  window.open(`/api/markers/pdf?ids=${[...selectedMarkerIds].join(",")}`, "_blank");
});

document.getElementById("marker-filter").addEventListener("input", renderMarkers);

// ---------- zones ----------
const zVideo = document.getElementById("z-video");
const zBg = document.getElementById("z-bg");
const zDraw = document.getElementById("z-draw");
const zCamSelect = document.getElementById("z-camera-select");
const zStartBtn = document.getElementById("z-start-cam");
const zStopBtn = document.getElementById("z-stop-cam");
const zSnapshotBtn = document.getElementById("z-snapshot");
const zoneNameInput = document.getElementById("zone-name");
const zoneLabelInput = document.getElementById("zone-label");
const zoneColorInput = document.getElementById("zone-color");
const zoneUndoBtn = document.getElementById("zone-undo");
const zoneClearBtn = document.getElementById("zone-clear");
const zoneSaveBtn = document.getElementById("zone-save");
const zonesListEl = document.getElementById("zones-list");
const zoneStage = document.getElementById("zone-stage");

let zStream = null;
let zoneZonesCache = [];
let drawingPoints = []; // [[x,y]] in normalized 0..1
let editingZoneId = null;

async function listZCameras() {
  try {
    const tmp = await navigator.mediaDevices.getUserMedia({ video: true });
    tmp.getTracks().forEach((t) => t.stop());
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cams = devices.filter((d) => d.kind === "videoinput");
    zCamSelect.innerHTML = "";
    cams.forEach((c, i) => {
      const opt = document.createElement("option");
      opt.value = c.deviceId;
      opt.textContent = c.label || `Camera ${i + 1}`;
      zCamSelect.appendChild(opt);
    });
  } catch (e) {
    zCamSelect.innerHTML = '<option value="">(grant permission)</option>';
  }
}

async function startZCam() {
  try {
    zStream = await navigator.mediaDevices.getUserMedia({
      video: {
        deviceId: zCamSelect.value ? { exact: zCamSelect.value } : undefined,
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });
    zVideo.srcObject = zStream;
    zVideo.style.display = "block";
    zBg.style.display = "none";
    await zVideo.play();
    sizeDrawCanvas();
  } catch (e) {
    alert("Camera error: " + e.message);
  }
}

function stopZCam() {
  if (zStream) { zStream.getTracks().forEach((t) => t.stop()); zStream = null; }
  zVideo.srcObject = null;
}

function takeBgSnapshot() {
  if (!zVideo.videoWidth) { alert("Start camera first."); return; }
  const c = document.createElement("canvas");
  c.width = zVideo.videoWidth;
  c.height = zVideo.videoHeight;
  c.getContext("2d").drawImage(zVideo, 0, 0);
  zBg.src = c.toDataURL("image/png");
  zBg.style.display = "block";
  zVideo.style.display = "none";
  if (zStream) { zStream.getTracks().forEach((t) => t.stop()); zStream = null; }
}

function sizeDrawCanvas() {
  const rect = zoneStage.getBoundingClientRect();
  zDraw.width = rect.width;
  zDraw.height = rect.height;
  redrawZoneCanvas();
}

window.addEventListener("resize", () => {
  if (!document.getElementById("tab-zones").hidden) sizeDrawCanvas();
});

zDraw.addEventListener("click", (ev) => {
  const r = zDraw.getBoundingClientRect();
  const x = (ev.clientX - r.left) / r.width;
  const y = (ev.clientY - r.top) / r.height;
  drawingPoints.push([x, y]);
  redrawZoneCanvas();
});

function redrawZoneCanvas() {
  const ctx = zDraw.getContext("2d");
  const w = zDraw.width;
  const h = zDraw.height;
  ctx.clearRect(0, 0, w, h);

  // existing zones (faint)
  for (const z of zoneZonesCache) {
    if (!z.polygon || z.polygon.length < 3) continue;
    ctx.beginPath();
    z.polygon.forEach(([x, y], i) => {
      const px = x * w;
      const py = y * h;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fillStyle = hexToRgba(z.color, 0.12);
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = z.color;
    ctx.stroke();
    const cx = (z.polygon.reduce((a, p) => a + p[0], 0) / z.polygon.length) * w;
    const cy = (z.polygon.reduce((a, p) => a + p[1], 0) / z.polygon.length) * h;
    ctx.font = "bold 16px sans-serif";
    ctx.fillStyle = z.color;
    ctx.strokeStyle = "rgba(0,0,0,0.7)";
    ctx.lineWidth = 3;
    const txt = z.label || z.name;
    const m = ctx.measureText(txt);
    ctx.strokeText(txt, cx - m.width / 2, cy);
    ctx.fillText(txt, cx - m.width / 2, cy);
  }

  // current drawing
  if (drawingPoints.length) {
    const color = zoneColorInput.value;
    ctx.beginPath();
    drawingPoints.forEach(([x, y], i) => {
      const px = x * w;
      const py = y * h;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
    if (drawingPoints.length >= 3) ctx.closePath();
    ctx.lineWidth = 2;
    ctx.strokeStyle = color;
    ctx.stroke();
    if (drawingPoints.length >= 3) {
      ctx.fillStyle = hexToRgba(color, 0.2);
      ctx.fill();
    }
    drawingPoints.forEach(([x, y]) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x * w, y * h, 5, 0, Math.PI * 2);
      ctx.fill();
    });
  }
}

function hexToRgba(hex, a) {
  const m = /^#?([a-f0-9]{6})$/i.exec(hex || "#22c55e");
  if (!m) return `rgba(34,197,94,${a})`;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

zoneUndoBtn.addEventListener("click", () => { drawingPoints.pop(); redrawZoneCanvas(); });
zoneClearBtn.addEventListener("click", () => { drawingPoints = []; editingZoneId = null; redrawZoneCanvas(); });

zoneSaveBtn.addEventListener("click", async () => {
  if (drawingPoints.length < 3) { alert("Need at least 3 points."); return; }
  const payload = {
    name: zoneNameInput.value.trim() || "zone",
    label: zoneLabelInput.value.trim(),
    color: zoneColorInput.value,
    polygon: drawingPoints,
  };
  try {
    if (editingZoneId) {
      await api(`/api/zones/${editingZoneId}`, { method: "PUT", body: payload });
    } else {
      await api("/api/zones", { method: "POST", body: payload });
    }
    drawingPoints = [];
    editingZoneId = null;
    zoneNameInput.value = "";
    zoneLabelInput.value = "";
    await loadZones();
  } catch (e) { alert(e.message); }
});

async function loadZones() {
  try {
    zoneZonesCache = await api("/api/zones");
    redrawZoneCanvas();
    renderZonesList();
  } catch (e) {
    zonesListEl.textContent = "Error: " + e.message;
  }
}

function renderZonesList() {
  clear(zonesListEl);
  if (!zoneZonesCache.length) {
    zonesListEl.appendChild(el("div", { class: "muted" }, "No zones yet."));
    return;
  }
  const tbl = el("table", {});
  tbl.appendChild(el("thead", {}, el("tr", {},
    el("th", {}, "Color"),
    el("th", {}, "Name"),
    el("th", {}, "Label"),
    el("th", {}, "Points"),
    el("th", {}, "Actions"),
  )));
  const tb = el("tbody", {});
  for (const z of zoneZonesCache) {
    tb.appendChild(el("tr", {},
      el("td", {}, el("span", { style: { display: "inline-block", width: "16px", height: "16px", background: z.color, borderRadius: "3px" } })),
      el("td", {}, z.name),
      el("td", {}, z.label || ""),
      el("td", {}, String(z.polygon.length)),
      el("td", {},
        el("button", {
          onclick: () => {
            editingZoneId = z.id;
            zoneNameInput.value = z.name;
            zoneLabelInput.value = z.label || "";
            zoneColorInput.value = z.color || "#22c55e";
            drawingPoints = z.polygon.map((p) => [...p]);
            redrawZoneCanvas();
          }
        }, "Edit polygon"),
        " ",
        el("button", {
          class: "danger",
          onclick: async () => {
            if (!confirm(`Delete zone "${z.name}"?`)) return;
            await api(`/api/zones/${z.id}`, { method: "DELETE" });
            await loadZones();
          }
        }, "Delete"),
      ),
    ));
  }
  tbl.appendChild(tb);
  zonesListEl.appendChild(tbl);
}

zStartBtn.addEventListener("click", startZCam);
zStopBtn.addEventListener("click", stopZCam);
zSnapshotBtn.addEventListener("click", takeBgSnapshot);
listZCameras();

// ---------- questions ----------
const questionsListEl = document.getElementById("questions-list");
const questionDetailPanel = document.getElementById("question-detail");
const questionDetailBody = document.getElementById("question-detail-body");

async function loadQuestions() {
  try {
    const qs = await api("/api/questions");
    renderQuestions(qs);
  } catch (e) {
    questionsListEl.textContent = "Error: " + e.message;
  }
}

function renderQuestions(qs) {
  clear(questionsListEl);
  if (!qs.length) {
    questionsListEl.appendChild(el("div", { class: "muted" }, "No questions yet."));
    return;
  }
  const tbl = el("table", {});
  tbl.appendChild(el("thead", {}, el("tr", {},
    el("th", {}, "Active"),
    el("th", {}, "Text"),
    el("th", {}, "Created"),
    el("th", {}, "Actions"),
  )));
  const tb = el("tbody", {});
  for (const q of qs) {
    tb.appendChild(el("tr", {},
      el("td", {}, q.is_active ? el("span", { class: "status-pill ok" }, "active") : ""),
      el("td", {}, q.text),
      el("td", { class: "muted" }, fmtTime(q.created_at)),
      el("td", {},
        el("button", {
          onclick: async () => { await api(`/api/questions/${q.id}/activate`, { method: "PUT" }); await loadQuestions(); }
        }, "Activate"),
        " ",
        el("button", { onclick: () => showQuestionDetail(q.id) }, "Results"),
        " ",
        el("button", {
          class: "danger",
          onclick: async () => {
            if (!confirm(`Delete "${q.text}"? All votes will be removed.`)) return;
            await api(`/api/questions/${q.id}`, { method: "DELETE" });
            questionDetailPanel.hidden = true;
            await loadQuestions();
          }
        }, "Delete"),
      ),
    ));
  }
  tbl.appendChild(tb);
  questionsListEl.appendChild(tbl);
}

document.getElementById("add-question-btn").addEventListener("click", async () => {
  const text = document.getElementById("question-text").value.trim();
  if (!text) return;
  try {
    await api("/api/questions", { method: "POST", body: { text } });
    document.getElementById("question-text").value = "";
    await loadQuestions();
  } catch (e) { alert(e.message); }
});

async function showQuestionDetail(qid) {
  const sum = await api(`/api/questions/${qid}/summary`);
  questionDetailPanel.hidden = false;
  clear(questionDetailBody);
  questionDetailBody.appendChild(el("h4", {}, sum.question.text));
  if (Object.keys(sum.latest_breakdown || {}).length) {
    questionDetailBody.appendChild(el("p", {}, el("strong", {}, "Latest snapshot: ")));
    const ul = el("ul", {});
    for (const [k, v] of Object.entries(sum.latest_breakdown)) {
      ul.appendChild(el("li", {}, `${k}: ${v}`));
    }
    questionDetailBody.appendChild(ul);
  }
  if (sum.snapshots.length === 0) {
    questionDetailBody.appendChild(el("div", { class: "muted" }, "No snapshots recorded yet."));
    return;
  }
  for (const s of sum.snapshots) {
    const block = el("div", { class: "panel", style: { marginTop: "8px", background: "var(--panel-2)" } });
    block.appendChild(el("div", {}, el("strong", {}, `Snapshot #${s.snapshot_id}`), " ", el("span", { class: "muted" }, fmtTime(s.recorded_at))));
    const counts = Object.entries(s.by_zone).map(([k, v]) => `${k}: ${v}`).join("  ·  ");
    block.appendChild(el("div", { class: "muted" }, counts));
    const tbl = el("table", {});
    tbl.appendChild(el("thead", {}, el("tr", {}, el("th", {}, "Marker"), el("th", {}, "Person"), el("th", {}, "Zone"))));
    const tb = el("tbody", {});
    for (const e of s.entries) {
      tb.appendChild(el("tr", {}, el("td", {}, "#" + e.aruco_id), el("td", {}, e.person || "—"), el("td", {}, e.zone || "—")));
    }
    tbl.appendChild(tb);
    block.appendChild(tbl);
    questionDetailBody.appendChild(block);
  }
}

// boot
loadPeople();
