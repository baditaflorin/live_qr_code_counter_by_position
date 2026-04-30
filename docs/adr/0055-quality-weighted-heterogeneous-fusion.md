# ADR 0055 — Quality-weighted fusion for heterogeneous cameras

## Status
Proposed (depends on ADR 0050 fusion, ADR 0051 / 0052 phone cameras).

## Context
ADR 0050's per-marker fusion uses *inverse-variance-weighted averaging* — every camera contributes proportionally to how confident its observation is. That's mathematically right when all cameras are *similar*. With phone-cameras (ADRs 0051–0054) the input is wildly heterogeneous:

- A 2024 iPhone 15 Pro on a tripod — clean optics, autofocus, OIS, 60 fps, 1080p.
- A 2018 mid-range Android — soft optics, no stabilisation, 24 fps.
- A phone held in someone's hand at the back of the room — shake, motion blur, occasional lens-finger.
- A phone in low-light at floor level — high ISO noise, exposure hunting.
- An old laptop webcam plugged in by the operator — fixed focus, decent stable mount.

Treating these equally means a single bad camera's marker observation gets the same vote as a great one. The fused world position drifts toward the noisiest contributor.

The fix is to weight each camera's contribution by its **observed quality** — measured live, not asserted up front.

## Decision
Compute a per-camera quality score `Q ∈ [0, 1]` from rolling 60-second metrics, and use `Q²` as a multiplier on each camera's per-observation fusion weight.

**Component metrics** (each normalised to `[0, 1]`):

| Metric                             | What it captures                                         | How it's measured                                        |
| ---------------------------------- | -------------------------------------------------------- | -------------------------------------------------------- |
| `q_density`                        | Camera sees the room at all                              | `markers_per_frame_median / 8`, capped at 1              |
| `q_reproj`                         | Pose estimation is consistent                            | `1 − clip(reproj_error_px_median / 4, 0, 1)`             |
| `q_position_stability`             | World-frame positions don't drift when nothing's moving  | `1 − clip(σ_world_pos / 0.20m, 0, 1)`                    |
| `q_frame_stability`                | Frame rate isn't jittering                               | `1 − clip(σ_frame_interval_ms / 100ms, 0, 1)`            |
| `q_latency`                        | Network round-trip is reasonable                         | `1 − clip(ws_rtt_ms / 500ms, 0, 1)`                      |
| `q_calibration_age`                | Calibration is recent (per ADR 0054)                     | `exp(−minutes_since_recalibration / 30)`                 |

**Composite score:**

```
Q = pow(prod(component_metrics), 1/6)         # geometric mean
```

Geometric mean is right here: a camera that is *good on average but terrible at one thing* (e.g. clean optics, but laggy network) should be downweighted more aggressively than the arithmetic mean implies. One bad component drags `Q` down hard.

**Fusion weighting.** When fusing N cameras' observations of the same marker:

```
weight_i = (1 / variance_i) * Q_i²
fused = sum(weight_i * obs_i) / sum(weight_i)
```

`Q²` rather than `Q`: a camera at `Q = 0.5` contributes a quarter of what a `Q = 1.0` camera does. Strongly favours the good cameras without silencing the bad ones.

**Quality threshold.** Below `Q < 0.2`, the camera enters `low_quality` state (per ADR 0051):

- Observations excluded from fusion.
- Camera kept connected for diagnostics.
- Participant gets a hint: *"Your camera quality is low. Try holding more steadily or moving closer."*

**Participant UI surface.** The phone-camera page shows `Q` as a 5-star rating, updated every 10 s. Soft gamification. *"⭐⭐⭐⭐ — your camera is contributing strongly"* vs *"⭐⭐ — try cleaning the lens"*.

**Operator dashboard.** `/admin` shows `Q` per camera, sorted descending. The operator can spot a struggling phone at a glance and quietly walk over to help.

**Telemetry.** Every component metric is recorded to the `Metric` table from ADR 0036. Quarterly reviews surface patterns: *"old Androids consistently score Q ~0.4; we should suggest workshop sponsors provide a small fleet of mid-range Pixels for participants without good phones."*

## Consequences

**Positive:**
- Heterogeneous fleets work. A mix of a few good cameras and many merely-okay phones produces a high-quality fused scene.
- Participants self-correct: the star rating gives them a reason to care about how they hold the phone.
- Operators have a real signal — a single misbehaving camera no longer poisons the fusion.

**Negative:**
- Six metrics is a lot to compute and tune. Mitigation: each is cheap (rolling median + variance); the composite is a single multiplication chain.
- The `Q²` weighting is a heuristic. With more data we'd derive the right exponent from observed fusion error vs cluster ground truth. Mitigation: log everything (ADR 0036), revisit at the quarterly review (ADR 0041).

**Risks:**
- A camera that's high-quality but pointed at a useless area gets `Q ≈ 1` and contributes well — but the contribution is to *no one*, because no markers are visible. Wasted but not harmful. Mitigation: the convergence loop (ADR 0053) re-points it.
- A bad-actor phone holds steady, looks at the room, but transmits subtly wrong frames (e.g. CGI overlay, deepfake). The system would assign it high `Q`. Mitigation: out-of-scope for the current trust model; the room is assumed to be cooperating with the workshop.
- Quality-weighting could mask a global degradation — every camera drops to `Q = 0.5` simultaneously and the fusion model trusts them all proportionally. Mitigation: absolute `Q` thresholds are surfaced per camera; an admin alert fires when the fleet's median `Q` drops below 0.4.

## Alternatives considered
- **Equal-weight fusion.** Current state. Bad cameras drag fusion down; good ones can't pull it up.
- **Hard threshold only** (kick cameras below `Q = 0.4`, treat the rest equally). Simpler; loses the *gradation* that makes the participant gamification work.
- **Single quality metric** (just reprojection error). Misses real failure modes — a phone with clean lens but laggy network is invisible to a reproj-only metric.
- **Operator-curated camera trust** (operator marks each camera ⭐–⭐⭐⭐⭐⭐). Doesn't scale to 30 phones; defeats automatic mesh.

## Postscript
Combined with ADRs 0051–0054 this completes the ground-floor sensing stack: **phones join freely (0051) → mesh adapts as they come and go (0052) → coverage gaps are surfaced and fixed by the room itself (0053) → calibration converges from whatever fiducials are visible (0054) → fusion weights each camera by its measured quality (0055)**. The system stops being "operator-driven multi-camera infrastructure" and becomes "every phone in the room, contributing what it can."
