// Tracking-session report rendering.
import { api, el, clear, fmtTime } from "/static/common.js";
import { formatDuration } from "./session.js";
import { computeClusters, drawClusters } from "./clusters.js";

const reportPanel = document.getElementById("track-report-panel");
const reportBody = document.getElementById("track-report-body");

export async function showReport(sessionId) {
  reportPanel.hidden = false;
  clear(reportBody);
  reportBody.appendChild(el("div", { class: "muted" }, "Loading report…"));
  try {
    const r = await api(`/api/tracking/sessions/${sessionId}/report`);
    render(r);
  } catch (e) {
    reportBody.textContent = "Error: " + e.message;
  }
}

export function hideReport() {
  reportPanel.hidden = true;
}

function nameOf(p) {
  return p?.name || (p?.id != null ? "#" + p.id : "—");
}

function pairLabel(row, side) {
  const id = side === "a" ? row.a : row.b;
  const name = side === "a" ? row.a_name : row.b_name;
  return name ? `${name} (#${id})` : `#${id}`;
}

function render(r) {
  clear(reportBody);
  const s = r.session;

  // Header — session metadata.
  const headerPanel = el("div", { class: "panel", style: { background: "var(--panel-2)" } });
  headerPanel.appendChild(el("h3", { style: { marginTop: 0 } }, s.name));
  const status = s.stopped_at
    ? el("span", { class: "status-pill" }, "ended " + fmtTime(s.stopped_at))
    : el("span", { class: "status-pill ok" }, "still recording");
  headerPanel.appendChild(el("div", {}, status));

  const metaRow = el("div", { class: "row", style: { marginTop: "8px" } });
  metaRow.appendChild(el("span", { class: "muted" }, `started ${fmtTime(s.started_at)}`));
  metaRow.appendChild(el("span", { class: "muted" }, `· duration ${formatDuration(r.duration_s)}`));
  metaRow.appendChild(el("span", { class: "muted" }, `· ${r.snapshot_count} snapshots`));
  metaRow.appendChild(el("span", { class: "muted" }, `· ${r.sample_count} samples`));
  metaRow.appendChild(el("span", { class: "muted" }, `· proximity=${s.proximity_norm}`));
  metaRow.appendChild(el("span", { class: "muted" }, `· every ${s.sample_interval_ms}ms`));
  headerPanel.appendChild(metaRow);
  reportBody.appendChild(headerPanel);

  // Summary tiles.
  const tiles = el("div", { class: "row", style: { marginBottom: "12px" } });
  tile(tiles, "Markers seen", String(r.markers_seen.length));
  tile(tiles, "Pairs that met", String(r.pair_contact_seconds.length));
  tile(tiles, "Pairs that never met", String(r.never_met_pairs.length));
  reportBody.appendChild(tiles);

  // Pair contact time table.
  const pairsPanel = el("div", { class: "panel" });
  pairsPanel.appendChild(el("h4", { style: { marginTop: 0 } }, "Who spent time together"));
  if (!r.pair_contact_seconds.length) {
    pairsPanel.appendChild(el("div", { class: "muted" }, "No pair was within proximity at the same time."));
  } else {
    const tbl = el("table", {});
    tbl.appendChild(el("thead", {}, el("tr", {},
      el("th", {}, "A"), el("th", {}, "B"), el("th", {}, "Time"), el("th", {}, "Snapshots"),
    )));
    const tb = el("tbody", {});
    for (const p of r.pair_contact_seconds) {
      tb.appendChild(el("tr", {},
        el("td", {}, pairLabel(p, "a")),
        el("td", {}, pairLabel(p, "b")),
        el("td", {}, formatSeconds(p.seconds)),
        el("td", { class: "muted" }, String(p.snapshots)),
      ));
    }
    tbl.appendChild(tb);
    pairsPanel.appendChild(tbl);
  }
  reportBody.appendChild(pairsPanel);

  // Per-person totals.
  const peoplePanel = el("div", { class: "panel" });
  peoplePanel.appendChild(el("h4", { style: { marginTop: 0 } }, "Time spent in clusters per person"));
  if (!r.per_person_contact_seconds.length) {
    peoplePanel.appendChild(el("div", { class: "muted" }, "No person was tracked."));
  } else {
    const tbl = el("table", {});
    tbl.appendChild(el("thead", {}, el("tr", {},
      el("th", {}, "Person / marker"), el("th", {}, "Total time in clusters"),
    )));
    const tb = el("tbody", {});
    for (const p of r.per_person_contact_seconds) {
      const label = p.person_name ? `${p.person_name} (#${p.aruco_id})` : `#${p.aruco_id}`;
      tb.appendChild(el("tr", {},
        el("td", {}, label),
        el("td", {}, formatSeconds(p.seconds)),
      ));
    }
    tbl.appendChild(tb);
    peoplePanel.appendChild(tbl);
  }
  reportBody.appendChild(peoplePanel);

  // Timeline scrubber (ADR 0008) — fetches NDJSON, renders cluster hulls
  // at the chosen frame.
  reportBody.appendChild(buildTimelineScrubber(s.id));

  // Never-met pairs.
  const neverPanel = el("div", { class: "panel" });
  neverPanel.appendChild(el("h4", { style: { marginTop: 0 } }, `Pairs that never met (${r.never_met_pairs.length})`));
  if (!r.never_met_pairs.length) {
    neverPanel.appendChild(el("div", { class: "muted" }, "Everyone met everyone else at some point."));
  } else {
    const max = 200;
    const list = el("div", { class: "muted", style: { lineHeight: "1.7" } });
    r.never_met_pairs.slice(0, max).forEach((p, i) => {
      const txt = `${pairLabel(p, "a")}  ↔  ${pairLabel(p, "b")}`;
      list.appendChild(el("div", {}, txt));
    });
    if (r.never_met_pairs.length > max) {
      list.appendChild(el("div", { class: "muted" }, `… and ${r.never_met_pairs.length - max} more.`));
    }
    neverPanel.appendChild(list);
  }
  reportBody.appendChild(neverPanel);

  // Download buttons.
  const dlPanel = el("div", { class: "panel" });
  dlPanel.appendChild(el("h4", { style: { marginTop: 0 } }, "Export"));
  dlPanel.appendChild(el("button", {
    onclick: () => downloadJson(r, `tracking-${s.id}-${slug(s.name)}.json`),
  }, "Download JSON"));
  dlPanel.appendChild(document.createTextNode(" "));
  dlPanel.appendChild(el("button", {
    onclick: () => downloadCsv(r, `tracking-${s.id}-${slug(s.name)}-pairs.csv`),
  }, "Download CSV (pair contact time)"));
  reportBody.appendChild(dlPanel);
}

function tile(parent, label, value) {
  const t = el("div", {
    style: {
      flex: "1 1 140px",
      minWidth: "140px",
      background: "var(--panel-2)",
      border: "1px solid var(--border)",
      borderRadius: "8px",
      padding: "12px 16px",
    },
  });
  t.appendChild(el("div", { class: "muted", style: { fontSize: "12px" } }, label));
  t.appendChild(el("div", { style: { fontSize: "26px", fontWeight: 700 } }, value));
  parent.appendChild(t);
}

function formatSeconds(secs) {
  if (secs == null) return "—";
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const m = Math.floor(secs / 60);
  const s = Math.round(secs - m * 60);
  return `${m}m ${s}s`;
}

function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""); }

function downloadJson(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  triggerDownload(blob, filename);
}

function downloadCsv(report, filename) {
  const lines = ["a_id,a_name,b_id,b_name,seconds,snapshots"];
  for (const p of report.pair_contact_seconds) {
    lines.push([p.a, q(p.a_name), p.b, q(p.b_name), p.seconds, p.snapshots].join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  triggerDownload(blob, filename);
}

function q(s) {
  if (s == null) return "";
  const needsQuote = /[",\n]/.test(s);
  const escaped = String(s).replace(/"/g, '""');
  return needsQuote ? `"${escaped}"` : escaped;
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}


// ---------- Timeline replay (ADR 0008) ----------

function buildTimelineScrubber(sessionId) {
  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h4", { style: { marginTop: 0 } }, "Timeline replay"));
  const status = el("div", { class: "muted", style: { fontSize: "12px" } }, "Loading timeline…");
  panel.appendChild(status);

  const canvas = document.createElement("canvas");
  canvas.width = 800; canvas.height = 600;
  canvas.style.cssText = "width:100%; max-width:800px; background:#0a1124; border-radius:8px; display:block;";
  panel.appendChild(canvas);

  const controls = el("div", { class: "row", style: { marginTop: "10px" } });
  const playBtn = el("button", {}, "▶ Play");
  const speedSel = document.createElement("select");
  for (const s of [0.5, 1, 2, 4, 8]) {
    const o = document.createElement("option");
    o.value = String(s); o.textContent = `${s}×`;
    if (s === 1) o.selected = true;
    speedSel.appendChild(o);
  }
  const slider = document.createElement("input");
  slider.type = "range"; slider.min = "0"; slider.max = "100"; slider.value = "0";
  slider.style.cssText = "flex:1; min-width:200px;";
  const ts = el("span", { class: "muted", style: { fontSize: "12px", minWidth: "100px" } }, "—");
  const proximityInput = document.createElement("input");
  proximityInput.type = "number"; proximityInput.min = "0.02"; proximityInput.max = "1";
  proximityInput.step = "0.01"; proximityInput.value = "0.12";
  proximityInput.style.width = "70px";
  controls.appendChild(playBtn);
  controls.appendChild(speedSel);
  controls.appendChild(slider);
  controls.appendChild(ts);
  controls.appendChild(el("span", { class: "muted", style: { fontSize: "12px" } }, "proximity:"));
  controls.appendChild(proximityInput);
  panel.appendChild(controls);

  // Fetch NDJSON
  let frames = [];
  let bucketMs = 500;
  let playing = false;
  let playTimer = null;

  fetch(`/api/tracking/sessions/${sessionId}/timeline?bucket_ms=500`)
    .then((r) => {
      bucketMs = parseInt(r.headers.get("X-Bucket-Ms") || "500", 10);
      return r.text();
    })
    .then((text) => {
      frames = text.split("\n").filter(Boolean).map((l) => {
        try { return JSON.parse(l); } catch { return null; }
      }).filter(Boolean);
      if (!frames.length) { status.textContent = "No samples in this session."; return; }
      slider.max = String(frames.length - 1);
      status.textContent = `${frames.length} frames · bucket ${bucketMs}ms`;
      renderFrame(0);
    })
    .catch((e) => { status.textContent = "Error: " + e.message; });

  function renderFrame(idx) {
    if (!frames[idx]) return;
    const f = frames[idx];
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Floor backdrop
    ctx.fillStyle = "#0a1124";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "rgba(255,255,255,0.1)";
    ctx.strokeRect(20, 20, canvas.width - 40, canvas.height - 40);

    // Detections shape: clusters.js expects {aruco_id, center_norm}.
    const detections = (f.frame || []).map((p) => ({
      aruco_id: p.id, center_norm: [p.x, p.y], person_name: p.name,
    }));
    const proximity = parseFloat(proximityInput.value) || 0.12;
    const clusters = computeClusters(detections, proximity);
    drawClusters(ctx, clusters, canvas.width, canvas.height);

    // Marker dots + names.
    for (const d of detections) {
      const cx = d.center_norm[0] * canvas.width;
      const cy = d.center_norm[1] * canvas.height;
      ctx.fillStyle = "#22d3ee";
      ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2); ctx.fill();
      const label = d.person_name || `#${d.aruco_id}`;
      ctx.font = "bold 12px sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.9)";
      ctx.fillText(label, cx + 8, cy - 6);
    }

    const seconds = (f.t_ms / 1000).toFixed(1);
    ts.textContent = `${seconds}s · ${detections.length} markers`;
  }

  slider.addEventListener("input", () => renderFrame(parseInt(slider.value, 10)));
  proximityInput.addEventListener("input", () => renderFrame(parseInt(slider.value, 10)));

  playBtn.addEventListener("click", () => {
    if (playing) {
      playing = false;
      clearInterval(playTimer);
      playBtn.textContent = "▶ Play";
      return;
    }
    if (!frames.length) return;
    playing = true;
    playBtn.textContent = "⏸ Pause";
    const speed = parseFloat(speedSel.value);
    const frameInterval = bucketMs / speed;
    playTimer = setInterval(() => {
      let i = parseInt(slider.value, 10) + 1;
      if (i >= frames.length) {
        clearInterval(playTimer);
        playing = false;
        playBtn.textContent = "▶ Play";
        return;
      }
      slider.value = String(i);
      renderFrame(i);
    }, frameInterval);
  });

  return panel;
}
