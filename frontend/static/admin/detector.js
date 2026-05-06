import { api } from "/static/common.js";

const DEFAULT_CONFIG = {
  detector_type: "apriltag",
  marker_size_m: 0.05,
  dual_detection_mode: false,
  apriltag: {
    quad_decimate: 4.0,
    quad_sigma: 0.0,
    refine_edges: false,
    decode_sharpening: 0.0,
    nthreads: 4,
  },
  aruco: {
    adaptiveThreshWinSizeMin: 5,
    adaptiveThreshWinSizeMax: 35,
    adaptiveThreshWinSizeStep: 6,
    minMarkerPerimeterRate: 0.02,
    cornerRefinementMethod: "CORNER_REFINE_SUBPIX",
  },
};

let currentConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
let savedConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));

function getFormConfig() {
  // Build config from form, preserving ArUco params from savedConfig
  return {
    detector_type: document.getElementById("detector-type").value,
    marker_size_m: parseFloat(document.getElementById("marker-size").value),
    dual_detection_mode: document.getElementById("detector-dual-mode").checked,
    apriltag: {
      quad_decimate: parseFloat(document.getElementById("apriltag-quad-decimate").value),
      quad_sigma: parseFloat(document.getElementById("apriltag-quad-sigma").value),
      refine_edges: document.getElementById("apriltag-refine-edges").checked,
      decode_sharpening: parseFloat(document.getElementById("apriltag-decode-sharpening").value),
      nthreads: parseInt(document.getElementById("apriltag-nthreads").value),
    },
    aruco: savedConfig.aruco, // Preserve ArUco config from server
  };
}

function setFormConfig(config) {
  document.getElementById("detector-type").value = config.detector_type;
  document.getElementById("marker-size").value = config.marker_size_m;
  document.getElementById("detector-dual-mode").checked = config.dual_detection_mode;
  document.getElementById("apriltag-quad-decimate").value = config.apriltag.quad_decimate;
  document.getElementById("apriltag-quad-sigma").value = config.apriltag.quad_sigma;
  document.getElementById("apriltag-refine-edges").checked = config.apriltag.refine_edges;
  document.getElementById("apriltag-decode-sharpening").value = config.apriltag.decode_sharpening;
  document.getElementById("apriltag-nthreads").value = config.apriltag.nthreads;
  updateValueLabels();
}

function updateValueLabels() {
  document.getElementById("quad-decimate-val").textContent =
    document.getElementById("apriltag-quad-decimate").value;
  document.getElementById("nthreads-val").textContent =
    document.getElementById("apriltag-nthreads").value;
  document.getElementById("quad-sigma-val").textContent =
    document.getElementById("apriltag-quad-sigma").value;
  document.getElementById("decode-sharpening-val").textContent =
    document.getElementById("apriltag-decode-sharpening").value;
  document.getElementById("marker-size-val").textContent =
    document.getElementById("marker-size").value;
}

function hasUnsavedChanges() {
  const formConfig = getFormConfig();
  return JSON.stringify(formConfig) !== JSON.stringify(savedConfig);
}

function showStatus(message, type = "info") {
  const statusEl = document.getElementById("detector-status");
  statusEl.textContent = message;
  statusEl.className = `status-pill status-${type}`;
}

function updateUnsavedIndicator() {
  const changesEl = document.getElementById("detector-changes");
  if (hasUnsavedChanges()) {
    changesEl.style.display = "block";
  } else {
    changesEl.style.display = "none";
  }
}

async function loadDetectorConfig() {
  try {
    showStatus("Loading...", "info");
    const config = await api("/api/admin/detector/config");
    savedConfig = JSON.parse(JSON.stringify(config));
    currentConfig = JSON.parse(JSON.stringify(config));
    setFormConfig(config);
    showStatus("Ready", "success");
    updateUnsavedIndicator();
  } catch (err) {
    console.error("Failed to load detector config:", err);
    let errorMsg = "Error loading config";
    if (err && typeof err === "object") {
      if (err.message) errorMsg = err.message;
      else if (err.detail) errorMsg = err.detail;
    }
    showStatus(errorMsg, "error");
  }
}

async function applyConfig(persist = false) {
  try {
    const config = getFormConfig();
    showStatus("Applying...", "info");

    const response = await api("/api/admin/detector/config", {
      method: "POST",
      body: JSON.stringify(config),
    });

    savedConfig = JSON.parse(JSON.stringify(config));
    updateUnsavedIndicator();

    if (persist) {
      showStatus("✓ Saved to disk", "success");
    } else {
      showStatus("✓ Applied (not saved)", "info");
    }
  } catch (err) {
    console.error("Failed to apply detector config:", err);
    let errorMsg = "Failed to apply";
    if (err && typeof err === "object") {
      if (err.message) errorMsg = err.message;
      else if (err.detail) errorMsg = err.detail;
      else if (err.statusText) errorMsg = err.statusText;
    }
    showStatus("Error: " + errorMsg, "error");
  }
}

export function initDetector() {
  // Sync value labels on slider changes
  document.getElementById("apriltag-quad-decimate").addEventListener("input", () => {
    updateValueLabels();
    updateUnsavedIndicator();
  });
  document.getElementById("apriltag-nthreads").addEventListener("input", () => {
    updateValueLabels();
    updateUnsavedIndicator();
  });
  document.getElementById("apriltag-quad-sigma").addEventListener("input", () => {
    updateValueLabels();
    updateUnsavedIndicator();
  });
  document.getElementById("apriltag-decode-sharpening").addEventListener("input", () => {
    updateValueLabels();
    updateUnsavedIndicator();
  });
  document.getElementById("marker-size").addEventListener("input", () => {
    updateValueLabels();
    updateUnsavedIndicator();
  });

  // Detect changes in dropdowns and checkboxes
  document.getElementById("detector-type").addEventListener("change", updateUnsavedIndicator);
  document.getElementById("detector-dual-mode").addEventListener("change", updateUnsavedIndicator);
  document.getElementById("apriltag-refine-edges").addEventListener("change", updateUnsavedIndicator);

  // Button handlers
  document.getElementById("detector-test-btn").addEventListener("click", () => {
    applyConfig(false);
  });

  document.getElementById("detector-save-btn").addEventListener("click", () => {
    applyConfig(true);
  });

  document.getElementById("detector-reset-btn").addEventListener("click", () => {
    setFormConfig(DEFAULT_CONFIG);
    updateUnsavedIndicator();
  });

  // Load initial config
  loadDetectorConfig();
}

export function loadDetector() {
  loadDetectorConfig();
}
