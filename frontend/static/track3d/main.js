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

const wrap        = document.getElementById("t3d-canvas-wrap");
const banner      = document.getElementById("t3d-banner");
const peopleList  = document.getElementById("t3d-people-list");
const camerasList = document.getElementById("t3d-cameras-list");
const statusEl    = document.getElementById("t3d-status");

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
    updateSpriteText(mesh.userData.sprite, witnesses > 1 ? `${witnesses}×` : "");
    lastSeen.set("m:" + m.aruco_id, now);
  }

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
  }

  for (const [id, mesh] of markerMeshes) {
    if (now - (lastSeen.get("m:" + id) || 0) > ageMs) {
      scene.remove(mesh); markerMeshes.delete(id);
      mesh.children.forEach((c) => { c.geometry?.dispose?.(); c.material?.dispose?.(); });
    }
  }
  for (const [key, mesh] of personMeshes) {
    if (now - (lastSeen.get(key) || 0) > ageMs) {
      scene.remove(mesh); personMeshes.delete(key);
    }
  }

  renderPeopleList(world.people || []);
  renderCamerasList(world.cameras || []);
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
    const card = document.createElement("div");
    card.className = "person-card";
    card.innerHTML = `
      <div class="nm">cam ${c.camera_id} — ${c.name}</div>
      <div class="muted">${c.marker_count} markers · ${c.fps.toFixed(1)} fps · coverage ${c.coverage_pct}%</div>
      <div style="font-size:11px;">
        <span style="color:${ageColor};">●</span>
        last sample ${c.age_ms} ms ago
      </div>
    `;
    camerasList.appendChild(card);
  }
}

// ---------- WS observer plumbing ----------------------------------------

function openSceneWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/scene`);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.ok && msg.scene_world) updateScene(msg.scene_world);
    } catch (_) {}
  };
  ws.onclose = () => {
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
