// Zones tab: drawing, editing, locking, undo/redo.
//
// Coord system: polygons are stored as normalized [x,y] in [0,1] so they
// survive resolution changes. The drawing canvas mirrors video pixel
// dimensions, so we convert pixel <-> norm at the event boundary.
//
// State machine via interaction handlers (no explicit modes):
//   - click on a zone           → select that zone for editing
//   - drag a vertex handle      → move vertex
//   - shift-click a handle      → delete vertex
//   - click empty space         → append a vertex to the WIP polygon
//   - "+ New zone" button       → clear WIP, start a fresh polygon
//   - "Save zone" button        → POST (new) or PUT (existing)
//   - Cmd-Z / Cmd-Shift-Z       → undo / redo of WIP polygon mutations
//   - Esc                       → deselect / clear WIP
//
// Locked zones are skipped in hit-testing and are drawn with a dashed
// outline so they're visibly locked.

import { api, el } from "/static/common.js";
import { renderGroupedTable, actionButton } from "./ui.js";

// ---------- DOM ----------
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
const zoneFormationSel = document.getElementById("zone-formation");
const zoneEditFormationEl = document.getElementById("zone-edit-formation");
const zoneStage = document.getElementById("zone-stage");
const zonesListEl = document.getElementById("zones-list");
const zoneUndoBtn = document.getElementById("zone-undo");
const zoneRedoBtn = document.getElementById("zone-redo");
const zoneNewBtn = document.getElementById("zone-new");
const zoneSaveBtn = document.getElementById("zone-save");
const seedZonesBtn = document.getElementById("seed-zones-btn");

// ---------- state ----------
let cache = [];                 // all zones (across formations)
let stream = null;              // MediaStream when the camera is running
let drawingPoints = [];         // [[x,y]] normalized 0..1, the WIP polygon
let editingZoneId = null;       // null = drawing a new zone
let undoStack = [];             // [{drawingPoints, editingZoneId}]
let redoStack = [];

let drag = null;                // { index, snapshotPushed }
let mouseDownPx = null;         // {x,y,shift} for click-vs-drag distinction
let didDrag = false;

// ---------- constants ----------
const VERTEX_HIT_PX = 12;
const CLICK_THRESHOLD_PX = 5;

// ---------- formation filter ----------
function visibleFormation() { return zoneEditFormationEl.value; }
function visibleZones() {
  const f = visibleFormation();
  return f ? cache.filter((z) => (z.formation || "") === f) : cache;
}

// ---------- undo / redo ----------
function snapshotState() {
  return {
    drawingPoints: drawingPoints.map((p) => [...p]),
    editingZoneId,
  };
}
function restoreState(s) {
  drawingPoints = s.drawingPoints.map((p) => [...p]);
  editingZoneId = s.editingZoneId;
}
function pushUndo() {
  undoStack.push(snapshotState());
  if (undoStack.length > 200) undoStack.shift();
  redoStack = [];
  refreshUndoButtons();
}
function undo() {
  if (!undoStack.length) return;
  redoStack.push(snapshotState());
  restoreState(undoStack.pop());
  syncEditorInputsFromCacheIfEditing();
  redrawCanvas();
  refreshUndoButtons();
}
function redo() {
  if (!redoStack.length) return;
  undoStack.push(snapshotState());
  restoreState(redoStack.pop());
  syncEditorInputsFromCacheIfEditing();
  redrawCanvas();
  refreshUndoButtons();
}
function refreshUndoButtons() {
  zoneUndoBtn.disabled = !undoStack.length;
  zoneRedoBtn.disabled = !redoStack.length;
}

function syncEditorInputsFromCacheIfEditing() {
  // After undo/redo restored editingZoneId, refill the metadata inputs from
  // the cached zone — keeps the form consistent with what's on the canvas.
  if (editingZoneId == null) return;
  const z = cache.find((x) => x.id === editingZoneId);
  if (!z) return;
  zoneNameInput.value = z.name;
  zoneLabelInput.value = z.label || "";
  zoneColorInput.value = z.color || "#22c55e";
  zoneFormationSel.value = z.formation || "";
}

// ---------- coord helpers ----------
function pxToNorm(px, py) { return [px / zDraw.width, py / zDraw.height]; }
function normToPx(nx, ny) { return [nx * zDraw.width, ny * zDraw.height]; }

function pointInPolygon(pt, poly) {
  if (!poly || poly.length < 3) return false;
  const [x, y] = pt;
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1];
    const xj = poly[j][0], yj = poly[j][1];
    const hit = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi);
    if (hit) inside = !inside;
  }
  return inside;
}

function vertexHit(x, y) {
  for (let i = drawingPoints.length - 1; i >= 0; i--) {
    const [px, py] = normToPx(...drawingPoints[i]);
    if (Math.hypot(px - x, py - y) <= VERTEX_HIT_PX) return i;
  }
  return -1;
}

function zoneHit(x, y) {
  const [nx, ny] = pxToNorm(x, y);
  const visible = visibleZones();
  // Front-to-back; skip locked.
  for (let i = visible.length - 1; i >= 0; i--) {
    const z = visible[i];
    if (z.locked) continue;
    if (pointInPolygon([nx, ny], z.polygon)) return z;
  }
  return null;
}

// ---------- canvas events ----------
function onDown(ev) {
  const r = zDraw.getBoundingClientRect();
  const x = ev.clientX - r.left;
  const y = ev.clientY - r.top;
  mouseDownPx = { x, y, shift: ev.shiftKey };
  didDrag = false;

  const vIdx = vertexHit(x, y);
  if (vIdx >= 0) {
    if (ev.shiftKey) {
      // Shift-click: delete vertex.
      pushUndo();
      drawingPoints.splice(vIdx, 1);
      mouseDownPx = null;
      redrawCanvas();
    } else {
      // Defer the undo snapshot until the first move — a click that doesn't
      // actually drag shouldn't pollute the undo stack.
      drag = { index: vIdx, snapshotPushed: false };
    }
  }
}

function onMove(ev) {
  if (!drag) return;
  const r = zDraw.getBoundingClientRect();
  const x = ev.clientX - r.left;
  const y = ev.clientY - r.top;
  if (!drag.snapshotPushed) {
    pushUndo();
    drag.snapshotPushed = true;
  }
  drawingPoints[drag.index] = pxToNorm(x, y);
  didDrag = true;
  redrawCanvas();
}

function onUp(ev) {
  if (drag) { drag = null; return; }
  if (!mouseDownPx) return;

  const r = zDraw.getBoundingClientRect();
  const x = ev.clientX - r.left;
  const y = ev.clientY - r.top;
  const dx = x - mouseDownPx.x;
  const dy = y - mouseDownPx.y;
  const isClick = Math.hypot(dx, dy) < CLICK_THRESHOLD_PX;
  mouseDownPx = null;
  if (!isClick) return;

  // Click on an existing zone → select it.
  const z = zoneHit(x, y);
  if (z) {
    pushUndo();
    loadZoneIntoEditor(z);
    redrawCanvas();
    return;
  }
  // Click on empty space → add a vertex to the WIP polygon.
  pushUndo();
  drawingPoints.push(pxToNorm(x, y));
  redrawCanvas();
}

function loadZoneIntoEditor(z) {
  editingZoneId = z.id;
  drawingPoints = z.polygon.map((p) => [...p]);
  zoneNameInput.value = z.name;
  zoneLabelInput.value = z.label || "";
  zoneColorInput.value = z.color || "#22c55e";
  zoneFormationSel.value = z.formation || "";
}

function clearWip(pushHistory = true) {
  if (pushHistory) pushUndo();
  drawingPoints = [];
  editingZoneId = null;
  redrawCanvas();
}

// ---------- drawing ----------
function redrawCanvas() {
  const ctx = zDraw.getContext("2d");
  const w = zDraw.width;
  const h = zDraw.height;
  ctx.clearRect(0, 0, w, h);

  // Existing zones (faint), except the one currently being edited.
  for (const z of visibleZones()) {
    if (!z.polygon || z.polygon.length < 3) continue;
    if (z.id === editingZoneId) continue;
    drawZonePolygon(ctx, z, w, h);
  }
  drawWipPolygon(ctx, w, h);
}

function drawZonePolygon(ctx, z, w, h) {
  ctx.beginPath();
  z.polygon.forEach(([x, y], i) => {
    const px = x * w; const py = y * h;
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.closePath();
  ctx.fillStyle = hexToRgba(z.color, 0.10);
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = z.color;
  ctx.setLineDash(z.locked ? [6, 4] : []);
  ctx.stroke();
  ctx.setLineDash([]);

  const [cx, cy] = polygonCentroid(z.polygon, w, h);
  ctx.font = "bold 16px sans-serif";
  ctx.fillStyle = z.color;
  ctx.strokeStyle = "rgba(0,0,0,0.7)";
  ctx.lineWidth = 3;
  const txt = (z.locked ? "🔒 " : "") + (z.label || z.name);
  const m = ctx.measureText(txt);
  ctx.strokeText(txt, cx - m.width / 2, cy);
  ctx.fillText(txt, cx - m.width / 2, cy);
}

function drawWipPolygon(ctx, w, h) {
  if (!drawingPoints.length) return;
  const color = zoneColorInput.value;
  ctx.beginPath();
  drawingPoints.forEach(([x, y], i) => {
    const px = x * w; const py = y * h;
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  if (drawingPoints.length >= 3) ctx.closePath();
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = color;
  ctx.stroke();
  if (drawingPoints.length >= 3) {
    ctx.fillStyle = hexToRgba(color, 0.25);
    ctx.fill();
  }
  // Vertex handles.
  drawingPoints.forEach(([x, y]) => {
    ctx.fillStyle = "#fff";
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x * w, y * h, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });
}

function polygonCentroid(poly, w, h) {
  const sx = poly.reduce((a, p) => a + p[0], 0) / poly.length;
  const sy = poly.reduce((a, p) => a + p[1], 0) / poly.length;
  return [sx * w, sy * h];
}

function hexToRgba(hex, a) {
  const m = /^#?([a-f0-9]{6})$/i.exec(hex || "#22c55e");
  if (!m) return `rgba(34,197,94,${a})`;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// ---------- list rendering ----------
function renderList() {
  const visible = visibleZones();
  if (!cache.length) {
    zonesListEl.innerHTML = '<div class="muted">No zones yet — click "Load default templates" above for a working set.</div>';
    return;
  }
  if (!visible.length) {
    zonesListEl.innerHTML = `<div class="muted">No zones for formation "${visibleFormation()}". Switch the filter to "all" or load defaults.</div>`;
    return;
  }
  renderGroupedTable({
    container: zonesListEl,
    items: visible,
    groupBy: (z) => z.formation || "(unassigned)",
    columns: [
      { header: "", width: "32px",
        cell: (z) => el("span", { style: { display: "inline-block", width: "16px", height: "16px", background: z.color, borderRadius: "3px" } }) },
      { header: "Name",  cell: (z) => z.name },
      { header: "Label", cell: (z) => z.label || "" },
      { header: "Pts",   width: "50px", cell: (z) => String(z.polygon.length) },
      { header: "Lock",  width: "60px",
        cell: (z) => actionButton(z.locked ? "🔒" : "🔓", {
          title: z.locked ? "Unlock to edit" : "Lock to prevent edits",
          onClick: async () => {
            await api(`/api/zones/${z.id}`, { method: "PATCH", body: { locked: !z.locked } });
            await loadZones();
          },
        }) },
      { header: "", width: "120px",
        cell: (z) => [
          actionButton("Edit", {
            title: "Or just click the zone on the camera",
            onClick: () => { pushUndo(); loadZoneIntoEditor(z); redrawCanvas(); },
          }),
          " ",
          actionButton("×", {
            class: "danger",
            confirm: `Delete zone "${z.name}"?`,
            onClick: async () => {
              await api(`/api/zones/${z.id}`, { method: "DELETE" });
              if (editingZoneId === z.id) clearWip(false);
              await loadZones();
            },
          }),
        ] },
    ],
  });
}

// ---------- public ----------
export async function loadZones() {
  try {
    cache = await api("/api/zones");
    redrawCanvas();
    renderList();
  } catch (e) { zonesListEl.textContent = "Error: " + e.message; }
}

// ---------- camera ----------
async function listCameras() {
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

async function startCam() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        deviceId: zCamSelect.value ? { exact: zCamSelect.value } : undefined,
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });
    zVideo.srcObject = stream;
    zVideo.style.display = "block";
    zBg.style.display = "none";
    await zVideo.play();
    sizeCanvas();
  } catch (e) { alert("Camera error: " + e.message); }
}

function stopCam() {
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
  zVideo.srcObject = null;
}

function takeBg() {
  if (!zVideo.videoWidth) { alert("Start camera first."); return; }
  const c = document.createElement("canvas");
  c.width = zVideo.videoWidth;
  c.height = zVideo.videoHeight;
  c.getContext("2d").drawImage(zVideo, 0, 0);
  zBg.src = c.toDataURL("image/png");
  zBg.style.display = "block";
  zVideo.style.display = "none";
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
  // Background image may take a moment to layout — re-size on next frame.
  requestAnimationFrame(sizeCanvas);
}

function sizeCanvas() {
  const rect = zoneStage.getBoundingClientRect();
  zDraw.width = rect.width;
  zDraw.height = rect.height;
  redrawCanvas();
}

// ---------- save ----------
async function save() {
  if (drawingPoints.length < 3) { alert("Need at least 3 points."); return; }
  const payload = {
    name: zoneNameInput.value.trim() || "zone",
    label: zoneLabelInput.value.trim(),
    color: zoneColorInput.value,
    polygon: drawingPoints,
    formation: zoneFormationSel.value || null,
  };
  try {
    if (editingZoneId) {
      const updated = await api(`/api/zones/${editingZoneId}`, { method: "PUT", body: payload });
      editingZoneId = updated.id;
    } else {
      const created = await api("/api/zones", { method: "POST", body: payload });
      editingZoneId = created.id;
    }
    await loadZones();
  } catch (e) { alert(e.message); }
}

// ---------- init / wire-up ----------
export function initZones() {
  zDraw.addEventListener("mousedown", onDown);
  zDraw.addEventListener("mousemove", onMove);
  // Capture mouseup at the window level so dragging off-canvas still releases.
  window.addEventListener("mouseup", onUp);
  window.addEventListener("resize", () => {
    if (!document.getElementById("tab-zones").hidden) sizeCanvas();
  });

  zoneEditFormationEl.addEventListener("change", () => {
    zoneFormationSel.value = zoneEditFormationEl.value;
    redrawCanvas();
    renderList();
  });

  zoneUndoBtn.addEventListener("click", undo);
  zoneRedoBtn.addEventListener("click", redo);
  zoneNewBtn.addEventListener("click", () => clearWip(true));
  zoneSaveBtn.addEventListener("click", save);

  zoneColorInput.addEventListener("input", redrawCanvas);

  zStartBtn.addEventListener("click", startCam);
  zStopBtn.addEventListener("click", stopCam);
  zSnapshotBtn.addEventListener("click", takeBg);
  seedZonesBtn.addEventListener("click", async () => {
    if (!confirm("Load default zone templates? Existing zones in those formations will be replaced.")) return;
    try {
      const created = await api("/api/zones/seed/defaults?replace=true", { method: "POST", body: {} });
      await loadZones();
      alert(`Loaded ${created.length} zones.`);
    } catch (e) { alert(e.message); }
  });

  // Keep the "draw a new zone" formation picker in sync with the editor filter on first paint.
  zoneFormationSel.value = zoneEditFormationEl.value;

  // Keyboard shortcuts (only when Zones tab is visible and not focused in a text input).
  window.addEventListener("keydown", (ev) => {
    if (document.getElementById("tab-zones").hidden) return;
    const t = ev.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
    const meta = ev.metaKey || ev.ctrlKey;
    if (meta && ev.key.toLowerCase() === "z" && !ev.shiftKey) { ev.preventDefault(); undo(); }
    else if (meta && (ev.key.toLowerCase() === "z" && ev.shiftKey)) { ev.preventDefault(); redo(); }
    else if (meta && ev.key.toLowerCase() === "y") { ev.preventDefault(); redo(); }
    else if (ev.key === "Escape") { clearWip(true); }
  });

  listCameras();
  refreshUndoButtons();
}
