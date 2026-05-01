// /track3d — live 3D world-frame view of the scene_world payload (ADR 0050).
//
// Pipeline:
//
//   webcam ── JPEG ──▶ WS /ws/detect ──▶ scene_world ──▶ Three.js scene
//
// The backend lifts each detected marker into world coordinates using the
// camera's intrinsic (ADR 0048) + extrinsic (ADR 0012); we just render
// what comes back. If the camera isn't fully calibrated, scene_world is
// null and we display a friendly banner pointing to /admin to finish setup.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CameraStream } from "/static/lib/camera.js";
import { api } from "/static/common.js";

// ---------- DOM refs ------------------------------------------------------

const wrap   = document.getElementById("t3d-canvas-wrap");
const banner = document.getElementById("t3d-banner");
const peopleList = document.getElementById("t3d-people-list");
const camStatus  = document.getElementById("cam-camera-status");
const fpsEl  = document.getElementById("t3d-fps-actual");
const statusEl = document.getElementById("t3d-status");

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

// World axis helper (X=red, Y=green, Z=blue) at origin (TL corner).
const axes = new THREE.AxesHelper(0.6);
scene.add(axes);

// Floor + grid get rebuilt whenever we learn the floor rectangle dimensions.
let floorMesh = null;
let floorGrid = null;
let cameraMarker = null;

const markerMeshes = new Map();   // aruco_id -> Group
const personMeshes = new Map();   // person_id -> Group

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

  // Rectangle outline in violet so the four-corner mapping is unambiguous.
  const lineGeom = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(w, 0, 0),
    new THREE.Vector3(w, h, 0),
    new THREE.Vector3(0, h, 0),
    new THREE.Vector3(0, 0, 0),
  ]);
  const lineMat = new THREE.LineBasicMaterial({ color: 0x7c3aed, linewidth: 2 });
  floorGrid = new THREE.Line(lineGeom, lineMat);
  scene.add(floorGrid);

  controls.target.set(w / 2, h / 2, 0);
  if (camera.position.length() < 1) camera.position.set(w + 1, -1, 4);
}

function reproErrorColor(err) {
  if (err <= 0.6) return 0x22c55e;
  if (err <= 1.5) return 0xf59e0b;
  return 0xef4444;
}

function makeMarkerMesh(initialColor) {
  // A tiny flat square with a yaw arrow on top — readable from above.
  const grp = new THREE.Group();
  const planeGeom = new THREE.PlaneGeometry(0.18, 0.18);
  const planeMat = new THREE.MeshStandardMaterial({
    color: initialColor, side: THREE.DoubleSide, transparent: true, opacity: 0.9,
  });
  const plane = new THREE.Mesh(planeGeom, planeMat);
  grp.add(plane);

  const arrow = new THREE.ArrowHelper(
    new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0.005),
    0.25, initialColor, 0.08, 0.04,
  );
  grp.add(arrow);

  grp.userData = { plane, arrow };
  return grp;
}

function makePersonMesh() {
  // A short pillar (~chest height) so people stand out from raw markers.
  const grp = new THREE.Group();
  const pillarGeom = new THREE.CylinderGeometry(0.12, 0.18, 1.6, 16, 1, false);
  const pillarMat = new THREE.MeshStandardMaterial({
    color: 0x60a5fa, roughness: 0.4, metalness: 0.1, transparent: true, opacity: 0.85,
  });
  const pillar = new THREE.Mesh(pillarGeom, pillarMat);
  pillar.rotation.x = Math.PI / 2; // cylinder default is along Y; we want along Z (up)
  pillar.position.z = 0.8;
  grp.add(pillar);

  const arrow = new THREE.ArrowHelper(
    new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 1.65),
    0.5, 0x60a5fa, 0.16, 0.08,
  );
  grp.add(arrow);

  // Sprite label
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
  ctx.fillStyle = "rgba(0,0,0,0)"; ctx.fillRect(0,0,256,64);
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

function ensureCameraMarker(pos) {
  if (!pos) {
    if (cameraMarker) { scene.remove(cameraMarker); cameraMarker = null; }
    return;
  }
  if (!cameraMarker) {
    cameraMarker = new THREE.Group();
    const geom = new THREE.ConeGeometry(0.18, 0.4, 16);
    const mat = new THREE.MeshStandardMaterial({ color: 0x0ea5e9, emissive: 0x0c4a6e });
    const cone = new THREE.Mesh(geom, mat);
    cone.rotation.x = Math.PI / 2; // tip pointing along +Z (down toward floor)
    cameraMarker.add(cone);
    cameraMarker.add(new THREE.Mesh(
      new THREE.SphereGeometry(0.06, 16, 12),
      new THREE.MeshStandardMaterial({ color: 0x0ea5e9 }),
    ));
    scene.add(cameraMarker);
  }
  cameraMarker.position.set(pos[0], pos[1], pos[2]);
}

// ---------- update from a scene_world payload ----------------------------

const ageMs = 1500;  // markers/people fade out this long after last seen
const lastSeen = new Map();  // key -> timestamp

function updateScene(world) {
  if (!world) return;
  ensureFloor(world.world_frame.floor_w_m, world.world_frame.floor_h_m);
  ensureCameraMarker(world.world_frame.camera_position_world_m);

  const now = performance.now();

  const visibleMarkerIds = new Set();
  for (const m of world.markers || []) {
    visibleMarkerIds.add(m.aruco_id);
    let mesh = markerMeshes.get(m.aruco_id);
    if (!mesh) {
      mesh = makeMarkerMesh(0x22c55e);
      scene.add(mesh);
      markerMeshes.set(m.aruco_id, mesh);
    }
    const [x, y, z] = m.world_xyz_m;
    mesh.position.set(x, y, Math.max(0.005, z));
    // Yaw rotation around world Z so the arrow points along the marker's
    // facing direction (in the floor plane).
    mesh.rotation.set(0, 0, (m.yaw_deg * Math.PI) / 180);
    const color = reproErrorColor(m.reproj_error_px);
    mesh.userData.plane.material.color.setHex(color);
    mesh.userData.arrow.setColor(new THREE.Color(color));
    lastSeen.set("m:" + m.aruco_id, now);
  }

  const visiblePersonKeys = new Set();
  for (const p of world.people || []) {
    const key = p.person_id != null ? `p:${p.person_id}` : `m:${p.marker_ids[0]}`;
    if (p.person_id == null) continue;  // unassigned markers are already drawn raw
    visiblePersonKeys.add(key);
    let mesh = personMeshes.get(key);
    if (!mesh) {
      mesh = makePersonMesh();
      scene.add(mesh);
      personMeshes.set(key, mesh);
    }
    const [x, y, _z] = p.body_xyz_m;
    mesh.position.set(x, y, 0);
    mesh.rotation.set(0, 0, (p.body_yaw_deg * Math.PI) / 180);
    const label = p.person_name || `#${p.marker_ids.join("+")}`;
    updateSpriteText(mesh.userData.sprite, label);
    lastSeen.set(key, now);
  }

  // Cull any marker / person mesh that hasn't been refreshed in `ageMs`.
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
}

function renderPeopleList(people) {
  if (!people.length) {
    peopleList.textContent = "Nothing detected.";
    peopleList.className = "muted";
    return;
  }
  peopleList.className = "";
  peopleList.innerHTML = "";
  for (const p of people) {
    const card = document.createElement("div");
    card.className = "person-card";
    const [x, y, z] = p.body_xyz_m;
    card.innerHTML = `
      <div class="nm">${p.person_name || "(unassigned)"}</div>
      <div class="muted">markers: ${p.marker_ids.join(", ")} · placements: ${p.placements_seen.join("+")}</div>
      <div>pos: (${x.toFixed(2)}, ${y.toFixed(2)}, ${z.toFixed(2)}) m</div>
      <div>yaw: ${p.body_yaw_deg.toFixed(1)}° · conf ${p.confidence}</div>
    `;
    peopleList.appendChild(card);
  }
}

// ---------- WS plumbing --------------------------------------------------

const stream = new CameraStream({
  video: makeHiddenVideo(),  // hidden — we don't show the raw image on /track3d
  overlayCanvas: null,
  statusEl,
  fpsEl,
});

function makeHiddenVideo() {
  const v = document.createElement("video");
  v.autoplay = true; v.playsInline = true; v.muted = true;
  v.style.display = "none";
  document.body.appendChild(v);
  return v;
}

async function refreshCameraInfo() {
  try {
    const cams = await api("/api/cameras");
    const c = cams.find((x) => x.id === 1) || cams[0];
    if (!c) {
      camStatus.textContent = "No camera row in DB.";
      banner.innerHTML = `<a href="/admin">Open Admin → Cameras</a> to set up a camera.`;
      return;
    }
    const lines = [
      `${c.name} (id ${c.id})`,
      c.intrinsic_calibrated
        ? `intrinsic ✓  reproj ${c.intrinsic_reproj_error_px?.toFixed(2)} px`
        : `intrinsic ✗  — ChArUco capture not done`,
      c.extrinsic_calibrated
        ? `extrinsic ✓  reproj ${c.extrinsic_reproj_error_px?.toFixed(2)} px`
        : `extrinsic ✗  — four floor corners not solved`,
      `floor: ${c.floor_rect_w_m} × ${c.floor_rect_h_m} m`,
      `marker side: ${c.marker_size_m} m`,
    ];
    camStatus.textContent = lines.join("\n");
    camStatus.style.whiteSpace = "pre";
    if (!c.intrinsic_calibrated || !c.extrinsic_calibrated) {
      banner.innerHTML = `Camera is partially calibrated. Open <a href="/admin">Admin → Cameras</a> to finish.`;
    } else {
      banner.textContent = "";
    }
  } catch (e) {
    camStatus.textContent = "Error: " + e.message;
  }
}

function onMessage(msg, _meta) {
  if (msg.scene_world) updateScene(msg.scene_world);
  else {
    banner.innerHTML = `Calibrate the camera first (intrinsic + extrinsic) to enable 3D — open <a href="/admin">Admin → Cameras</a>.`;
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

// ---------- wire UI ------------------------------------------------------

await stream.listDevices(document.getElementById("t3d-device-select"));
refreshCameraInfo();

document.getElementById("t3d-start").addEventListener("click", async () => {
  const [w, h] = document.getElementById("t3d-resolution").value.split("x").map(Number);
  const fps = Number(document.getElementById("t3d-fps").value);
  const deviceId = document.getElementById("t3d-device-select").value;
  document.getElementById("t3d-start").disabled = true;
  document.getElementById("t3d-stop").disabled = false;
  await stream.start({ deviceId, width: w, height: h, fps, onMessage });
});
document.getElementById("t3d-stop").addEventListener("click", () => {
  stream.stop();
  document.getElementById("t3d-start").disabled = false;
  document.getElementById("t3d-stop").disabled = true;
});
