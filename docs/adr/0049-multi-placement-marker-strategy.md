# ADR 0049 — Multi-placement marker strategy: hat + chest + back per person

## Status
Proposed (depends on ADR 0048 pose estimation; relates to ADR 0042 budget).

## Context
A single marker per person fails predictably:

| Placement                | Visible from              | Fails when                         |
| ------------------------ | ------------------------- | ---------------------------------- |
| **Hat (top-down)**       | Overhead / gallery cameras| Person looks down, wears a hood, the marker tilts during dance/movement |
| **Chest (front)**        | Front-facing cameras      | Person turns away                  |
| **Back**                 | Rear cameras              | Person faces camera                |
| **Wrist / arm-band**     | When arm raised           | Arm at side                        |
| **Lanyard around neck**  | All horizontal angles when standing | Person bends forward; lanyard flips |

The slide deck specifies **six gallery cameras** shooting *from above*. Hat-mounted is the obvious primary, and that's the implicit default of the system today. But:

1. Even with six cameras, an overhead marker on a participant standing under a beam is invisible to all of them.
2. The slide deck's witness gestures (`WITNESS`, `YOU + INTENT_SPEAK`) need *facing direction* — top-down hat markers can give yaw if the marker has a clearly-marked "front" edge, but this is fragile (a hat rotated on the head shifts yaw without the body turning).
3. Multi-camera fusion (ADR 0005) helps with positional coverage but doesn't help with facing direction unless markers are visible from the side cameras too.

A marker *constellation* — multiple markers per person, each at a known body location, all linked to the same person id — solves all three. From any camera angle, at least one marker is visible. When ≥2 are simultaneously detected, their relative offset gives **body orientation** robustly: a chest marker at floor `(3.0, 2.0)` and a back marker at `(3.0, 1.7)` says the person is facing toward `+y` regardless of how the hat is rotated.

## Decision
Each person gets **3 markers**, all linked to the same `Person` row, each tagged by **placement**.

Schema change on `Marker`:

```python
placement: Mapped[str] = mapped_column(String(20))  # 'hat' | 'chest' | 'back' | 'wrist' | 'accessory'
```

Default kit per participant:

| Placement | Why                                                                  | Recommended attach |
| --------- | -------------------------------------------------------------------- | ------------------ |
| `hat`     | Primary visibility from gallery cameras. Highest detection rate.     | Adhesive cap or stitched onto a baseball cap. |
| `chest`   | Front-facing detection; carries body orientation when paired with `back`. | Lanyard at sternum height, marker laminated. |
| `back`    | Rear cameras; orientation pair with `chest`; redundancy when chest is occluded by raised arms. | Same lanyard, marker on the back panel. |

**Detection pipeline change.** After detection (and optional pose estimation per ADR 0048):

1. Group detected markers by `person_id` (lookup via `Marker.person_id`).
2. **Person observation** = the union of all detected markers belonging to one person, this frame.
3. **Position**: weighted average of detected markers' world positions, weights = detection-confidence × pose-reprojection-quality.
4. **Body orientation**: when ≥2 markers of the same person are detected and their *placements* are known and non-collinear (e.g. `chest` + `back`, or `hat` + `chest`), body yaw is computed directly from their world-frame offset vector. When only one marker is detected, body yaw falls back to the marker's own pose (per ADR 0048) — accurate for `chest`/`back`, less so for `hat` (which can rotate on the head independently).
5. **Cluster detection** uses the person observation, not raw markers — so two visible markers on the same person can't accidentally form a "cluster of two" with themselves.

**Per-camera placement priority.** The kit editor (ADR 0030) gains a per-camera *placement preference*: gallery cameras prioritise `hat`, side-of-room cameras prioritise `chest`/`back`. The placement-priority feeds confidence weighting in step 3 above.

**Budget impact.** With 3 markers per person and 138 IDs reserved for people (per ADR 0042):

```
138 person IDs ÷ 3 markers/person = 46 people max
```

That's well below the 100-person target in ADR 0039's destination. **Action**: when the active workshop is configured for >40 people, the system automatically **prompts to switch to `DICT_4X4_1000`** (1000 IDs total — 800+ available for people after reservations). The dictionary is per-workshop in ADR 0010 anyway. ADR 0031 thresholds get more demanding at higher dictionary sizes (`DICT_4X4_1000` requires ~50 px per marker side for reliable decoding) so the workshop also gets a print-size warning.

## Consequences

**Positive:**
- **Coverage**: from any angle, at least one of the three markers is usually visible. Detection rate per person rises from ~80 % (single hat) to ~98 % (any of three).
- **Orientation**: chest+back offset gives reliable body yaw, independent of hat rotation. Witness inference (ADR 0027) gets a much stronger signal.
- **Redundancy**: a marker that falls off mid-workshop doesn't make the participant invisible.
- **Vertical info**: with hat (~1.7 m), chest (~1.2 m), and back (~1.2 m) at known heights, the 3D pose data (ADR 0048) becomes self-validating — if a "hat" marker reports z = 0.5 m, something's wrong.

**Negative:**
- **3× printing cost.** Mitigated by the existing PDF generator — one extra page per workshop.
- **3× attach effort** at registration. Mitigated by pre-assembled kits: the participant is handed a baseball cap with the hat marker pre-attached and a lanyard with chest+back markers laminated; total fit time ~15 seconds per person.
- **Budget pressure**: ADR 0042's 96-ID reservation now fits 46 people. Above that we move to `DICT_4X4_1000`, which has its own resolution implications (ADR 0031).

**Risks:**
- A participant accidentally wearing two lanyards (e.g. picked up a spare) reports orientation that's wrong. Mitigation: registration step pairs each lanyard's two markers explicitly with the person; orphan or double-issued markers are flagged in the audit log.
- Markers at different placements get different lighting (chest in shadow, hat in flare). Detection rates skew. Mitigation: per-placement detection-rate is a metric in ADR 0036; chronic placement bias surfaces in the quarterly memo.
- A back marker is occluded by a worn jacket; participants forget to pull it out from under. Mitigation: the briefing covers this; the lanyard is designed to ride on top of jackets.

## Alternatives considered
- **Single hat marker** (current default). Simplest; loses orientation reliability and back-camera coverage. Acceptable for a single-camera workshop, insufficient for the slide deck's six-camera setup.
- **Hat + chest only.** Two markers, similar gains for forward-facing cameras; misses rear-camera coverage. Reasonable budget compromise; not recommended once `DICT_4X4_1000` is the default.
- **Five markers per person** (hat, chest, back, both wrists). Better wrist gesture detection (raised hand for `INTENT_SPEAK`); 5× printing; budget unfriendly even at `DICT_4X4_1000`. Defer.
- **Markers on accessories that move with the body** (badge ribbon, scarf). High friction; marker flatness and size constraints are hard to meet with non-rigid backing.
