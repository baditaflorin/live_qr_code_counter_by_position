# ADR 0073 — Orientation as a semantic channel

## Status
Proposed. Depends on ADR 0048 (6-DOF pose), ADR 0031 (resolution / marker-size
envelope). Extends ADR 0022 (adds an `orientation` fire model) and overlays
ADR 0023 (one card can carry several reactions when rotated). Does **not**
supersede 0023; the printed-eight stay valid. Lands together with the first
implementations of ADR 0021 (`participant_cards` table + `ParticipantRouter`)
and ADR 0022's four fire models — the experimental scoping below describes
the original first-cut shape; the *graduated* shape lives in the postscript.

## Context
ADR 0048 made yaw / pitch / roll a first-class signal: every detected marker
now carries a world-frame rotation in the WS payload. ADR 0022's existing
fire models (`pulse` / `level` / `gesture`) ignore rotation entirely — a
card raised at 0° fires the same event as one raised at 180°.

Several places in the kit pay a real cost for that:

- ADR 0023 spends **eight ID slots** to express what is, semantically, one
  decision class with eight possible values (`YES` / `NO` / `UNSURE` / …).
  A participant who wants to change their answer must put one card down
  and pick a different one up.
- ADR 0067's spare budget (36 IDs) is fine today but is the same pool that
  ADRs 0030 (custom decks) and any future activation cards draw from.
  Anything we can express in <1 ID/value is leverage.
- Live answers that drift ("I started at *yes*, I'm landing at *unsure*")
  have no representation today — the card was raised, the card was lowered;
  what happened in between is invisible.

Rotating a card is a faster gesture than swapping cards, and the pose
estimator already gives us the angle. The "physics for free" argument from
ADR 0048 applies again: the data is on the wire, we just aren't reading it.

## Decision
Add an **`orientation` fire model** alongside `pulse` / `level` / `gesture`
(see the ADR 0022 patch landing in the same change). A card whose row in
`ParticipantCard.params_json` is tagged `fire_model: "orientation"` is
interpreted by **rotation bucket** instead of presence.

### Bucket scheme

`yaw_deg` is partitioned into N equal-sized sectors with a **dead-zone**
between each pair of sectors. Buckets are assigned a symbol in
`params_json["orientation_buckets"]`:

```jsonc
{
  "fire_model": "orientation",
  "orientation_axis": "yaw",          // "yaw" | "pitch" | "roll"
  "orientation_buckets": [            // ordered by ascending angle
    { "center_deg":   0, "half_width_deg": 30, "value": "yes"    },
    { "center_deg":  90, "half_width_deg": 30, "value": "unsure" },
    { "center_deg": 180, "half_width_deg": 30, "value": "no"     },
    { "center_deg": 270, "half_width_deg": 30, "value": "tender" }
  ],
  "stability_window_s": 0.6,          // ADR 0022 activation gate
  "stability_tolerance_deg": 10       // see "Risks" below
}
```

A bucket is **active** when, over a sliding `stability_window_s` window,
≥ 80 % of samples fall within `half_width_deg` of `center_deg` *and* the
sample stddev within the window is ≤ `stability_tolerance_deg`. The dead
zone (any angle outside every bucket) emits no event — this is by design,
so a card mid-rotation does not flicker through every value on its way.

Discrete sectors only; no interpolation. ADR 0048 quotes ±15° orientation
error at low marker resolution (ADR 0031's 30 px floor); a 4-sector / 90°
spacing with a 30° half-width and 30° dead zone is comfortably above that.
**Six sectors is the practical maximum.** Beyond that, noise dominates.

### Event semantics

Each bucket transition emits one `OrientationEvent` (analogous to
`FiredEvent` in ADR 0014):

- **enter bucket**: `kind: "orientation_enter"`, `value: "yes"`
- **exit bucket**: `kind: "orientation_exit"`,  `value: "yes"`
- **change bucket**: implicit — exit-old + enter-new on the same frame

This gives downstream consumers a stream that mirrors `pulse`'s
fire-on-activate / fire-on-deactivate shape, so existing aggregators
(ADR 0023 live-count badge, ADR 0017 reflection card, ADR 0036 metrics)
plug in unchanged.

### Per-marker rate limit

ADR 0022's per-marker 1.5 s rate limit applies to the *card*, not the
*bucket*. So a participant flipping between *yes* and *no* twice a second
is still capped at one event every 1.5 s; the most recent stable bucket
wins on each fire. Prevents wrist-jitter from generating a vote storm.

### Experimental scoping (this ADR)

A full participant routing layer is still ADR-only (0021 / 0022). To avoid
coupling this experiment to that work — multiple agents are touching the
repo — the **first implementation** ships with a deliberately narrow shape:

- A new module `backend/orientation.py` with two pieces:
  1. A pure classifier `classify_yaw(yaw_deg, buckets) -> Optional[str]`.
  2. A stateful `OrientationRouter` that tracks per-marker bucket history
     and emits events.
- Marker IDs that the router watches are taken from the
  **`ORIENTATION_ROUTER_MARKERS`** env var (comma-separated). Empty → the
  router is inactive and the experiment is dormant. No DB schema change.
- Bucket configuration is taken from
  **`ORIENTATION_ROUTER_BUCKETS_JSON`** env var, defaulting to the four-sector
  yes / unsure / no / tender table above. Per-marker overrides land later,
  once the participant routing layer exists.
- Events are emitted on the WS payload as `orientation_events: [...]` and
  recorded in the existing `Metric` table (ADR 0036) with name
  `orientation.fire`. **No new database tables.**

When the participant router lands, the classifier graduates unchanged; the
router is rewired to read `ParticipantCard.fire_model == "orientation"`
rows and drop the env-var path. ADRs 0023 / 0067 will be revisited to
decide whether the eight reaction IDs collapse to one orientation card.

## Consequences

**Positive:**
- One ID can carry up to ~6 distinct discrete values without spending more
  of the 96-ID budget. ADR 0067's spare 36 stays untouched.
- Mid-question shifts are observable (`orientation_change` events), which
  is data the ADR 0023 yes/no/unsure cards literally cannot produce.
- Faster than swapping cards — a wrist twist is sub-second; picking up a
  different card from a communal table is multi-second.
- Falls out of ADR 0048's pose pipeline at zero CPU cost. The classifier is
  a single bucket-comparison per detected marker per frame.

**Negative:**
- One more thing to brief participants on. Mitigation: keep the
  experimental rollout to a single card class (e.g. one rotating
  *reaction* card per pilot workshop) so the briefing line is one
  sentence ("rotate it the way you mean it").
- Operators inspecting the kit see two ways a card can mean things
  (presence vs. orientation). Mitigation: the `kit` tag and printed label
  on the card distinguish them; the operator handbook (ADR 0060) gains a
  one-page section.

**Risks:**
- **Orientation precision floor.** ADR 0048 quotes ±15° at the resolution
  floor of ADR 0031 (≥ 30 px per marker side). Two adjacent buckets must
  therefore be ≥ 30° apart center-to-center for reliable classification at
  the worst legal marker size. The default config uses 90° spacing, well
  above this. Mitigation: the classifier rejects samples whose
  `reproj_error_px > 1.5`, falling back to "no event" rather than firing
  on noisy data.
- **Neutral position is not 0°.** A participant naturally holds a card
  off-axis (chest-level, slight yaw, slight tilt). ADR 0048's yaw_deg is
  in the *world frame*, not the participant's body frame, so the same wrist
  posture reads different yaws depending on which way they face. Mitigation:
  bucket centers are configured in world-frame yaw; the briefing tells
  participants to stand facing the operator end of the room. The
  participant routing layer will later add per-event "subtract holder yaw"
  to make this body-relative — but the experiment ships world-frame to
  avoid taking on that complexity now.
- **Wrist jitter at bucket edges.** A card held at exactly the bucket
  boundary can ping-pong. Mitigation: the dead zone between buckets
  (`half_width_deg < 90° / N`) and the stability window (≥ 0.6 s of
  ≤ 10° stddev) together filter this out. The per-marker rate limit
  caps the worst case at one event per 1.5 s.
- **Pitch / roll are noisier than yaw.** ADR 0048's yaw is the most
  reliable Euler angle (it's the rotation around the world up axis, which
  is the dominant degree of freedom for a held card). Pitch and roll are
  configurable for completeness but the default — and the recommended
  experiment — is `orientation_axis: "yaw"`.
- **Conflating with body yaw (ADR 0050).** A chest-placed marker rotates
  with the *person*, not the *card*. Mitigation: the
  `ORIENTATION_ROUTER_MARKERS` allowlist is opt-in per ID, so a chest
  marker is not enrolled by accident. Cards intended for orientation use
  are printed on a separate card (placement implicitly `accessory` per
  ADR 0049's nomenclature).

## Alternatives considered

- **Stick with one ID per value (status quo).** Cheap, debuggable, but
  burns IDs and forgoes the "rotation as gradient" expression entirely.
- **Continuous yaw → continuous value.** Tempting (a knob, not a switch),
  but the noise floor + briefing complexity make it not worth it for a
  workshop instrument. Discrete sectors keep the metaphor crisp.
- **Use position-on-floor as the channel** (e.g. step left for *no*, right
  for *yes* with the same card). Already covered by zones (ADR 0003 / 0014)
  and the standing-on-a-side gesture from the slide deck — no new ground
  to gain.
- **Ship as a property of `ParticipantCard.fire_model` directly.**
  Correct long-term home; rejected for the *experiment* to avoid blocking
  on the participant routing layer. Documented as the graduation path.

## Postscript

This ADR is intentionally a probe, not a foundation. If the rotation
gesture proves legible in a pilot workshop, it folds into ADR 0022 as a
permanent fire model and several reaction cards collapse into one. If it
doesn't — if participants find the "which way is yes" briefing harder than
just picking up a different card — the experiment is removed by deleting
one module and one env var, and ADRs 0022 / 0023 / 0067 are unchanged.

The cost of finding out is small; the upside is one less card to print
and the first time the room can express "I'm shifting".

### Graduation note

The original "experimental scoping" section above described an env-var-only
shape (`ORIENTATION_ROUTER_MARKERS`, no DB tables, no participant routing
layer). That shape shipped briefly; in the same change set the channel
**graduated** to the canonical home ADR 0021 / 0022 always intended:

- `participant_cards` and `participant_events` tables now exist (Alembic
  migration 0003). Per-card config (axis, buckets, stability tuning) lives
  in `params_json`; the elevated `fire_model` column drives routing.
- A real `ParticipantRouter` (ADR 0021) routes detections to the four fire
  models from ADR 0022 (`pulse` / `level` / `gesture` / `orientation`).
  Holder attribution, per-marker rate limit, and per-person rate limit are
  all in place; the co-occurrence-window bundling for theme + intent
  composites is deferred to a follow-up.
- The legacy env vars become a one-time **seed bridge**: at boot, any IDs
  in `ORIENTATION_ROUTER_MARKERS` are inserted as `orientation`-fire-model
  rows (idempotent — only IDs without an existing row are added). Once
  the rows exist, runtime config comes from them.
- WS payload key was renamed `orientation_events` → `participant_events`
  to match the broader scope; orientation events are one `kind` among the
  four fire models' events. The frontend has not consumed the old key, so
  this is a clean rename.
- CRUD endpoints land at `/api/participant-cards` (GET / POST / PATCH /
  DELETE) and a read-only `/api/participant-events` for the audit trail.

The experimental probe answered itself faster than expected. The sections
above are preserved as the design history; this postscript is the truth.
