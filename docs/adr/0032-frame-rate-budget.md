# ADR 0032 — Frame-rate budget by use case

## Status
Proposed.

## Context
Frame rate is currently a single dropdown in the Live UI (5 / 10 / 15 / 20 fps). One number drives every consumer of frames. That's wrong: the *cost* of a frame is constant (encode + WS + detect ≈ 50–100 ms per frame at 1080p), but the *value* of a frame varies by use case:

| Use case                    | What it needs                       | Useful fps     |
| --------------------------- | ----------------------------------- | -------------- |
| Live counter (`/`)          | Eye comfort, snapshot accuracy      | **5–10 fps**   |
| Tracking samples (ADR 0008) | Sub-second cluster transitions      | **2 Hz** writes (so 4–6 fps detection feeding the smoother) |
| Marker tracker (ADR 0004)   | Sub-100 ms response to motion       | **10 fps**     |
| Cluster overlay rendering   | Smooth motion to the eye            | **30 fps render**, decoupled from detection |
| Highlight reel frames (0019)| 1 frame every ~2 s for clip windows | **0.5 fps writes** |
| Calibration (ADR 0012)      | A few stable frames                 | **2–3 fps**    |
| Drift detection (0015)      | 5-second median, sample sparsely    | **1 fps**      |

Running everything at 20 fps wastes 4× the CPU and 4× the upload bandwidth for the same outcome. Running at 5 fps starves the marker tracker. There's no universal answer; each subsystem wants its own rate.

## Decision
Decouple **camera capture rate** (set by the camera UI) from **per-subsystem rates** by introducing a *frame distributor* in `static/lib/camera.js`.

- The camera captures at a single configurable rate (default **10 fps**).
- A `FrameRouter` sits between capture and consumers. It accepts subscribe-with-rate calls:
  - `frameRouter.subscribe("ws-detect", { fps: 10, callback })` — the live WS sender.
  - `frameRouter.subscribe("highlight-reel", { fps: 0.5, callback })` — disk frame archiver if recording.
  - `frameRouter.subscribe("drift-check", { fps: 1, callback })` — anchor positions.
- Each subscriber gets *every Nth frame*, not the same frame. CPU is amortised; bandwidth scales with the highest subscribed rate, not the sum.
- A new `/api/system/limits` endpoint reports the configured rates so `/admin` can show "WS detect: 10 fps · highlight: 0.5 fps · drift: 1 fps · render: 30 fps".

For the **render layer** (cluster hulls, marker outlines, zone overlays) the canvas redraws at `requestAnimationFrame` (~60 fps), interpolating between WS-arrival snapshots. This is independent of detection rate and gives smooth motion even when detection runs at 5 fps.

A per-camera *adaptive* mode (default off) drops capture rate by 50 % if the WS upload buffer exceeds 2 frames — the network gets to dictate the ceiling instead of the operator.

## Consequences

**Positive:**
- 4× less CPU and bandwidth on the operator's laptop for the same perceived smoothness.
- Operator can run multi-camera (ADR 0005) on one laptop without the fan turning on — capture is shared, not duplicated per consumer.
- Detection latency stays low (10 fps) while expensive subsystems (highlight reel) only sip frames when they need them.

**Negative:**
- The cluster overlay sometimes shows interpolated positions that are slightly behind the actual marker. Acceptable for the human eye; not for hard-realtime use cases (none in this system).
- More moving parts in `lib/camera.js`. Tests required.

**Risks:**
- Subscribers accidentally specify too-high rates and the system silently degrades. Mitigation: the `/admin` panel warns when the sum of subscribed rates exceeds capture rate.
- Adaptive throttling masks an underlying network problem. Mitigation: it's logged at WARN; the audit log (ADR 0009) records the throttle event.

## Alternatives considered
- **Status quo single fps.** Simple, wasteful.
- **Per-subscriber capture session** (each WS opens its own getUserMedia stream). Doesn't work — a webcam can only be opened once per process.
- **Server-side rate decimation** — the camera sends at 30 fps, the server picks every Nth. Wastes upload bandwidth.
