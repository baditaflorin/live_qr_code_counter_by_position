import { api, el, clear, fmtTime } from "/static/common.js";

const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const cameraSelect = document.getElementById("camera-select");
const resolutionSel = document.getElementById("resolution");
const fpsSel = document.getElementById("fps");
const statusPill = document.getElementById("status");
const fpsActual = document.getElementById("fps-actual");
const zoneCountsEl = document.getElementById("zone-counts");
const detectedListEl = document.getElementById("detected-list");
const activeQuestionSel = document.getElementById("active-question");
const snapshotBtn = document.getElementById("snapshot-btn");
const lastSnapshotEl = document.getElementById("last-snapshot");

let mediaStream = null;
let ws = null;
let sendIntervalId = null;
let captureCanvas = document.createElement("canvas");
let captureCtx = captureCanvas.getContext("2d");
let lastResult = null;
let lastSentTimestamps = [];
let zonesCache = [];

function setStatus(text, kind = "") {
  statusPill.textContent = text;
  statusPill.className = "status-pill " + kind;
}

async function loadCameras() {
  try {
    // Need permission to see device labels.
    const tmp = await navigator.mediaDevices.getUserMedia({ video: true });
    tmp.getTracks().forEach((t) => t.stop());
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cams = devices.filter((d) => d.kind === "videoinput");
    cameraSelect.innerHTML = "";
    cams.forEach((c, i) => {
      const opt = document.createElement("option");
      opt.value = c.deviceId;
      opt.textContent = c.label || `Camera ${i + 1}`;
      cameraSelect.appendChild(opt);
    });
  } catch (e) {
    cameraSelect.innerHTML = '<option value="">(grant permission to list cameras)</option>';
  }
}

async function loadZones() {
  try {
    zonesCache = await api("/api/zones");
    renderZoneCounts({}, zonesCache);
  } catch (e) {
    console.error(e);
  }
}

async function loadQuestions() {
  try {
    const qs = await api("/api/questions");
    activeQuestionSel.innerHTML = '<option value="">— none —</option>' +
      qs.map((q) => `<option value="${q.id}" ${q.is_active ? "selected" : ""}>${escapeHtml(q.text)}</option>`).join("");
  } catch (e) {
    console.error(e);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function start() {
  startBtn.disabled = true;
  setStatus("starting...");
  const [w, h] = resolutionSel.value.split("x").map(Number);
  const constraints = {
    video: {
      width: { ideal: w },
      height: { ideal: h },
      deviceId: cameraSelect.value ? { exact: cameraSelect.value } : undefined,
    },
    audio: false,
  };
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
    video.srcObject = mediaStream;
    await video.play();
    captureCanvas.width = video.videoWidth;
    captureCanvas.height = video.videoHeight;
    overlay.width = video.videoWidth;
    overlay.height = video.videoHeight;
  } catch (e) {
    setStatus("camera error: " + e.message, "err");
    startBtn.disabled = false;
    return;
  }

  await loadZones();
  openWS();

  const fps = Number(fpsSel.value);
  const interval = Math.max(1, Math.round(1000 / fps));
  sendIntervalId = setInterval(sendFrame, interval);
  stopBtn.disabled = false;
}

function stop() {
  if (sendIntervalId) { clearInterval(sendIntervalId); sendIntervalId = null; }
  if (ws) { try { ws.close(); } catch (_) {} ws = null; }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  video.srcObject = null;
  setStatus("idle");
  stopBtn.disabled = true;
  startBtn.disabled = false;
  clearOverlay();
}

function openWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/detect`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => setStatus("live", "ok");
  ws.onclose = () => setStatus("disconnected", "err");
  ws.onerror = () => setStatus("ws error", "err");
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (!msg.ok) {
        console.warn("server:", msg.error);
        return;
      }
      lastResult = msg;
      drawOverlay(msg);
      renderZoneCounts(msg.zone_counts || {}, zonesCache);
      renderDetected(msg.detections || []);
      tickFps();
    } catch (e) {
      console.error(e);
    }
  };
}

function tickFps() {
  const now = performance.now();
  lastSentTimestamps.push(now);
  while (lastSentTimestamps.length && now - lastSentTimestamps[0] > 1000) lastSentTimestamps.shift();
  fpsActual.textContent = `${lastSentTimestamps.length} fps`;
}

async function sendFrame() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  if (video.readyState < 2) return;
  if (captureCanvas.width !== video.videoWidth || captureCanvas.height !== video.videoHeight) {
    captureCanvas.width = video.videoWidth;
    captureCanvas.height = video.videoHeight;
    overlay.width = video.videoWidth;
    overlay.height = video.videoHeight;
  }
  captureCtx.drawImage(video, 0, 0);
  const blob = await new Promise((r) => captureCanvas.toBlob(r, "image/jpeg", 0.7));
  if (!blob) return;
  const buf = await blob.arrayBuffer();
  if (ws.readyState === WebSocket.OPEN) ws.send(buf);
}

function clearOverlay() {
  const ctx = overlay.getContext("2d");
  ctx.clearRect(0, 0, overlay.width, overlay.height);
}

function drawOverlay(msg) {
  const ctx = overlay.getContext("2d");
  const w = overlay.width;
  const h = overlay.height;
  ctx.clearRect(0, 0, w, h);

  // Draw zones
  for (const z of zonesCache) {
    if (!z.polygon || z.polygon.length < 3) continue;
    ctx.beginPath();
    z.polygon.forEach(([x, y], i) => {
      const px = x * w;
      const py = y * h;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fillStyle = hexToRgba(z.color, 0.18);
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = z.color;
    ctx.stroke();
    // Label
    const cx = (z.polygon.reduce((a, p) => a + p[0], 0) / z.polygon.length) * w;
    const cy = (z.polygon.reduce((a, p) => a + p[1], 0) / z.polygon.length) * h;
    ctx.font = "bold 22px sans-serif";
    ctx.fillStyle = z.color;
    ctx.strokeStyle = "rgba(0,0,0,0.7)";
    ctx.lineWidth = 4;
    const text = z.label || z.name;
    const count = (msg.zone_counts || {})[z.id] || 0;
    const txt = `${text}: ${count}`;
    const m = ctx.measureText(txt);
    ctx.strokeText(txt, cx - m.width / 2, cy);
    ctx.fillText(txt, cx - m.width / 2, cy);
  }

  // Draw detections
  for (const d of msg.detections || []) {
    ctx.beginPath();
    d.corners_norm.forEach(([x, y], i) => {
      const px = x * w;
      const py = y * h;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
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
    ctx.font = "bold 14px sans-serif";
    ctx.lineWidth = 4;
    ctx.strokeStyle = "rgba(0,0,0,0.8)";
    ctx.fillStyle = "#ffffff";
    ctx.strokeText(label, cx + 8, cy - 8);
    ctx.fillText(label, cx + 8, cy - 8);
  }
}

function hexToRgba(hex, a) {
  const m = /^#?([a-f0-9]{6})$/i.exec(hex || "#22c55e");
  if (!m) return `rgba(34,197,94,${a})`;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function renderZoneCounts(counts, zones) {
  clear(zoneCountsEl);
  if (!zones || zones.length === 0) {
    zoneCountsEl.appendChild(el("div", { class: "muted" }, "No zones yet — go to Admin → Zones."));
    return;
  }
  for (const z of zones) {
    const c = counts[z.id] || 0;
    zoneCountsEl.appendChild(
      el("div", { class: "item", style: { borderLeft: `4px solid ${z.color}` } },
        el("div", {},
          el("div", { class: "label" }, z.label || z.name),
          el("div", { class: "name" }, z.name),
        ),
        el("div", { class: "count" }, String(c)),
      )
    );
  }
  // Add "unzoned" if any
  const unzoned = (lastResult?.detections || []).filter((d) => d.zone_id == null).length;
  if (unzoned > 0) {
    zoneCountsEl.appendChild(
      el("div", { class: "item", style: { borderLeft: "4px solid #64748b" } },
        el("div", {},
          el("div", { class: "label" }, "Unzoned"),
          el("div", { class: "name" }, "outside any zone"),
        ),
        el("div", { class: "count" }, String(unzoned)),
      )
    );
  }
}

function renderDetected(detections) {
  if (!detections.length) {
    detectedListEl.textContent = "No markers in view.";
    detectedListEl.classList.add("muted");
    return;
  }
  detectedListEl.classList.remove("muted");
  clear(detectedListEl);
  const tbl = el("table", {});
  tbl.appendChild(el("thead", {}, el("tr", {},
    el("th", {}, "ID"),
    el("th", {}, "Person"),
    el("th", {}, "Zone"),
  )));
  const tb = el("tbody", {});
  detections.sort((a, b) => a.aruco_id - b.aruco_id);
  for (const d of detections) {
    tb.appendChild(el("tr", {},
      el("td", {}, "#" + d.aruco_id),
      el("td", {}, d.person_name || "—"),
      el("td", {}, d.zone_label || "—"),
    ));
  }
  tbl.appendChild(tb);
  detectedListEl.appendChild(tbl);
}

snapshotBtn.addEventListener("click", async () => {
  const qid = activeQuestionSel.value;
  if (!qid) { alert("Pick an active question first (or create one in Admin → Questions)."); return; }
  if (!lastResult || !lastResult.detections) {
    alert("No detections yet — start the camera first.");
    return;
  }
  const payload = {
    detections: lastResult.detections.map((d) => ({
      aruco_id: d.aruco_id,
      zone_id: d.zone_id,
      zone_label: d.zone_label,
    })),
  };
  try {
    const res = await api(`/api/questions/${qid}/snapshot/record`, { method: "POST", body: payload });
    lastSnapshotEl.textContent = `Saved snapshot #${res.snapshot_id} with ${res.votes} markers at ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    alert("Snapshot failed: " + e.message);
  }
});

activeQuestionSel.addEventListener("change", async () => {
  const qid = activeQuestionSel.value;
  try {
    if (qid) {
      await api(`/api/questions/${qid}/activate`, { method: "PUT" });
    } else {
      await api(`/api/questions/deactivate-all`, { method: "PUT" });
    }
  } catch (e) {
    console.error(e);
  }
});

startBtn.addEventListener("click", start);
stopBtn.addEventListener("click", stop);

// boot
loadCameras();
loadZones();
loadQuestions();
