// Admin tab for camera intrinsic + extrinsic calibration (ADR 0048 + 0012).
//
// Two flows live here:
//
//   1. Intrinsic — open the laptop's webcam, capture JPEG frames of a
//      printed ChArUco board, POST each frame to the backend; backend keeps
//      novel views and surfaces "20/20 ready" once enough have been seen.
//      Hitting "Compute calibration" runs the OpenCV solver and persists K
//      + dist on the Camera row.
//
//   2. Extrinsic — open the live /ws/detect feed; once the four reserved
//      corner markers are all visible (the backend tells us so via
//      `calibration_hint`), the operator hits "Solve extrinsic" which
//      ships the corner pixel centers to the backend's PnP solver.

import { api, el, clear, fmtTime } from "/static/common.js";

const listEl = () => document.getElementById("cameras-list");
const intrinsicPanel = () => document.getElementById("intrinsic-panel");
const extrinsicPanel = () => document.getElementById("extrinsic-panel");

let activeCameraId = null;
let cameras = [];

export async function loadCameras() {
  try {
    cameras = await api("/api/cameras");
    if (!activeCameraId && cameras.length) activeCameraId = cameras[0].id;
    renderList();
    if (activeCameraId) {
      const cam = cameras.find((c) => c.id === activeCameraId);
      if (cam) {
        intrinsicPanel().hidden = false;
        extrinsicPanel().hidden = !cam.intrinsic_calibrated;
        syncExtrinsicForm(cam);
      }
    }
  } catch (e) { listEl().textContent = "Error: " + e.message; }
}

function renderList() {
  const root = listEl();
  clear(root);
  for (const c of cameras) {
    const row = el("div", { class: "panel", style: { padding: "12px", marginBottom: "8px" } });
    const head = el("div", { class: "row" });
    head.appendChild(el("strong", {}, `${c.name} (id ${c.id})`));
    head.appendChild(el("span", { class: "spacer" }));
    head.appendChild(intrinsicBadge(c));
    head.appendChild(extrinsicBadge(c));
    row.appendChild(head);

    const meta = el("div", { class: "muted", style: { fontSize: "12px", marginTop: "6px" } });
    meta.innerHTML = `marker side ${c.marker_size_m} m · floor rect ${c.floor_rect_w_m} × ${c.floor_rect_h_m} m · `
      + `corners TL=${c.corner_ids?.tl ?? "?"} TR=${c.corner_ids?.tr ?? "?"} BR=${c.corner_ids?.br ?? "?"} BL=${c.corner_ids?.bl ?? "?"}`;
    row.appendChild(meta);

    if (c.intrinsic_calibrated) {
      const det = el("div", { class: "muted", style: { fontSize: "12px", marginTop: "4px" } },
        `intrinsic: ${c.intrinsic_image_w}×${c.intrinsic_image_h}, `
        + `reproj err ${c.intrinsic_reproj_error_px?.toFixed(3)} px, `
        + `at ${fmtTime(c.intrinsic_calibrated_at)}`);
      row.appendChild(det);
    }
    if (c.extrinsic_calibrated && c.camera_position_world_m) {
      const p = c.camera_position_world_m;
      row.appendChild(el("div", { class: "muted", style: { fontSize: "12px", marginTop: "4px" } },
        `extrinsic: camera at world (${p[0].toFixed(2)}, ${p[1].toFixed(2)}, ${p[2].toFixed(2)}) m, `
        + `reproj err ${c.extrinsic_reproj_error_px?.toFixed(3)} px`));
    }

    const actions = el("div", { class: "row", style: { marginTop: "8px" } });
    actions.appendChild(el("button", {
      onclick: () => { activeCameraId = c.id; loadCameras(); },
    }, "Calibrate this camera"));
    if (c.intrinsic_calibrated) {
      actions.appendChild(el("button", {
        class: "danger",
        onclick: async () => {
          if (!confirm("Forget the intrinsic calibration? You'll need to redo the ChArUco capture.")) return;
          await api(`/api/cameras/${c.id}/intrinsic`, { method: "DELETE" });
          await loadCameras();
        },
      }, "Clear intrinsic"));
    }
    if (c.extrinsic_calibrated) {
      actions.appendChild(el("button", {
        class: "danger",
        onclick: async () => {
          if (!confirm("Forget the extrinsic? You'll need to re-show the four corner markers.")) return;
          await api(`/api/cameras/${c.id}/extrinsic`, { method: "DELETE" });
          await loadCameras();
        },
      }, "Clear extrinsic"));
    }
    if (c.id !== 1) {
      actions.appendChild(el("button", {
        class: "danger",
        onclick: async () => {
          if (!confirm(`Delete camera ${c.id} (${c.name})? Calibration is lost.`)) return;
          await api(`/api/cameras/${c.id}`, { method: "DELETE" });
          if (activeCameraId === c.id) activeCameraId = 1;
          await loadCameras();
        },
      }, "Delete camera"));
    }
    row.appendChild(actions);
    root.appendChild(row);
  }
}

function intrinsicBadge(c) {
  return el("span", {
    class: "status-pill " + (c.intrinsic_calibrated ? "ok" : "err"),
    style: { fontSize: "11px" },
  }, c.intrinsic_calibrated ? "intrinsic ✓" : "intrinsic ✗");
}
function extrinsicBadge(c) {
  return el("span", {
    class: "status-pill " + (c.extrinsic_calibrated ? "ok" : "err"),
    style: { fontSize: "11px" },
  }, c.extrinsic_calibrated ? "extrinsic ✓" : "extrinsic ✗");
}

// ---------- intrinsic capture flow ----------------------------------------

const ic = {
  stream: null,
  sessionId: null,
  captureCanvas: document.createElement("canvas"),
  uploadInterval: null,
  videoEl: () => document.getElementById("ic-video"),
  status: (text, kind = "") => {
    const el = document.getElementById("ic-status");
    if (el) { el.textContent = text; el.className = "status-pill " + kind; }
  },
};

async function listVideoDevices(selectEl) {
  try {
    const tmp = await navigator.mediaDevices.getUserMedia({ video: true });
    tmp.getTracks().forEach((t) => t.stop());
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cams = devices.filter((d) => d.kind === "videoinput");
    selectEl.innerHTML = "";
    cams.forEach((c, i) => {
      const opt = document.createElement("option");
      opt.value = c.deviceId;
      opt.textContent = c.label || `Camera ${i + 1}`;
      selectEl.appendChild(opt);
    });
  } catch {
    selectEl.innerHTML = '<option value="">(grant camera permission)</option>';
  }
}

async function startIntrinsicCapture() {
  if (!activeCameraId) { alert("Pick a camera row first."); return; }
  const sel = document.getElementById("ic-device-select");
  const [w, h] = document.getElementById("ic-resolution").value.split("x").map(Number);
  try {
    ic.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: w }, height: { ideal: h },
        deviceId: sel.value ? { exact: sel.value } : undefined,
      },
      audio: false,
    });
    ic.videoEl().srcObject = ic.stream;
    await ic.videoEl().play();
  } catch (e) { ic.status("camera error: " + e.message, "err"); throw e; }

  const sess = await api(`/api/cameras/${activeCameraId}/calibration/intrinsic/start`, { method: "POST" });
  ic.sessionId = sess.session_id;
  ic.status("capturing", "ok");
  document.getElementById("ic-finish-btn").disabled = false;
  document.getElementById("ic-cancel-btn").disabled = false;
  document.getElementById("ic-start-btn").disabled = true;
  setProgress(sess);

  // Throttle uploads to 2 fps — well above the rate at which a human moves
  // the board, well below the rate that would saturate the upstream bandwidth.
  ic.uploadInterval = setInterval(uploadIntrinsicFrame, 500);
}

async function uploadIntrinsicFrame() {
  if (!ic.sessionId) return;
  const v = ic.videoEl();
  if (v.readyState < 2) return;
  if (ic.captureCanvas.width !== v.videoWidth || ic.captureCanvas.height !== v.videoHeight) {
    ic.captureCanvas.width = v.videoWidth;
    ic.captureCanvas.height = v.videoHeight;
  }
  const ctx = ic.captureCanvas.getContext("2d");
  ctx.drawImage(v, 0, 0);
  const blob = await new Promise((r) => ic.captureCanvas.toBlob(r, "image/jpeg", 0.85));
  if (!blob) return;
  try {
    const buf = await blob.arrayBuffer();
    const res = await fetch(
      `/api/cameras/${activeCameraId}/calibration/intrinsic/${ic.sessionId}/frame`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: buf }
    );
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      document.getElementById("ic-message").textContent = "⚠️ " + (j.detail || `HTTP ${res.status}`);
      return;
    }
    const status = await res.json();
    setProgress(status);
  } catch (e) {
    document.getElementById("ic-message").textContent = "upload error: " + e.message;
  }
}

function setProgress(status) {
  const pct = Math.min(100, Math.round(100 * status.views_accepted / status.views_required));
  document.getElementById("ic-views-fill").style.width = pct + "%";
  document.getElementById("ic-views-label").textContent =
    `${status.views_accepted} / ${status.views_required} views captured`;
  document.getElementById("ic-message").textContent = status.message || "";
}

async function finishIntrinsicCalibration() {
  if (!ic.sessionId) return;
  document.getElementById("ic-finish-btn").disabled = true;
  ic.status("computing...", "");
  try {
    const result = await api(
      `/api/cameras/${activeCameraId}/calibration/intrinsic/${ic.sessionId}/finish`,
      { method: "POST" }
    );
    document.getElementById("ic-result").innerHTML =
      `<strong style="color: var(--ok);">✓ Calibration saved</strong> — `
      + `reproj error ${result.reproj_error_px.toFixed(3)} px over ${result.views_used} views.`;
    ic.status("done", "ok");
    stopIntrinsicCapture(/*keepResult*/ true);
    await loadCameras();
  } catch (e) {
    document.getElementById("ic-result").innerHTML = `<span style="color: var(--err);">✗ ${e.message}</span>`;
    document.getElementById("ic-finish-btn").disabled = false;
    ic.status("error", "err");
  }
}

function stopIntrinsicCapture(keepResult = false) {
  if (ic.uploadInterval) { clearInterval(ic.uploadInterval); ic.uploadInterval = null; }
  if (ic.stream) { ic.stream.getTracks().forEach((t) => t.stop()); ic.stream = null; }
  ic.videoEl().srcObject = null;
  if (!keepResult && ic.sessionId) {
    fetch(`/api/cameras/${activeCameraId}/calibration/intrinsic/${ic.sessionId}`, { method: "DELETE" })
      .catch(() => {});
  }
  ic.sessionId = null;
  document.getElementById("ic-finish-btn").disabled = true;
  document.getElementById("ic-cancel-btn").disabled = true;
  document.getElementById("ic-start-btn").disabled = false;
  if (!keepResult) ic.status("idle", "");
}

// ---------- extrinsic flow ------------------------------------------------

const ex = {
  stream: null,
  ws: null,
  sendInterval: null,
  captureCanvas: document.createElement("canvas"),
  lastHint: null,
  lastFrameSize: { w: 0, h: 0 },
};

function syncExtrinsicForm(cam) {
  document.getElementById("ex-floor-w").value = cam.floor_rect_w_m;
  document.getElementById("ex-floor-h").value = cam.floor_rect_h_m;
  document.getElementById("ex-marker-size").value = cam.marker_size_m;
  const ids = cam.corner_ids || {};
  document.getElementById("ex-corner-ids").textContent =
    `TL=${ids.tl}  TR=${ids.tr}  BR=${ids.br}  BL=${ids.bl}`;
  // Print-sheet href is the static /api/calibration/corner-markers-pdf endpoint
  // (set in admin.html). It renders the four reserved corner ids directly from
  // the active camera, which the markers/pdf endpoint can't do because corner
  // ids aren't person-marker rows.
}

async function saveExtrinsicSettings() {
  if (!activeCameraId) return;
  const body = {
    floor_rect_w_m: Number(document.getElementById("ex-floor-w").value),
    floor_rect_h_m: Number(document.getElementById("ex-floor-h").value),
    marker_size_m:  Number(document.getElementById("ex-marker-size").value),
  };
  try {
    await api(`/api/cameras/${activeCameraId}`, { method: "PUT", body });
    await loadCameras();
  } catch (e) { alert(e.message); }
}

async function startExtrinsicCamera() {
  const sel = document.getElementById("ex-device-select");
  const [w, h] = document.getElementById("ex-resolution").value.split("x").map(Number);
  try {
    ex.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: w }, height: { ideal: h },
        deviceId: sel.value ? { exact: sel.value } : undefined,
      },
      audio: false,
    });
    document.getElementById("ex-video").srcObject = ex.stream;
    await document.getElementById("ex-video").play();
  } catch (e) { alert("camera error: " + e.message); throw e; }

  ex.ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/detect`);
  ex.ws.binaryType = "arraybuffer";
  ex.ws.onopen = () => setExStatus("live", "ok");
  ex.ws.onclose = () => setExStatus("disconnected", "err");
  ex.ws.onmessage = (evt) => {
    let msg; try { msg = JSON.parse(evt.data); } catch { return; }
    if (!msg.ok) return;
    handleExFrame(msg);
  };
  ex.sendInterval = setInterval(sendExFrame, 200);
  document.getElementById("ex-stop-cam").disabled = false;
  document.getElementById("ex-start-cam").disabled = true;
}

function stopExtrinsicCamera() {
  if (ex.sendInterval) { clearInterval(ex.sendInterval); ex.sendInterval = null; }
  if (ex.ws) { try { ex.ws.close(); } catch {} ex.ws = null; }
  if (ex.stream) { ex.stream.getTracks().forEach((t) => t.stop()); ex.stream = null; }
  document.getElementById("ex-video").srcObject = null;
  const c = document.getElementById("ex-overlay");
  c.getContext("2d").clearRect(0, 0, c.width, c.height);
  document.getElementById("ex-stop-cam").disabled = true;
  document.getElementById("ex-start-cam").disabled = false;
  document.getElementById("ex-solve").disabled = true;
  setExStatus("idle", "");
}

async function sendExFrame() {
  if (!ex.ws || ex.ws.readyState !== WebSocket.OPEN) return;
  const v = document.getElementById("ex-video");
  if (v.readyState < 2) return;
  if (ex.captureCanvas.width !== v.videoWidth) {
    ex.captureCanvas.width = v.videoWidth;
    ex.captureCanvas.height = v.videoHeight;
  }
  ex.captureCanvas.getContext("2d").drawImage(v, 0, 0);
  const blob = await new Promise((r) => ex.captureCanvas.toBlob(r, "image/jpeg", 0.7));
  if (!blob) return;
  if (ex.ws.readyState !== WebSocket.OPEN) return;
  ex.ws.send(await blob.arrayBuffer());
}

function handleExFrame(msg) {
  ex.lastFrameSize = { w: msg.frame_w, h: msg.frame_h };
  ex.lastHint = msg.calibration_hint;
  const overlay = document.getElementById("ex-overlay");
  overlay.width = msg.frame_w;
  overlay.height = msg.frame_h;
  const ctx = overlay.getContext("2d");
  ctx.clearRect(0, 0, overlay.width, overlay.height);

  const seen = (ex.lastHint && ex.lastHint.corners_visible_px) || {};
  const expected = ["tl", "tr", "br", "bl"];
  const dotR = Math.max(8, Math.min(overlay.width, overlay.height) / 80);
  const labelOffset = dotR + 4;
  for (const k of expected) {
    const px = seen[k];
    ctx.lineWidth = 2;
    ctx.strokeStyle = px ? "#22c55e" : "#ef4444";
    ctx.fillStyle = px ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)";
    if (px) {
      ctx.beginPath();
      ctx.arc(px[0], px[1], dotR, 0, Math.PI * 2);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.font = `${dotR * 1.6}px ui-monospace, monospace`;
      ctx.fillText(k.toUpperCase(), px[0] + labelOffset, px[1] - labelOffset);
    }
  }

  const status = document.getElementById("ex-corners-status");
  if (!ex.lastHint) {
    status.textContent = "Waiting for camera to load…";
  } else {
    const present = expected.filter((k) => seen[k]);
    const missing = expected.filter((k) => !seen[k]);
    status.innerHTML = `Visible: <strong>${present.length} / 4</strong>` +
      (missing.length ? ` — missing ${missing.map((m) => m.toUpperCase()).join(", ")}` : "");
  }
  document.getElementById("ex-solve").disabled = !(ex.lastHint && ex.lastHint.all_four_visible);
}

function setExStatus(text, kind = "") {
  const el = document.getElementById("ex-status");
  if (el) { el.textContent = text; el.className = "status-pill " + kind; }
}

async function solveExtrinsic() {
  if (!ex.lastHint || !ex.lastHint.all_four_visible) return;
  try {
    const result = await api(`/api/cameras/${activeCameraId}/calibration/extrinsic/auto`, {
      method: "POST",
      body: { corners: ex.lastHint.corners_visible_px },
    });
    document.getElementById("ex-result").innerHTML =
      `<strong style="color: var(--ok);">✓ Extrinsic saved</strong> — reproj error ${result.reproj_error_px.toFixed(3)} px.`;
    await loadCameras();
  } catch (e) {
    document.getElementById("ex-result").innerHTML = `<span style="color: var(--err);">✗ ${e.message}</span>`;
  }
}

// ---------- init ----------------------------------------------------------

export function initCameras() {
  document.getElementById("ic-start-btn").addEventListener("click", () => startIntrinsicCapture());
  document.getElementById("ic-finish-btn").addEventListener("click", () => finishIntrinsicCalibration());
  document.getElementById("ic-cancel-btn").addEventListener("click", () => stopIntrinsicCapture(false));
  document.getElementById("ex-save-settings").addEventListener("click", () => saveExtrinsicSettings());
  document.getElementById("ex-start-cam").addEventListener("click", () => startExtrinsicCamera());
  document.getElementById("ex-stop-cam").addEventListener("click", () => stopExtrinsicCamera());
  document.getElementById("ex-solve").addEventListener("click", () => solveExtrinsic());

  const addBtn = document.getElementById("add-camera-btn");
  if (addBtn) addBtn.addEventListener("click", async () => {
    const nameInput = document.getElementById("new-camera-name");
    const name = (nameInput.value || "").trim();
    try {
      const created = await api("/api/cameras", {
        method: "POST",
        body: { name: name || null },
      });
      nameInput.value = "";
      activeCameraId = created.id;
      await loadCameras();
    } catch (e) {
      alert("Add camera failed: " + e.message);
    }
  });

  // Lazy-list video devices when the tab opens.
  const onTabSwitch = new MutationObserver(() => {
    if (!document.getElementById("tab-cameras").hidden) {
      listVideoDevices(document.getElementById("ic-device-select"));
      listVideoDevices(document.getElementById("ex-device-select"));
    }
  });
  onTabSwitch.observe(document.getElementById("tab-cameras"), { attributes: true, attributeFilter: ["hidden"] });
}
