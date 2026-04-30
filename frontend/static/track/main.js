// /track entry. Composes:
//   - shared CameraStream (lib/camera.js) for webcam → /ws/detect plumbing
//   - clusters.js for live cluster overlay
//   - session.js for start/stop/list
//   - report.js for per-session reports

import { CameraStream } from "/static/lib/camera.js";
import { computeClusters, drawClusters } from "./clusters.js";
import { initSession, refresh as refreshSessions, formatDuration } from "./session.js";
import { showReport } from "./report.js";

// ---------- DOM ----------
const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const startCamBtn = document.getElementById("start-cam-btn");
const stopCamBtn = document.getElementById("stop-cam-btn");
const cameraSelect = document.getElementById("camera-select");
const resolutionSel = document.getElementById("resolution");
const fpsSel = document.getElementById("fps");
const statusPill = document.getElementById("status");
const fpsActual = document.getElementById("fps-actual");
const detectedListEl = document.getElementById("detected-list");
const clusterListEl = document.getElementById("cluster-list");
const proximityVisInput = document.getElementById("proximity-vis");

// ---------- camera stream ----------
const cam = new CameraStream({
  video,
  overlayCanvas: overlay,
  statusEl: statusPill,
  fpsEl: fpsActual,
});
cam.listDevices(cameraSelect);

let lastMsg = null;

startCamBtn.addEventListener("click", async () => {
  startCamBtn.disabled = true;
  const [w, h] = resolutionSel.value.split("x").map(Number);
  const fps = Number(fpsSel.value);
  try {
    await cam.start({
      deviceId: cameraSelect.value,
      width: w, height: h, fps,
      onMessage: onWs,
    });
    stopCamBtn.disabled = false;
  } catch (e) {
    startCamBtn.disabled = false;
  }
});

stopCamBtn.addEventListener("click", () => {
  cam.stop();
  startCamBtn.disabled = false;
  stopCamBtn.disabled = true;
});

// ---------- WS message handler ----------
function onWs(msg) {
  lastMsg = msg;
  redraw();
  renderDetected(msg.detections || []);
  // Active tracking session changed under us (e.g. server stopped it)?
  // session.js polls separately so we don't need to rerender here, but
  // refresh stats every second if a session is live.
  if (msg.active_tracking) {
    bumpActiveStatsIfStale(msg.active_tracking);
  }
}

let lastActiveBump = 0;
function bumpActiveStatsIfStale(active) {
  const now = performance.now();
  if (now - lastActiveBump < 1500) return;
  lastActiveBump = now;
  refreshSessions();
}

// ---------- cluster overlay ----------
function redraw() {
  const ctx = overlay.getContext("2d");
  const w = overlay.width;
  const h = overlay.height;
  ctx.clearRect(0, 0, w, h);

  if (!lastMsg) return;
  const detections = lastMsg.detections || [];
  const proximity = parseFloat(proximityVisInput.value) || 0.12;

  // Cluster hulls first (drawn underneath markers).
  const clusters = computeClusters(detections, proximity);
  drawClusters(ctx, clusters, w, h);

  // Marker outlines + IDs (inline, since we don't depend on live.js draw code).
  for (const d of detections) {
    ctx.beginPath();
    d.corners_norm.forEach(([x, y], i) => {
      const px = x * w, py = y * h;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#22d3ee";
    ctx.stroke();

    const [cx, cy] = [d.center_norm[0] * w, d.center_norm[1] * h];
    ctx.fillStyle = "#22d3ee";
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fill();

    const label = d.person_name ? `${d.person_name} (#${d.aruco_id})` : `#${d.aruco_id}`;
    ctx.font = "bold 13px sans-serif";
    ctx.lineWidth = 4;
    ctx.strokeStyle = "rgba(0,0,0,0.85)";
    ctx.fillStyle = "#ffffff";
    ctx.strokeText(label, cx + 8, cy - 8);
    ctx.fillText(label, cx + 8, cy - 8);
  }

  // Cluster sidebar list — current state.
  renderClusterList(clusters);
}

function renderClusterList(clusters) {
  if (!clusters.length) {
    clusterListEl.innerHTML = '<div class="muted">No clusters right now (need 2+ markers within proximity).</div>';
    return;
  }
  clusterListEl.innerHTML = "";
  clusters.forEach((c, i) => {
    const div = document.createElement("div");
    div.style.padding = "8px 10px";
    div.style.borderLeft = "4px solid var(--accent-2)";
    div.style.background = "var(--panel-2)";
    div.style.marginBottom = "6px";
    div.style.borderRadius = "4px";
    const names = c.map((d) => d.person_name || `#${d.aruco_id}`).join(", ");
    div.innerHTML = `<div style="font-weight:600;">Cluster ${i + 1} (${c.length})</div>
                     <div style="font-size:12px; color:#94a3b8;">${escapeHtml(names)}</div>`;
    clusterListEl.appendChild(div);
  });
}

function renderDetected(detections) {
  if (!detections.length) {
    detectedListEl.innerHTML = '<span class="muted">No markers in view.</span>';
    return;
  }
  detectedListEl.innerHTML =
    `<div class="muted">${detections.length} markers visible.</div>`;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
  }[c]));
}

// Re-render overlay when proximity slider changes.
proximityVisInput.addEventListener("input", redraw);

// ---------- sessions ----------
initSession({
  onSelectReport: (id) => showReport(id),
  onActiveChange: (active) => {
    // If a session was just started and the camera isn't running, prompt
    // the user. Otherwise just continue.
    if (active && !cam.stream) {
      console.warn("Tracking session started but camera is off — start the camera to record positions.");
    }
  },
});

// Poll active session every 3s so the banner stays fresh while tracking.
setInterval(() => refreshSessions(), 3000);
