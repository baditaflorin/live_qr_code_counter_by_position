# ADR 0021 — Participant-activable control markers (32 shared IDs)

## Status
Proposed. Foundation for ADR 0022–0030.

## Context
ADR 0011 reserved 16 dictionary IDs as **operator** commands — held-still cards, debounced, often confirmation-gated. They make the operator hands-free. They do not give the room itself any voice.

The slide deck's whole thesis is that the room is the work — *"a hundred strangers cannot become a hundred witnesses by accident"*. By Day 4 the participants are the protagonists. The system today gives them no input channel except *standing in zones*. That's binary, slow, and operator-mediated.

A second card class — printed on a different card stock, sitting on a table participants can walk past, picked up by anyone — turns the participants into co-authors of the session. They aren't waiting for the next prompt; they can *propose* the next prompt. The operator's job becomes *holding the room*; the participants' job becomes *speaking through the cards*.

These cards are not assigned to any individual. They live communally. Anyone can grab one, raise it, drop it back on the table.

## Decision
Reserve a second contiguous range of dictionary IDs — the **32 IDs immediately below the operator's 16** — as **participant cards**.

For `DICT_4X4_250` that's IDs **202–233**, leaving 0–201 for person markers and 234–249 for operator commands.

Concretely:

- A `ParticipantCard` table (`marker_aruco_id`, `name`, `kit`, `action`, `params_json`, `enabled`). Each card has a `kit` tag (one of `reaction` / `theme` / `intent` / `composition` / etc.) corresponding to ADR 0023–0026.
- `_next_aruco_id()` skips the participant range as well as the operator range.
- Detection pipeline now classifies each detected ID into one of three buckets: `person`, `operator_control`, `participant_control`. Person markers go to the existing tracker (ADR 0004). Operator markers go to `CommandRouter`. Participant markers go to a new `ParticipantRouter` with **different semantics** (see ADR 0022).
- A new admin tab "Card kits" lists every participant card with its kit, action, current enable/disable, and a printable PDF that includes both the marker *and* the card label on each face — participants need to be able to read what they're picking up.
- Every participant-card activation generates a `ParticipantEvent` row (`t`, `marker_aruco_id`, `held_by_aruco_id` if known, `kit`, `action`). This is the substrate ADR 0023–0030 build on.

## Consequences

**Positive:**
- The system gains a second user class. A workshop can be run with no operator-side input at all if the kit is well-designed — the operator just *facilitates*, the room *operates*.
- Composition. Every later "magic" feature (witness cards, theme cards, memory cards) is just a new entry in `ParticipantCard`. No new code paths.
- Audit trail. Every emergent action has a row.

**Negative:**
- Reserves 32 more IDs. With `DICT_4X4_250` that's still 80 % free for people. With `DICT_4X4_100` we're now at 48 % overhead — adoption requires defaulting to `DICT_4X4_250` (already the prod default).
- Distinct printing logistics. Participant cards need to be visually distinguishable from operator cards (ADR 0011) and from person markers (the printed PDFs already differ).

**Risks:**
- A participant carries a card off-site, brings a copy back next workshop, fires unexpected actions. Mitigation: per-workshop card-deck binding (ADR 0030) makes a card from another workshop a no-op.
- "Whoever shouts loudest with cards drives the room" — a single dominant participant could spam cards. Mitigation: per-marker rate limiting in `ParticipantRouter` and a discreet `card_disable` operator command (ADR 0014 extension).

## Alternatives considered
- **Personal card per participant.** Every attendee gets their own deck. Higher production cost; reduces the *communal* feel that makes the cards a shared instrument.
- **Phone-based input.** A web app on each phone replaces cards. Loses the physical-object quality the slide deck explicitly leans on.
- **No participant input.** Current state. Participants are objects of measurement, not authors. Sufficient for a counter, insufficient for the workshop.
