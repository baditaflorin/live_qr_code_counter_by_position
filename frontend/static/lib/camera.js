// Shared webcam → JPEG → WebSocket streaming.
//
// Used by both the live counter (/) and the tracking page (/track). The
// caller supplies references to the <video> and overlay <canvas> elements
// plus a callback that receives each parsed message from /ws/detect.
//
// Usage:
//   const cam = new CameraStream({
//     video, overlayCanvas, statusEl, fpsEl,
//     onMessage: (msg, { videoWidth, videoHeight }) => { ... },
//   });
//   await cam.listDevices(selectEl);
//   await cam.start({ deviceId, width, height, fps });
//   ...
//   cam.stop();
//
// The class is intentionally framework-free (vanilla DOM) so any new mode
// can plug into the same JPEG+WS pipeline without re-implementing it.

export class CameraStream {
  constructor({ video, overlayCanvas, statusEl, fpsEl, wsPath = "/ws/detect" }) {
    this.video = video;
    this.overlay = overlayCanvas;
    this.statusEl = statusEl;
    this.fpsEl = fpsEl;
    this.wsPath = wsPath;
    this.onMessage = null;
    this.stream = null;
    this.ws = null;
    this.sendInterval = null;
    this.captureCanvas = document.createElement("canvas");
    this.captureCtx = this.captureCanvas.getContext("2d");
    this.fpsTimes = [];
  }

  setStatus(text, kind = "") {
    if (!this.statusEl) return;
    this.statusEl.textContent = text;
    this.statusEl.className = "status-pill " + kind;
  }

  async listDevices(selectEl) {
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
    } catch (e) {
      selectEl.innerHTML = '<option value="">(grant permission to list cameras)</option>';
    }
  }

  async start({ deviceId, width = 1280, height = 720, fps = 10, onMessage }) {
    this.onMessage = onMessage;
    this.setStatus("starting...");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: width },
          height: { ideal: height },
          deviceId: deviceId ? { exact: deviceId } : undefined,
        },
        audio: false,
      });
      this.video.srcObject = this.stream;
      await this.video.play();
      this._matchCanvasToVideo();
    } catch (e) {
      this.setStatus("camera error: " + e.message, "err");
      throw e;
    }

    this._openWs();
    const interval = Math.max(1, Math.round(1000 / fps));
    this.sendInterval = setInterval(() => this._sendFrame(), interval);
  }

  stop() {
    if (this.sendInterval) { clearInterval(this.sendInterval); this.sendInterval = null; }
    if (this.ws) { try { this.ws.close(); } catch (_) {} this.ws = null; }
    if (this.stream) { this.stream.getTracks().forEach((t) => t.stop()); this.stream = null; }
    this.video.srcObject = null;
    if (this.overlay) {
      const ctx = this.overlay.getContext("2d");
      ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);
    }
    this.setStatus("idle");
  }

  _matchCanvasToVideo() {
    this.captureCanvas.width = this.video.videoWidth;
    this.captureCanvas.height = this.video.videoHeight;
    if (this.overlay) {
      this.overlay.width = this.video.videoWidth;
      this.overlay.height = this.video.videoHeight;
    }
  }

  _openWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}${this.wsPath}`);
    this.ws.binaryType = "arraybuffer";
    this.ws.onopen = () => this.setStatus("live", "ok");
    this.ws.onclose = () => this.setStatus("disconnected", "err");
    this.ws.onerror = () => this.setStatus("ws error", "err");
    this.ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (!msg.ok) { console.warn("server:", msg.error); return; }
      this._tickFps();
      this.onMessage?.(msg, {
        videoWidth: this.video.videoWidth,
        videoHeight: this.video.videoHeight,
      });
    };
  }

  _tickFps() {
    if (!this.fpsEl) return;
    const now = performance.now();
    this.fpsTimes.push(now);
    while (this.fpsTimes.length && now - this.fpsTimes[0] > 1000) this.fpsTimes.shift();
    this.fpsEl.textContent = `${this.fpsTimes.length} fps`;
  }

  async _sendFrame() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    if (this.video.readyState < 2) return;
    if (
      this.captureCanvas.width !== this.video.videoWidth ||
      this.captureCanvas.height !== this.video.videoHeight
    ) {
      this._matchCanvasToVideo();
    }
    this.captureCtx.drawImage(this.video, 0, 0);
    const blob = await new Promise((r) => this.captureCanvas.toBlob(r, "image/jpeg", 0.7));
    if (!blob) return;
    if (this.ws.readyState !== WebSocket.OPEN) return;
    const buf = await blob.arrayBuffer();
    this.ws.send(buf);
  }
}
