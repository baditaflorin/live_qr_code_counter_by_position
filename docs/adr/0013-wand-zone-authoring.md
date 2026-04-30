# ADR 0013 — Zone authoring with a "wand" marker

## Status
Proposed (depends on ADR 0011 control markers, ADR 0012 calibration so positions land in floor coords).

## Context
Zone polygons today are clicked on a video preview from the keyboard. The drawing has been polished — click-to-edit, drag handles, mid-edge `+`, undo/redo (ADRs already implemented in [`zones.js`](../../frontend/static/admin/zones.js)) — but the operator is still indoors, in front of a laptop, eyeballing where the floor markings will be when the room is set up.

For Sala Rycerska this is backwards. The floor markings are placed by hand: a piece of gaffer tape, a chalk line, a rug edge. The natural way to tell the system "the *Yes* zone is *here*" is to walk the floor and gesture at the corners, not to peer at a webcam preview from the gallery and approximate.

## Decision
Reserve two control-marker ids (per ADR 0011) — `ZONE_PIN` and `ZONE_DONE` — and use them as a **physical zone-authoring wand**.

- The operator picks a formation in the admin UI (or via a future formation-control marker), then walks the floor.
- Each time `ZONE_PIN` is held still for ≥0.7 seconds at a new floor position (≥0.3 m from the previous pin), the system drops a vertex at that floor coordinate.
- `ZONE_DONE` held still for 0.7 seconds closes the polygon. The admin UI shows a "Save zone?" prompt with the auto-generated polygon and the formation tag pre-filled; one click commits it.
- Live overlay shows the wand's current position as a glowing dot and the polygon-in-progress in real time, so the operator can see what they're drawing.

The polygon is stored in **normalized image coords** the same as today (so the rest of the system needs no changes) but is computed from floor coords via the inverse homography (ADR 0003). That way zones authored with the wand follow perspective correctly.

## Consequences

**Positive:**
- Zones are defined where they are *actually applied* — on the floor — by the person who knows where the chalk lines go.
- Setup the day before: walk through every formation's zones (Block 4 two_camps, Block 6 circle, Privilege Walk bands), drop a few pins each, done.
- Onboarding for new operators is much shorter — "hold this card at each corner" beats "click vertices, then drag the mid-edge plus, then..."

**Negative:**
- Two more reserved control ids.
- Live polygon preview costs a touch more bandwidth (we already ship `detections` per frame; we'd add a `wand` field).

**Risks:**
- Operator drops the wand mid-walk; spurious pins. Mitigation: the dwell-time gate (≥0.7 s holding still) plus a min-distance gate (≥0.3 m from previous pin) plus a visible "live polygon" preview the operator can correct from.
- Polygon ends up self-intersecting if the operator walks a figure-8. Mitigation: server-side simplify that rejects self-intersection and shows a red overlay until the operator backtracks.

## Alternatives considered
- **Dwell-only with no DONE marker** — finalises after 5 s of no activity. Faster but error-prone; the operator inevitably stops mid-zone to think.
- **Pen-and-tablet drawing on the laptop** (status quo) — works but loses the on-floor-while-setting-up benefit.
- **Hold a continuous "drawing" marker and walk a continuous path** — captures organic zones but makes the polygon point-count explode.
