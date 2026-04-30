// Live cluster computation + canvas overlay for the tracking page.
//
// Server-side `tracking.compute_report` already does this for the recorded
// samples; the frontend duplicates the logic in JS so the operator sees the
// clusters update in real time as people move, without round-tripping each
// frame through a report endpoint.

const CLUSTER_PALETTE = [
  "#22d3ee", "#a855f7", "#f59e0b", "#ec4899",
  "#14b8a6", "#6366f1", "#10b981", "#f97316",
];

/**
 * Group detections into clusters by image-space proximity (union-find).
 * `thresholdNorm` is in normalized [0..1] image coordinates.
 *
 * Returns clusters of size >= 2 only (a single marker on its own isn't a cluster).
 */
export function computeClusters(detections, thresholdNorm) {
  const t2 = thresholdNorm * thresholdNorm;
  const parent = new Map();
  const find = (x) => {
    while (parent.get(x) !== x) {
      parent.set(x, parent.get(parent.get(x)));
      x = parent.get(x);
    }
    return x;
  };
  for (const d of detections) parent.set(d.aruco_id, d.aruco_id);
  for (let i = 0; i < detections.length; i++) {
    const a = detections[i];
    for (let j = i + 1; j < detections.length; j++) {
      const b = detections[j];
      const dx = a.center_norm[0] - b.center_norm[0];
      const dy = a.center_norm[1] - b.center_norm[1];
      if (dx * dx + dy * dy <= t2) {
        const ra = find(a.aruco_id), rb = find(b.aruco_id);
        if (ra !== rb) parent.set(ra, rb);
      }
    }
  }
  const groups = new Map();
  for (const d of detections) {
    const r = find(d.aruco_id);
    if (!groups.has(r)) groups.set(r, []);
    groups.get(r).push(d);
  }
  return [...groups.values()].filter((g) => g.length >= 2);
}

/** Andrew's monotone-chain convex hull. Input + output: array of [x,y]. */
function convexHull(points) {
  if (points.length < 3) return points.slice();
  const pts = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  upper.pop(); lower.pop();
  return lower.concat(upper);
}

/**
 * Draw colored hulls around each cluster on the overlay canvas.
 * `detections` should also be drawn separately (this module only paints
 * the cluster outlines so it composes with the live page's existing overlay).
 */
export function drawClusters(ctx, clusters, w, h) {
  clusters.forEach((cluster, i) => {
    const color = CLUSTER_PALETTE[i % CLUSTER_PALETTE.length];
    const pts = cluster.map((d) => [d.center_norm[0] * w, d.center_norm[1] * h]);
    let hull = convexHull(pts);
    // For 2-point "hulls" the convex hull is a degenerate line — pad it
    // slightly into a thin lens so it's visible.
    if (hull.length < 3) {
      hull = expandLine(pts, 18);
    }
    ctx.beginPath();
    hull.forEach(([x, y], k) => {
      if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = color + "40";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.stroke();

    const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
    const cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
    ctx.font = "bold 18px sans-serif";
    ctx.lineWidth = 4;
    ctx.strokeStyle = "rgba(0,0,0,0.85)";
    ctx.fillStyle = "#ffffff";
    const label = `${cluster.length} together`;
    const m = ctx.measureText(label);
    ctx.strokeText(label, cx - m.width / 2, cy - 22);
    ctx.fillText(label, cx - m.width / 2, cy - 22);
  });
}

function expandLine([a, b], pad) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  // Perpendicular unit
  const nx = -dy / len, ny = dx / len;
  return [
    [a[0] + nx * pad, a[1] + ny * pad],
    [b[0] + nx * pad, b[1] + ny * pad],
    [b[0] - nx * pad, b[1] - ny * pad],
    [a[0] - nx * pad, a[1] - ny * pad],
  ];
}
