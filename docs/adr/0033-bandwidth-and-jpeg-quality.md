# ADR 0033 — Bandwidth budget and adaptive JPEG quality

## Status
Proposed.

## Context
Each video frame travels browser → backend as a JPEG over WebSocket. At the current defaults — 1280 × 720, q=0.7 — a typical frame is **40–55 KB**. Multiply out:

| Setup                                       | Per-camera   | Multiple cameras                |
| ------------------------------------------- | ------------ | ------------------------------- |
| 720p · q=0.7 · 10 fps                       | 4–5 Mbps     | 6 cameras = **24–30 Mbps**      |
| 720p · q=0.7 · 5 fps                        | 2–3 Mbps     | 6 cameras = **12–18 Mbps**      |
| 1080p · q=0.7 · 10 fps                      | 9–11 Mbps    | 6 cameras = **54–66 Mbps**      |
| 4K · q=0.85 · 10 fps                        | ~30 Mbps     | 6 cameras = **180 Mbps**        |

Localhost handles all of these. **Real venue Wi-Fi** is the binding constraint:

- Eduroam-class venue Wi-Fi: ~30 Mbps upstream per client.
- Conference centre 5 GHz: 50–100 Mbps upstream when uncongested, 5–20 Mbps in a packed hall.
- 4G hotspot: 5–25 Mbps upstream, highly variable.

Multi-camera at 1080p is on the wrong side of this for most venues. The current frontend just keeps stuffing frames into the WebSocket; if upload is too slow, the WS buffer grows unboundedly and the live overlay starts lagging seconds behind reality.

## Decision
Add an explicit bandwidth budget with three coordinated mechanisms.

1. **Per-camera default profile.** Three named profiles selectable per camera:
   - `lite` — 960 × 540 · q=0.55 · 5 fps · ~1 Mbps. For weak Wi-Fi, multi-camera, mobile hotspots.
   - `standard` (default) — 1280 × 720 · q=0.70 · 10 fps · ~4 Mbps.
   - `pro` — 1920 × 1080 · q=0.80 · 10 fps · ~10 Mbps. For wired LAN or single-camera 4K stretch.

2. **Adaptive degrade.** While the capture-side WS buffer holds more than 2 frames waiting to be sent (i.e. upload is slower than capture), the camera streamer halves the JPEG quality (down to q=0.4 floor) before degrading frame rate (down to half the profile's fps). The detector tolerates q=0.4 for ArUco; the overlay tolerates 5 fps. Both are reversed when buffer drops back to ≤1 frame.

3. **Visible budget meter.** `/admin` and `/track` display a small meter: `↑ 3.2 Mbps · q=0.70 · 10 fps · buf 0` — green at 0–1 buffered, yellow at 2, red at 3+. If the meter is red for >5 seconds the operator sees a clear "your network is the bottleneck — switch to *lite* profile or use wired" hint.

## Consequences

**Positive:**
- The system stops silently degrading. Either it works at the chosen profile, or it visibly tells the operator to back off.
- `lite` profile makes phone-tethered hotspot setups viable for small workshops.
- Multi-camera (ADR 0005) becomes practical on real venue Wi-Fi by defaulting to `lite` and auto-tuning per camera.

**Negative:**
- q=0.4 frames have detectable JPEG artefacts that can occasionally cost a marker detection. Mitigation: that's the *degradation gracefully* part — better to drop one marker per second than to lag 5 s behind reality.
- Three profiles is a knob most operators won't touch, but they need to exist for the bad-network cases.

**Risks:**
- Adaptive quality oscillates near the network's capacity (q=0.7 → backpressure → q=0.4 → buffer empties → q=0.7 → repeat). Mitigation: 5-second hysteresis on quality changes; the change is visible in the meter so operators see what's happening.
- The buffer-watching heuristic can be fooled by network bursts. Mitigation: buffer-length is a 3-second moving average, not instantaneous.

## Alternatives considered
- **Hardware H.264/VP8 encoding** via `MediaRecorder`. Lower bandwidth at same quality, but introduces encoding delay (several frames) and complicates the per-frame WS protocol.
- **Server-side resolution downsizing** — but the upload is already the bottleneck.
- **Offload detection to the browser** with `js-aruco2`. Eliminates the upload entirely. Worth ADR-grade exploration but the detector is meaningfully less reliable, and we lose server-side smoothing (ADR 0004).
