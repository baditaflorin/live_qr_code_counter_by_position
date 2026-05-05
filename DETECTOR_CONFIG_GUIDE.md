# Detector Configuration Guide

## Overview

The detector configuration system allows you to tune marker detection parameters **at runtime without restarting the service**. You can:

- ✅ Adjust detection speed vs accuracy tradeoff
- ✅ Switch between AprilTag and ArUco detectors dynamically
- ✅ Run both detectors side-by-side for A/B testing
- ✅ Persist configuration across service restarts
- ✅ Load settings from environment variables or disk

## Quick Start

### Get Current Configuration
```bash
curl http://localhost:8000/api/admin/detector/config
```

Response:
```json
{
  "detector_type": "apriltag",
  "marker_size_m": 0.05,
  "dual_detection_mode": false,
  "apriltag": {
    "quad_decimate": 4.0,
    "quad_sigma": 0.0,
    "refine_edges": false,
    "decode_sharpening": 0.0,
    "nthreads": 4
  },
  "aruco": { ... }
}
```

### Update Configuration at Runtime
```bash
curl -X POST http://localhost:8000/api/admin/detector/config \
  -H "Content-Type: application/json" \
  -d '{
    "detector_type": "apriltag",
    "marker_size_m": 0.05,
    "apriltag": {
      "quad_decimate": 2.0,
      "nthreads": 4,
      "refine_edges": false
    }
  }'
```

**No restart needed** — changes apply immediately to all new frames.

## Configuration Options

### AprilTag Parameters

| Parameter | Type | Range | Default | Effect |
|-----------|------|-------|---------|--------|
| `quad_decimate` | float | 1.0–8.0 | 4.0 | Speed optimization. 1.0 = accurate/slow, 8.0 = fast/inaccurate |
| `quad_sigma` | float | 0.0–2.0 | 0.0 | Edge blur before detection (0=off, higher=more blur) |
| `refine_edges` | bool | - | false | CPU-intensive edge refinement (+10-20% latency, +5% accuracy) |
| `decode_sharpening` | float | 0.0–2.0 | 0.0 | Sharpening filter (0=off, higher=more sharpen) |
| `nthreads` | int | 1–8 | 4 | Parallel detection threads |

### ArUco Parameters

| Parameter | Type | Range | Default | Effect |
|-----------|------|-------|---------|--------|
| `adaptiveThreshWinSizeMin` | int | 3–20 | 5 | Minimum adaptive threshold window |
| `adaptiveThreshWinSizeMax` | int | 10–80 | 35 | Maximum adaptive threshold window |
| `adaptiveThreshWinSizeStep` | int | 1–10 | 6 | Window size step |
| `minMarkerPerimeterRate` | float | 0.01–0.5 | 0.02 | Filter for small detections |
| `cornerRefinementMethod` | enum | NONE, SUBPIX | SUBPIX | Corner refinement |

### Common Parameters

| Parameter | Type | Range | Default | Effect |
|-----------|------|-------|---------|--------|
| `detector_type` | enum | "apriltag", "aruco" | "apriltag" | Which detector to use |
| `marker_size_m` | float | 0.01–1.0 | 0.05 | Physical marker size in metres |
| `dual_detection_mode` | bool | - | false | Run both detectors (CPU-heavy, testing only) |

## Tuning Guide

### Problem: Detection is too slow

**Solution**: Increase `quad_decimate`
```bash
# Fast mode (trade accuracy for speed)
curl -X POST http://localhost:8000/api/admin/detector/config \
  -H "Content-Type: application/json" \
  -d '{"detector_type": "apriltag", "apriltag": {"quad_decimate": 6.0}}'
```

### Problem: Missing distant or small markers

**Solution**: Decrease `quad_decimate` and enable edge refinement
```bash
# Accurate mode (trade speed for accuracy)
curl -X POST http://localhost:8000/api/admin/detector/config \
  -H "Content-Type: application/json" \
  -d '{
    "detector_type": "apriltag",
    "apriltag": {
      "quad_decimate": 1.0,
      "refine_edges": true
    }
  }'
```

### Problem: Try ArUco instead of AprilTag

```bash
curl -X POST http://localhost:8000/api/admin/detector/config \
  -H "Content-Type: application/json" \
  -d '{"detector_type": "aruco"}'
```

### Problem: Compare both detectors side-by-side

```bash
# Enable dual-detection mode (logs both detectors)
curl -X POST http://localhost:8000/api/admin/detector/config \
  -H "Content-Type: application/json" \
  -d '{"dual_detection_mode": true}'
```

**⚠️ Warning**: Dual-detection mode doubles detection latency. Disable after testing.

## Configuration Persistence

### Load from Environment Variables

At startup, configuration is loaded from environment variables:

```bash
# Set before starting the service
export DETECTOR_TYPE=apriltag
export APRILTAG_QUAD_DECIMATE=2.0
export APRILTAG_NTHREADS=4
export MARKER_SIZE_M=0.05
export DUAL_DETECTION_MODE=false
```

### Persist Configuration to Disk

When you POST a new configuration, it's automatically saved to:
```
{DATA_DIR}/detector_config.json
```

On restart, config is loaded: **env vars → disk file → defaults**

### Example detector_config.json

```json
{
  "detector_type": "apriltag",
  "marker_size_m": 0.05,
  "dual_detection_mode": false,
  "apriltag": {
    "quad_decimate": 2.0,
    "quad_sigma": 0.0,
    "refine_edges": true,
    "decode_sharpening": 0.0,
    "nthreads": 4
  },
  "aruco": {
    "adaptiveThreshWinSizeMin": 5,
    "adaptiveThreshWinSizeMax": 35,
    "adaptiveThreshWinSizeStep": 6,
    "minMarkerPerimeterRate": 0.02,
    "cornerRefinementMethod": "CORNER_REFINE_SUBPIX"
  }
}
```

## API Reference

### GET /api/admin/detector/config
Get current detector configuration.

**Response**: DetectorConfig JSON

---

### POST /api/admin/detector/config
Update detector configuration at runtime. Changes apply immediately.

**Body**: Partial or full DetectorConfig JSON (only specified fields are updated)

**Response**:
```json
{
  "status": "success",
  "message": "Detector reconfigured: apriltag",
  "config": { ... }
}
```

---

### GET /api/admin/detector/schema
Get JSON Schema for configuration parameters. Use this to build a UI form.

**Response**: Schema with parameter descriptions, ranges, defaults, and types.

## Performance Metrics

### Detection Latency by quad_decimate

| quad_decimate | Latency (ms) | Accuracy | Detection Range |
|---------------|------------|----------|-----------------|
| 1.0 | 50–100 | High | 3+ meters |
| 2.0 | 20–30 | Good | 2+ meters |
| 4.0 | 0.3–1.0 | Fair | 1+ meter |
| 8.0 | 0.2–0.5 | Low | < 1 meter |

### Effect of refine_edges

- **Disabled (default)**: ~0.3ms per frame, baseline accuracy
- **Enabled**: +10-20% latency (~0.04-0.06ms), +5% detection rate improvement

### Thread Count Impact

- More threads = faster detection (but CPU bound at 4+ threads on most systems)
- Recommended: 4 threads (default) unless running on low-power hardware

## Testing Workflow

1. **Establish baseline**:
   ```bash
   curl http://localhost:8000/api/admin/detector/config > baseline.json
   ```

2. **Try a variation** (e.g., lower quad_decimate for accuracy):
   ```bash
   curl -X POST http://localhost:8000/api/admin/detector/config \
     -d '{"apriltag": {"quad_decimate": 2.0}}' -H "Content-Type: application/json"
   ```

3. **Monitor metrics** (WebSocket detection frames):
   - Watch for `detection.latency_ms` and `detection.markers_seen` in `/api/metrics`
   - Verify marker detection count and latency over ~30 seconds

4. **Compare AprilTag vs ArUco**:
   ```bash
   # Test AprilTag
   curl -X POST ... -d '{"detector_type": "apriltag"}'
   # (monitor metrics)
   
   # Test ArUco
   curl -X POST ... -d '{"detector_type": "aruco"}'
   # (monitor metrics)
   ```

5. **Use dual-detection for A/B testing**:
   ```bash
   curl -X POST ... -d '{"dual_detection_mode": true}'
   # Both detectors run, log results with source labels
   ```

6. **Revert to baseline**:
   ```bash
   curl -X POST ... -d @baseline.json -H "Content-Type: application/json"
   ```

## Frontend Configuration UI (Optional)

A web form can be built using the schema from `/api/admin/detector/schema`:

- Displays all parameters grouped by detector type
- Sliders for numeric ranges (quad_decimate, nthreads, etc.)
- Toggles for boolean flags (refine_edges, dual_detection_mode)
- Dropdowns for enum values (detector_type, cornerRefinementMethod)
- "Test" button: apply without saving to disk
- "Save" button: persist to {DATA_DIR}/detector_config.json

## Troubleshooting

**Q: Changes don't apply immediately**
- A: Wait ~100ms for the next WebSocket frame. Detection is asynchronous.

**Q: Detector crashes when I set invalid parameters**
- A: Parameters are validated on POST. If you get a 400 error, check the message for what's out of range.

**Q: dual_detection_mode is slow**
- A: Normal! Running both detectors doubles latency. Disable when not A/B testing.

**Q: Configuration is reset after restart**
- A: If env vars are set, they override the disk file. Clear env vars to use persisted config:
  ```bash
  unset DETECTOR_TYPE APRILTAG_QUAD_DECIMATE ...
  ```

**Q: Which detector is better?**
- A: It depends on your markers and environment. Test both with dual-detection mode and compare metrics.

## Advanced: Factory Pattern Internals

The system uses a factory pattern to support pluggable detectors:

- `BaseDetector`: Abstract interface (detect, estimate_pose, get_dictionary_name, dictionary_size)
- `AprilTagDetector`: Wraps pupil-apriltags with IPPE pose estimation
- `ArUcoDetector`: Wraps cv2.aruco with OpenCV solvePnP
- `DualDetector`: Runs both AprilTag and ArUco simultaneously
- `create_detector(config)`: Factory function that returns appropriate detector instance

When you POST a new config, `detection.set_config()` recreates the detector with new parameters using the factory.

Thread safety is ensured via `threading.RLock` in the ConfigManager.
