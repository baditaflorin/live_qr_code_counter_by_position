// /track3d — observer for the multi-camera fused world scene.
//
// Pipeline:
//
//   capture clients ── frames ──▶ /ws/detect ──▶ scene_state aggregator
//                                                       │
//                            /ws/scene  ◀── 10 Hz ──────┘
//                                ▼
//                          Three.js scene
//
// This page no longer owns a camera — capture happens on the Live page (or
// any other /ws/detect publisher).  /track3d just subscribes to the fused
// world state at 10 Hz and renders it.  Multiple cameras observing the same
// floor are quality-weighted and combined per-marker before reaching us.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { api } from "/static/common.js";

// ---------- DOM refs ------------------------------------------------------

const wrap          = document.getElementById("t3d-canvas-wrap");
const banner        = document.getElementById("t3d-banner");
const peopleList    = document.getElementById("t3d-people-list");
const camerasList   = document.getElementById("t3d-cameras-list");
const encountersList = document.getElementById("t3d-encounters-list");
const statusEl      = document.getElementById("t3d-status");
const optTrails     = document.getElementById("opt-trails");
const optHeatmap    = document.getElementById("opt-heatmap");
const optClear      = document.getElementById("opt-clear-history");
const optStatus     = document.getElementById("opt-status");

// ---------- Three.js scene -----------------------------------------------

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x060912);

const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 200);
camera.position.set(6, -6, 6);
camera.up.set(0, 0, 1); // world Z is up

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
wrap.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(2.5, 2.0, 0);

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(4, -6, 8);
scene.add(dirLight);

scene.add(new THREE.AxesHelper(0.6));

let floorMesh = null;
let floorGrid = null;
const cameraMarkers = new Map();   // camera_id -> Group

const markerMeshes = new Map();    // aruco_id -> Group
const personMeshes = new Map();    // person_id -> Group
const personTrails = new Map();    // person_id -> { line, positions[], colors }
const TRAIL_MAX_POINTS = 300;      // ~30 s at 10 Hz; past that, drop oldest

// Heatmap accumulator: 20 cm grid cells, dwell time per cell.
const HEAT_CELL_M = 0.2;
const heatGrid = new Map();        // "x,y" -> seconds dwelt
let heatLastUpdateTs = 0;
let heatMesh = null;

function ensureFloor(w, h) {
  if (floorMesh && floorMesh.userData.w === w && floorMesh.userData.h === h) return;
  if (floorMesh) { scene.remove(floorMesh); floorMesh.geometry.dispose(); floorMesh.material.dispose(); }
  if (floorGrid) { scene.remove(floorGrid); floorGrid.geometry.dispose(); floorGrid.material.dispose(); }

  const geom = new THREE.PlaneGeometry(w, h);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x1c2540, roughness: 0.95, side: THREE.DoubleSide,
  });
  floorMesh = new THREE.Mesh(geom, mat);
  floorMesh.position.set(w / 2, h / 2, -0.005);
  floorMesh.userData = { w, h };
  scene.add(floorMesh);

  const lineGeom = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, 0), new THREE.Vector3(w, 0, 0),
    new THREE.Vector3(w, h, 0), new THREE.Vector3(0, h, 0),
    new THREE.Vector3(0, 0, 0),
  ]);
  const lineMat = new THREE.LineBasicMaterial({ color: 0x7c3aed, linewidth: 2 });
  floorGrid = new THREE.Line(lineGeom, lineMat);
  scene.add(floorGrid);

  controls.target.set(w / 2, h / 2, 0);
}

function reproErrorColor(err) {
  if (err <= 0.6) return 0x22c55e;
  if (err <= 1.5) return 0xf59e0b;
  return 0xef4444;
}

function makeMarkerMesh(initialColor) {
  // Tiny flat square + yaw arrow on the marker's local +X axis.  The whole
  // group is rotated by the full ZYX euler from scene_world so pitch/roll
  // show up too — useful when a marker is on a hat/wrist that tilts.
  const grp = new THREE.Group();
  const planeGeom = new THREE.PlaneGeometry(0.18, 0.18);
  const planeMat = new THREE.MeshStandardMaterial({
    color: initialColor, side: THREE.DoubleSide, transparent: true, opacity: 0.9,
  });
  const plane = new THREE.Mesh(planeGeom, planeMat);
  grp.add(plane);

  // Tri-axis gizmo so flips/rolls are obvious — small enough not to clutter.
  const arrowX = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0.005), 0.22, 0xff4d4d, 0.07, 0.035);
  const arrowY = new THREE.ArrowHelper(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0.005), 0.16, 0x4dff7a, 0.06, 0.03);
  const arrowZ = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0.005), 0.13, 0x4d9bff, 0.05, 0.025);
  grp.add(arrowX); grp.add(arrowY); grp.add(arrowZ);

  // Witnesses badge — number of cameras that see this marker right now.
  const sprite = makeTextSprite("");
  sprite.position.set(0, 0, 0.18);
  sprite.scale.set(0.35, 0.1, 1);
  grp.add(sprite);

  grp.userData = { plane, arrowX, sprite };
  return grp;
}

function makePersonMesh() {
  const grp = new THREE.Group();
  const pillarGeom = new THREE.CylinderGeometry(0.12, 0.18, 1.6, 16, 1, false);
  const pillarMat = new THREE.MeshStandardMaterial({
    color: 0x60a5fa, roughness: 0.4, metalness: 0.1, transparent: true, opacity: 0.85,
  });
  const pillar = new THREE.Mesh(pillarGeom, pillarMat);
  pillar.rotation.x = Math.PI / 2;
  pillar.position.z = 0.8;
  grp.add(pillar);

  const arrow = new THREE.ArrowHelper(
    new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 1.65),
    0.5, 0x60a5fa, 0.16, 0.08,
  );
  grp.add(arrow);

  const sprite = makeTextSprite("");
  sprite.position.set(0, 0, 1.95);
  grp.add(sprite);

  grp.userData = { pillar, arrow, sprite };
  return grp;
}

function makeTextSprite(text) {
  const canvas = document.createElement("canvas");
  canvas.width = 256; canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "rgba(0,0,0,0)"; ctx.fillRect(0, 0, 256, 64);
  ctx.font = "bold 32px system-ui, sans-serif";
  ctx.fillStyle = "#fff";
  ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.lineWidth = 4;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.strokeText(text, 128, 32);
  ctx.fillText(text, 128, 32);
  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(1.0, 0.25, 1);
  sprite.userData = { text, canvas, ctx, tex };
  return sprite;
}

function updateSpriteText(sprite, text) {
  if (sprite.userData.text === text) return;
  sprite.userData.text = text;
  const { canvas, ctx, tex } = sprite.userData;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = "bold 32px system-ui, sans-serif";
  ctx.fillStyle = "#fff";
  ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.lineWidth = 4;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.strokeText(text, 128, 32);
  ctx.fillText(text, 128, 32);
  tex.needsUpdate = true;
}

function ensureCameraMarker(cameraId, pos) {
  if (!pos) {
    const m = cameraMarkers.get(cameraId);
    if (m) { scene.remove(m); cameraMarkers.delete(cameraId); }
    return;
  }
  let m = cameraMarkers.get(cameraId);
  if (!m) {
    m = new THREE.Group();
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(0.18, 0.4, 16),
      new THREE.MeshStandardMaterial({ color: 0x0ea5e9, emissive: 0x0c4a6e }),
    );
    cone.rotation.x = Math.PI / 2;
    m.add(cone);
    m.add(new THREE.Mesh(
      new THREE.SphereGeometry(0.06, 16, 12),
      new THREE.MeshStandardMaterial({ color: 0x0ea5e9 }),
    ));
    const sprite = makeTextSprite(`cam ${cameraId}`);
    sprite.position.set(0, 0, 0.4);
    sprite.scale.set(0.6, 0.18, 1);
    m.add(sprite);
    scene.add(m);
    cameraMarkers.set(cameraId, m);
  }
  m.position.set(pos[0], pos[1], pos[2]);
}

function pruneCameraMarkers(activeIds) {
  for (const id of cameraMarkers.keys()) {
    if (!activeIds.has(id)) {
      scene.remove(cameraMarkers.get(id));
      cameraMarkers.delete(id);
    }
  }
}

// ---------- trails -------------------------------------------------------

function ensureTrail(personId) {
  let t = personTrails.get(personId);
  if (t) return t;
  const positions = new Float32Array(TRAIL_MAX_POINTS * 3);
  const colors    = new Float32Array(TRAIL_MAX_POINTS * 3);
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geom.setAttribute("color",    new THREE.BufferAttribute(colors, 3));
  geom.setDrawRange(0, 0);
  const mat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true });
  const line = new THREE.Line(geom, mat);
  scene.add(line);
  t = { line, positions, colors, count: 0 };
  personTrails.set(personId, t);
  return t;
}

function pushTrailPoint(personId, x, y) {
  const t = ensureTrail(personId);
  // Shift existing points back by one slot, drop the oldest.
  if (t.count >= TRAIL_MAX_POINTS) {
    t.positions.copyWithin(0, 3);
    t.colors.copyWithin(0, 3);
    t.count = TRAIL_MAX_POINTS - 1;
  }
  const i = t.count;
  t.positions[i * 3 + 0] = x;
  t.positions[i * 3 + 1] = y;
  t.positions[i * 3 + 2] = 0.02;
  t.count++;
  // Repaint colors: oldest = transparent blue, newest = bright cyan.
  for (let k = 0; k < t.count; k++) {
    const a = (k + 1) / t.count;
    t.colors[k * 3 + 0] = 0.4 * a;
    t.colors[k * 3 + 1] = 0.9 * a;
    t.colors[k * 3 + 2] = 1.0 * a;
  }
  t.line.geometry.attributes.position.needsUpdate = true;
  t.line.geometry.attributes.color.needsUpdate = true;
  t.line.geometry.setDrawRange(0, t.count);
  t.line.visible = optTrails.checked;
}

function pruneTrail(personId) {
  const t = personTrails.get(personId);
  if (!t) return;
  scene.remove(t.line);
  t.line.geometry.dispose();
  t.line.material.dispose();
  personTrails.delete(personId);
}

function clearAllTrails() {
  for (const id of [...personTrails.keys()]) pruneTrail(id);
}

// ---------- heatmap ------------------------------------------------------

function bumpHeat(x, y, dt_s) {
  const gx = Math.round(x / HEAT_CELL_M);
  const gy = Math.round(y / HEAT_CELL_M);
  const key = gx + "," + gy;
  heatGrid.set(key, (heatGrid.get(key) || 0) + dt_s);
}

function rebuildHeatMesh() {
  if (heatMesh) {
    scene.remove(heatMesh);
    heatMesh.geometry.dispose();
    heatMesh.material.dispose();
    heatMesh = null;
  }
  if (heatGrid.size === 0) return;
  const max = Math.max(...heatGrid.values());
  if (max <= 0) return;
  const dummy = new THREE.Object3D();
  const geom = new THREE.PlaneGeometry(HEAT_CELL_M * 0.95, HEAT_CELL_M * 0.95);
  const mat = new THREE.MeshBasicMaterial({
    transparent: true, opacity: 0.55, depthWrite: false, side: THREE.DoubleSide,
  });
  const inst = new THREE.InstancedMesh(geom, mat, heatGrid.size);
  inst.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(heatGrid.size * 3), 3);
  let i = 0;
  for (const [key, dwell] of heatGrid.entries()) {
    const [gx, gy] = key.split(",").map(Number);
    dummy.position.set(gx * HEAT_CELL_M, gy * HEAT_CELL_M, 0.001);
    dummy.updateMatrix();
    inst.setMatrixAt(i, dummy.matrix);
    const intensity = Math.min(1, dwell / max);
    // Cool→warm gradient: blue (cool) → yellow (medium) → red (hot)
    const r = intensity;
    const g = intensity < 0.5 ? intensity * 2 : (1 - intensity) * 2;
    const b = 1 - intensity;
    inst.instanceColor.setXYZ(i, r, g, b);
    i++;
  }
  inst.instanceMatrix.needsUpdate = true;
  inst.instanceColor.needsUpdate = true;
  inst.visible = optHeatmap.checked;
  scene.add(inst);
  heatMesh = inst;
}

function clearHeat() {
  heatGrid.clear();
  if (heatMesh) {
    scene.remove(heatMesh);
    heatMesh.geometry.dispose();
    heatMesh.material.dispose();
    heatMesh = null;
  }
}

// ---------- update from a fused scene_world payload ---------------------

const ageMs = 1500;
const lastSeen = new Map();

// Three.js Euler order for our convention: scene_world reports yaw/pitch/roll
// as intrinsic Z-Y-X, which corresponds to Three.js order "ZYX".
function applyEulerZYX(obj3d, yaw_deg, pitch_deg, roll_deg) {
  const e = new THREE.Euler(
    (roll_deg  * Math.PI) / 180,
    (pitch_deg * Math.PI) / 180,
    (yaw_deg   * Math.PI) / 180,
    "ZYX",
  );
  obj3d.setRotationFromEuler(e);
}

function updateScene(world) {
  if (!world || !world.world_frame) return;
  ensureFloor(world.world_frame.floor_w_m, world.world_frame.floor_h_m);

  const activeCameraIds = new Set();
  for (const c of world.cameras || []) {
    activeCameraIds.add(c.camera_id);
    ensureCameraMarker(c.camera_id, c.camera_position_world_m);
  }
  pruneCameraMarkers(activeCameraIds);

  const now = performance.now();

  for (const m of world.markers || []) {
    let mesh = markerMeshes.get(m.aruco_id);
    if (!mesh) {
      mesh = makeMarkerMesh(0x22c55e);
      scene.add(mesh);
      markerMeshes.set(m.aruco_id, mesh);
    }
    const [x, y, z] = m.world_xyz_m;
    mesh.position.set(x, y, Math.max(0.005, z));
    applyEulerZYX(mesh, m.yaw_deg, m.pitch_deg, m.roll_deg);
    const color = reproErrorColor(m.reproj_error_px);
    mesh.userData.plane.material.color.setHex(color);
    const witnesses = (m.witness_camera_ids || []).length;
    let label = "";
    if (witnesses > 1) {
      // "2× ⚠ 12cm" if disagreement is loose, just "2×" otherwise.
      if (m.disagreement_cm != null && m.disagreement_cm > 5) {
        label = `${witnesses}× ⚠ ${m.disagreement_cm.toFixed(0)}cm`;
      } else if (m.disagreement_cm != null) {
        label = `${witnesses}× ${m.disagreement_cm.toFixed(0)}cm`;
      } else {
        label = `${witnesses}×`;
      }
    }
    updateSpriteText(mesh.userData.sprite, label);
    lastSeen.set("m:" + m.aruco_id, now);
  }

  // Heatmap accumulator: time since last update (for dwell weighting).
  const wallNow = world.ts || (Date.now() / 1000);
  const dt_s = heatLastUpdateTs > 0 ? Math.min(0.5, wallNow - heatLastUpdateTs) : 0;
  heatLastUpdateTs = wallNow;

  for (const p of world.people || []) {
    if (p.person_id == null) continue;
    const key = `p:${p.person_id}`;
    let mesh = personMeshes.get(key);
    if (!mesh) {
      mesh = makePersonMesh();
      scene.add(mesh);
      personMeshes.set(key, mesh);
    }
    const [x, y] = p.body_xyz_m;
    mesh.position.set(x, y, 0);
    mesh.rotation.set(0, 0, (p.body_yaw_deg * Math.PI) / 180);
    const label = p.person_name || `#${p.marker_ids.join("+")}`;
    updateSpriteText(mesh.userData.sprite, label);
    lastSeen.set(key, now);

    pushTrailPoint(p.person_id, x, y);
    if (dt_s > 0) bumpHeat(x, y, dt_s);
  }

  // Heatmap mesh is expensive to rebuild — refresh at 1 Hz max.
  if (optHeatmap.checked && (!heatMesh || performance.now() - (heatMesh.userData?.builtAt || 0) > 1000)) {
    rebuildHeatMesh();
    if (heatMesh) heatMesh.userData.builtAt = performance.now();
  }
  if (heatMesh) heatMesh.visible = optHeatmap.checked;

  for (const [id, mesh] of markerMeshes) {
    if (now - (lastSeen.get("m:" + id) || 0) > ageMs) {
      scene.remove(mesh); markerMeshes.delete(id);
      mesh.children.forEach((c) => { c.geometry?.dispose?.(); c.material?.dispose?.(); });
    }
  }
  for (const [key, mesh] of personMeshes) {
    if (now - (lastSeen.get(key) || 0) > ageMs) {
      scene.remove(mesh); personMeshes.delete(key);
      const pid = parseInt(key.slice(2), 10);
      pruneTrail(pid);
    }
  }

  renderPeopleList(world.people || []);
  renderCamerasList(world.cameras || []);
  renderEncounters(world.encounters);
  if (optStatus) {
    optStatus.textContent =
      `${heatGrid.size} cells · ${[...personTrails.values()].reduce((a, t) => a + t.count, 0)} trail pts`;
  }
}

function renderEncounters(enc) {
  if (!enc || (!enc.live?.length)) {
    encountersList.textContent = "No-one is close to anyone yet.";
    encountersList.className = "muted";
    return;
  }
  encountersList.className = "";
  encountersList.innerHTML = "";
  for (const e of enc.live) {
    const card = document.createElement("div");
    card.className = "person-card";
    const aName = e.a_name || `#${e.a_id}`;
    const bName = e.b_name || `#${e.b_id}`;
    const m = Math.floor(e.duration_s / 60);
    const s = Math.floor(e.duration_s % 60);
    const dur = m > 0 ? `${m}m${String(s).padStart(2, "0")}s` : `${s}s`;
    card.innerHTML = `
      <div class="nm">${aName} ↔ ${bName}</div>
      <div class="muted">together for ${dur}</div>
    `;
    encountersList.appendChild(card);
  }
}

function renderPeopleList(people) {
  const named = people.filter((p) => p.person_id != null);
  if (!named.length) {
    peopleList.textContent = "Nothing detected.";
    peopleList.className = "muted";
    return;
  }
  peopleList.className = "";
  peopleList.innerHTML = "";
  for (const p of named) {
    const card = document.createElement("div");
    card.className = "person-card";
    const [x, y] = p.body_xyz_m;
    card.innerHTML = `
      <div class="nm">${p.person_name || "(unassigned)"}</div>
      <div class="muted">markers: ${p.marker_ids.join(", ")} · placements: ${p.placements_seen.join("+")}</div>
      <div>pos: (${x.toFixed(2)}, ${y.toFixed(2)}) m · yaw ${p.body_yaw_deg.toFixed(1)}°</div>
      <div class="muted">conf ${p.confidence.toFixed(2)}</div>
    `;
    peopleList.appendChild(card);
  }
}

function renderCamerasList(cams) {
  if (!cams.length) {
    camerasList.innerHTML = `<div class="muted">No cameras publishing. Open <a href="/" target="_blank">/</a> on a device with a webcam, then press <strong>Start</strong>.</div>`;
    statusEl.textContent = "no publishers";
    statusEl.style.background = "#374151";
    return;
  }
  statusEl.textContent = `${cams.length} cam · ${cams.reduce((a, c) => a + c.marker_count, 0)} markers`;
  statusEl.style.background = "#16a34a";
  camerasList.innerHTML = "";
  for (const c of cams) {
    const ageColor = c.age_ms < 500 ? "#22c55e" : c.age_ms < 1500 ? "#f59e0b" : "#ef4444";
    const errColor = c.mean_reproj_error_px == null ? "#9ca3af"
      : c.mean_reproj_error_px <= 0.6 ? "#22c55e"
      : c.mean_reproj_error_px <= 1.5 ? "#f59e0b" : "#ef4444";
    const card = document.createElement("div");
    card.className = "person-card";
    const errBadge = c.mean_reproj_error_px != null
      ? `<span style="color:${errColor};">● reproj ${c.mean_reproj_error_px.toFixed(2)} px</span>`
      : `<span class="muted">no markers</span>`;
    card.innerHTML = `
      <div class="nm">cam ${c.camera_id} — ${c.name}</div>
      <div class="muted">${c.marker_count} markers · ${c.fps.toFixed(1)} fps · coverage ${c.coverage_pct}%</div>
      <div style="font-size:11px;">
        <span style="color:${ageColor};">●</span> last sample ${c.age_ms} ms ago · ${errBadge}
      </div>
    `;
    camerasList.appendChild(card);
  }
}

// ---------- WS observer plumbing ----------------------------------------

// ?replay=ID&speed=N flips the viewer into playback mode (uses /ws/replay/ID).
const urlParams = new URLSearchParams(location.search);
const replayId = urlParams.get("replay");
const replaySpeed = urlParams.get("speed") || "1";

function openSceneWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const path = replayId
    ? `/ws/replay/${encodeURIComponent(replayId)}?speed=${encodeURIComponent(replaySpeed)}`
    : `/ws/scene`;
  const ws = new WebSocket(`${proto}://${location.host}${path}`);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.playback_done) {
        statusEl.textContent = "playback done";
        statusEl.style.background = "#7c3aed";
        return;
      }
      if (msg.ok && msg.scene_world) updateScene(msg.scene_world);
    } catch (_) {}
  };
  ws.onclose = () => {
    if (replayId) return;  // don't auto-reconnect to a finished playback
    statusEl.textContent = "reconnecting…";
    statusEl.style.background = "#374151";
    setTimeout(openSceneWS, 1500);
  };
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
  return ws;
}

const setupGuide = document.getElementById("t3d-setup-guide");
const setupStep1 = document.getElementById("setup-step-1");
const setupStep2 = document.getElementById("setup-step-2");

async function refreshCalibrationBanner() {
  try {
    const cams = await api("/api/cameras");
    if (!cams.length) {
      banner.innerHTML = `<a href="/admin#cameras">Open Admin → Cameras</a> to set up a camera.`;
      return;
    }
    const allIntr = cams.every((c) => c.intrinsic_calibrated);
    const allExt  = cams.every((c) => c.extrinsic_calibrated);
    if (allIntr && setupStep1) {
      setupStep1.style.opacity = "0.5";
      setupStep1.innerHTML = `<strong>Intrinsic calibration</strong> ✓`;
    }
    if (allExt && setupStep2) {
      setupStep2.style.opacity = "0.5";
      setupStep2.innerHTML = `<strong>Extrinsic calibration</strong> ✓`;
    }
    if (allIntr && allExt) {
      if (setupGuide) setupGuide.hidden = true;
      banner.textContent = "";
    } else {
      if (setupGuide) setupGuide.hidden = false;
      banner.innerHTML = `Some cameras need calibration — open <a href="/admin#cameras">Admin → Cameras</a>.`;
    }
  } catch (e) {
    banner.textContent = "Error: " + e.message;
  }
}

// ---------- size + animate ----------------------------------------------

function onResize() {
  const r = wrap.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / r.height;
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", onResize);
onResize();

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

// ---------- boot --------------------------------------------------------

refreshCalibrationBanner();
setInterval(refreshCalibrationBanner, 5000);
openSceneWS();

// ---------- recordings ----------------------------------------------------

const recNameEl   = document.getElementById("rec-name");
const recStartBtn = document.getElementById("rec-start");
const recStopBtn  = document.getElementById("rec-stop");
const recStatusEl = document.getElementById("rec-status");
const recListEl   = document.getElementById("rec-list");

async function refreshRecordings() {
  try {
    const data = await api("/api/recordings");
    if (data.active) {
      const a = data.active;
      recStartBtn.disabled = true;
      recStopBtn.disabled = false;
      recStatusEl.innerHTML = `🔴 <strong>${a.name}</strong> · ${a.frames_written} frames · ${(a.bytes_written / 1024).toFixed(1)} KB · ${a.elapsed_s}s`;
    } else {
      recStartBtn.disabled = false;
      recStopBtn.disabled = true;
      recStatusEl.textContent = "";
    }
    if (!data.recordings.length) {
      recListEl.textContent = "No recordings yet.";
      recListEl.className = "muted";
      return;
    }
    recListEl.className = "";
    recListEl.innerHTML = "";
    for (const r of data.recordings) {
      const row = document.createElement("div");
      row.className = "person-card";
      const dur = r.frame_count ? `${r.frame_count} frames` : "(empty)";
      const sizeKB = (r.file_size_bytes / 1024).toFixed(1);
      row.innerHTML = `
        <div class="nm">${r.name}${r.is_active ? " 🔴" : ""}</div>
        <div class="muted" style="font-size:11px;">${dur} · ${sizeKB} KB · ${new Date(r.started_at).toLocaleString()}</div>
        <div style="margin-top:4px;">
          <a href="/track3d?replay=${r.id}" target="_blank"><button>▶ Play</button></a>
          <a href="/track3d?replay=${r.id}&speed=4" target="_blank"><button>4× </button></a>
          <button data-del="${r.id}" class="danger">Delete</button>
        </div>
      `;
      row.querySelector("[data-del]").addEventListener("click", async (ev) => {
        const id = ev.target.dataset.del;
        if (!confirm("Delete this recording? File and DB row are removed.")) return;
        await api(`/api/recordings/${id}`, { method: "DELETE" });
        await refreshRecordings();
      });
      recListEl.appendChild(row);
    }
  } catch (e) {
    recListEl.textContent = "Error: " + e.message;
  }
}

recStartBtn.addEventListener("click", async () => {
  const name = (recNameEl.value || "").trim() || `rec-${new Date().toISOString().slice(0, 19)}`;
  try {
    await api("/api/recordings/start", { method: "POST", body: { name } });
    recNameEl.value = "";
    await refreshRecordings();
  } catch (e) {
    alert("Start failed: " + e.message);
  }
});
recStopBtn.addEventListener("click", async () => {
  try {
    await api("/api/recordings/stop", { method: "POST", body: {} });
    await refreshRecordings();
  } catch (e) {
    alert("Stop failed: " + e.message);
  }
});

if (replayId) {
  // Replay mode: hide the recording controls + show a banner.
  document.querySelector("#rec-start").style.display = "none";
  document.querySelector("#rec-stop").style.display = "none";
  document.querySelector("#rec-name").style.display = "none";
  banner.innerHTML = `▶ Replaying recording <strong>#${replayId}</strong> at ${replaySpeed}× — <a href="/track3d">back to live</a>.`;
}

refreshRecordings();
setInterval(refreshRecordings, 3000);

optTrails.addEventListener("change", () => {
  for (const t of personTrails.values()) t.line.visible = optTrails.checked;
});
optHeatmap.addEventListener("change", () => {
  if (heatMesh) heatMesh.visible = optHeatmap.checked;
  if (optHeatmap.checked && !heatMesh) rebuildHeatMesh();
});
optClear.addEventListener("click", () => {
  clearAllTrails();
  clearHeat();
});
