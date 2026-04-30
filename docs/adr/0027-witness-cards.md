# ADR 0027 — Witness cards: directional "I see you"

## Status
Proposed (depends on ADR 0021, 0022, optionally 0023's `REACT_AMEN`).

## Context
The slide deck calls participants "witnesses" — *"a hundred strangers cannot become a hundred witnesses by accident"*. The whole arc is from *seeing* to *being seen*. But the data layer today knows nothing about who *witnessed* whom. We know who stood next to whom (proximity), who clustered with whom (also proximity), but not who *acknowledged* whom.

A witness gesture is intentional: turning toward someone, raising a card while looking at them, holding it for a beat, putting it down. It's deliberate in a way that proximity isn't.

ArUco markers carry orientation in their detected corner ordering. With a per-camera homography (ADR 0003) we can convert that orientation to a *facing direction in the floor plane*. Combine the two — a held card with a known facing direction — and we can identify the *target* of a witness gesture: the closest other person in the direction the card-holder is pointing.

## Decision
Add a single witness card ID — `WITNESS` — to the participant deck, gesture-mode (per ADR 0022).

The semantics:

1. Participant raises the `WITNESS` card while standing close to and facing another participant. The card has a small directional arrow on its face; participants are briefed to "point the arrow at whoever you're seeing".
2. While the card is detected:
   - **Holder identification**: the nearest person marker (within 0.8 m) is the witness's holder.
   - **Target identification**: along the card's "pointing" axis (computed from the marker's corner orientation projected through the camera homography), the closest other person marker within a 60° cone, ≤ 3 m, is the target.
   - The gesture must be sustained for ≥ 0.7 s for both holder and target to lock in.
3. On lower (gesture complete), a `WitnessEvent` row is written: `(t, witness_aruco_id, target_aruco_id, confidence)`.

Reports gain a "witness graph": who saw whom, weighted by gesture count. Two derivative artifacts:

- **`/project` halo.** When a witness gesture completes, both holder and target glow briefly on the projection — a visual handshake.
- **Per-person reflection card** (ADR 0017) gains: *"You were seen by 47 people. You witnessed 31."*
- **Day 5 closing reel** (ADR 0019): "the most-witnessed person in the room", "the person who witnessed the most people". Pairs of mutual witnesses get a special highlight.

## Consequences

**Positive:**
- The system gains a layer the slide deck explicitly asks for: not just *position*, but *acknowledgment*.
- Mutual witness is the core artifact of the workshop; making it data makes it visible in the closing reel and in personal reflections.
- The witness graph is a beautiful object — a sociogram authored by the room itself.

**Negative:**
- Direction inference from a marker held by a person is noisier than direction inference from a stationary marker. Confidence scores will be lower. Mitigation: confidence-weighted reports; default to >0.6 confidence for the per-person card.
- One more gesture for participants to learn. Mitigation: the card is the most explained in the briefing — "this is the one card you'll come back to."

**Risks:**
- A participant uses the card playfully ("witnessing" the wall, the camera, the operator). Mitigation: target must be a person marker; non-person targets just produce no event.
- Privacy of the witness graph. Knowing *who saw whom* is sensitive. Mitigation: the graph is operator-only by default; per-person cards anonymize "you witnessed 31 people" without naming them; opt-in to share names.

## Alternatives considered
- **Treat proximity as witnessing.** Loses intent — proximity is involuntary; witnessing is chosen.
- **A "you saw me" reciprocity card.** Adds complexity for marginal gain — mutuality already emerges from two people each raising `WITNESS` toward each other.
- **No witness layer.** Sufficient for the counter; insufficient for what the slide deck describes the workshop *as*.
