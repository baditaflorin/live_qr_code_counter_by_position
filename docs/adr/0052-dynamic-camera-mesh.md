# ADR 0052 — Dynamic camera mesh: cameras come and go without operator intervention

## Status
Proposed (depends on ADR 0051).

## Context
Fixed cameras stay put for the whole workshop. Phone cameras don't. A 90-minute exercise with 30 phone-cameras involved generates a continuous stream of mesh changes:

- A phone's screen times out and the page suspends.
- A participant pockets the phone for an embodiment moment.
- A battery dies at minute 73.
- Late arrivals join at minute 12.
- Two phones briefly drop off Wi-Fi at the same moment when somebody walks through a Faraday-ish doorway.

ADR 0050's fusion was written assuming a static set of cameras. ADR 0005 introduced multi-camera fusion. Neither is wrong, but neither was designed for a *constantly mutating* set of contributors. Without explicit handling, the system either jitters as cameras flicker, freezes when a key contributor drops, or quietly accumulates observations from cameras that have actually departed.

The mesh is now an ongoing negotiation, not a setup step.

## Decision
Treat the active camera set as **derived state**, computed per fusion cycle from a `Camera.last_seen_at` heartbeat.

**Heartbeat-driven membership.**

- Every WS frame (or every 5 s for suspended cameras) updates `Camera.last_seen_at`.
- The fusion module (ADR 0050) re-derives "active cameras" each cycle as `last_seen_at >= now - 2s`.
- A camera that goes silent ≥ 2 s is dropped from fusion automatically; no operator action required.
- A new camera that joins is added to fusion the moment its calibration (ADR 0054) completes.

**Graceful coverage degradation.**

- When a camera drops, ADR 0050's per-marker fusion continues with whatever cameras remain. The fused world position has slightly higher uncertainty, but the model doesn't break.
- Per-frame coverage metrics (per ADR 0036) record the drop: `scene.active_cameras = 27` → `26`, with the dropped camera's last-known-coverage-area highlighted on the live planner (ADR 0053).
- A camera that crashes mid-observation has its in-flight contributions ignored — no half-frames in the fusion.

**Slot reservation for re-join.**

- A camera that goes `suspended` (page backgrounded, screen off) holds its `Camera` row + session id for 60 seconds. If the same browser hits `/camera` within that window, it resumes the slot — same camera id, same calibration cache, no warming-up phase.
- After 60 s the slot is released and a fresh re-join goes through full warming up.
- This handles the dominant pattern: a participant briefly pockets the phone, takes it out 20 s later, expects to keep contributing.

**Rebalance signals.**

When a camera departs and its dropped coverage is now unique (no other camera covers that area), the system emits a **rebalance signal** to the live planner (ADR 0053):

- `rebalance.gap_opened: { area_m2, location, age_s }` — broadcast to `/admin` and to the live planner.
- The planner identifies which currently-active phones are *closest* to the gap and could plausibly re-aim to cover it. Those phones receive a directional ping (per ADR 0053).

**Per-camera contribution score.**

Each camera carries a rolling 60-second contribution score: *"what fraction of the system's observations would have been lost if this camera had not been present?"*. This is the gamification surface in the participant's UI ("you contribute 12 %") and the prioritisation surface for rebalance pings ("the highest-contributor that just dropped").

## Consequences

**Positive:**
- The system handles real-world phone churn invisibly. Operators never have to manage which phones are in or out.
- Re-join in the dominant case (phone briefly suspended) is seamless — no warming-up flash, no operator notice.
- The contribution score gives the system a self-aware notion of "which cameras matter most" — useful for both the rebalance loop and post-event diagnostics.

**Negative:**
- The 2-second drop threshold is a heuristic. Too short = thrashing on brief network blips; too long = stale observations linger. Mitigation: configurable per workshop; default 2 s based on typical Wi-Fi blip durations.
- "Per-camera contribution score" is a small but non-trivial computation. Mitigation: amortised across a 60 s window; cheap to maintain incrementally.

**Risks:**
- A network blip drops *all* phones simultaneously (the venue's Wi-Fi power-cycles). The fusion model collapses for the blip duration. Mitigation: expected and documented; the WS handler resumes from where it left off; tracking samples are missing for the blip window but the session continues.
- A malicious phone holds its slot but contributes garbage. Mitigation: ADR 0055's quality scoring downweights it; persistent garbage triggers `low_quality` exclusion automatically.

## Alternatives considered
- **Operator-curated camera mesh.** Works for fixed setups; defeats ADR 0051's whole premise.
- **Strict join/leave events** instead of heartbeat-derived state. Brittle — a missed leave-event keeps a dead camera "active" forever; the heartbeat approach is self-correcting.
- **Sticky 5-minute slot reservation** on suspend. Too long; locks out a re-aiming participant who tries to switch which phone they're using.
