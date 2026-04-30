# ADR 0014 — Marker-driven session control

## Status
Proposed (depends on ADR 0011).

## Context
During a 90-minute exercise the operator must:

- Start tracking ([`/track`](../../frontend/track.html)).
- Step through the deck question by question (`Next ›` / `‹ Prev` on Live).
- Snapshot the current room state when an interesting cluster forms (`Record snapshot`).
- Stop tracking at the end.

Every one of these is a click on a laptop currently on the gallery. The slide deck (`SLIDE 18 · FACILITATOR CUES`) explicitly emphasises **silence and stillness** — the operator's job is to hold the room, not type. Cards are the obvious surface: the facilitator already carries the deck of statements; one extra deck of "control cards" is invisible to participants.

## Decision
Reserve six control-marker ids (per ADR 0011) — each printed onto a credit-card-sized placard — for the high-frequency operator gestures:

| Card                | Action                                              |
| ------------------- | --------------------------------------------------- |
| `TRACK_START`       | Begin a tracking session (default settings)         |
| `TRACK_STOP`        | End the active tracking session                     |
| `Q_NEXT`            | Activate the next question in the current block     |
| `Q_PREV`            | Activate the previous question                      |
| `Q_SNAPSHOT`        | Record a vote snapshot for the active question      |
| `RESET`             | Clear current detections (advance round)            |

A card fires when it is **detected and held still for ≥1.5 seconds** (debounced to one fire per visible-window). Visible-window means: once it fires, it can't fire again until the marker has *left* the frame for ≥0.5 s.

When a card fires, the live overlay flashes a 2-second banner ("⏺ Recording started", "✓ Snapshot saved", etc.) so the operator gets unmistakable confirmation. Destructive actions (`TRACK_STOP`, `RESET`) require a **second confirmation card** held within 5 seconds — a deliberate two-card move that's hard to do accidentally.

## Consequences

**Positive:**
- Operator is hands-free during the exercise. No need to glance at the laptop; the cards are part of their toolkit.
- Card-based control composes naturally with the existing API — every card maps to an HTTP endpoint that already exists. Adding a card is just wiring `CommandRouter` (ADR 0011) to the right call.
- Cards can be brought to a venue without the operator's laptop being on stage.

**Negative:**
- Six more reserved ids (16 total reserved across all marker-control ADRs is comfortable inside DICT_4X4_250).
- The dwell-and-confirm gate adds a slight delay; an operator pressing a button on the laptop is faster.

**Risks:**
- Workshop participants spotting and copying a control marker. Mitigation: reserved ids are printed on an obviously-different card stock and kept in the operator's pocket; the confirmation step on destructive actions stops the worst outcomes anyway.
- Latency: from "I want to next-question" to "the room sees the next question on /present" is now ≥1.5 s (dwell) + WS round-trip. Acceptable since the operator's pacing is already on a multi-second cadence.
- A card held stationary against the operator's body for too long fires repeatedly. Mitigation: visible-window gate.

## Alternatives considered
- **Bluetooth presenter remote** — adds device pairing, batteries, range issues; one more thing to charge.
- **Voice control** — fragile in a hall full of people talking.
- **Foot pedal / hardware button** — works but adds bespoke hardware to ship to every venue.
- **Phone app for the operator** — fine, but the operator's phone is often not in their hand mid-exercise.
