# ADR 0022 — Card-handling semantics for many-hands input

## Status
Proposed (depends on ADR 0021).

## Context
Operator cards (ADR 0014) work with a **hold-still ≥ 1.5 s** gate, debounced, often confirm-gated for destructive actions. That model assumes a single, careful actor: the operator deliberately raises a card, the system deliberately fires.

Participant cards are different in every dimension:

- **Plurality.** Twenty hands raising twenty cards simultaneously is the normal case, not the exception.
- **Speed.** A participant raises a "Yes" reaction for a few seconds, then drops it. A 1.5-second gate would miss most of these.
- **Position.** A reaction card is held in front of the participant's chest; their head marker is also in frame. The system must know *who* raised the card.
- **Repetition.** The same card raised twice in 30 seconds is two distinct events, not a single debounced one.
- **Composition.** Two cards held simultaneously by the same person (e.g. *theme: TRUST* + *intent: speak*) is meaningful — and different from the two cards held by two different people.

A naive single-actor debounce model would either drop most participant inputs or fire constant duplicates.

## Decision
A separate `ParticipantRouter` (introduced in ADR 0021) with **distinct triggering semantics** from `CommandRouter`:

- **Activation gate**: a participant card is "active" while it is detected for ≥ 0.4 s out of any sliding 0.6 s window. Faster than operator (1.5 s), but enough to filter momentary detection errors.
- **Holder attribution**: when a participant card activates, the router associates it with the nearest detected *person marker* whose floor-position is within 0.8 m. If no person marker is nearby, the event is recorded as anonymous (some cards are intentionally pickable without identity — see ADR 0030 for the `anonymous_ok` flag per card).
- **Fire model**: each card has one of three fire models in its row in `ParticipantCard.params_json`:
  - `pulse` — fires once on activation, once on deactivation. (Reactions, intents.)
  - `level` — broadcasts continuous "active" status while held. (Composition modifiers like *silent* — true while raised, off when lowered.)
  - `gesture` — fires a single event after a card is raised and lowered within 5 s. (Promise, memory.)
- **Per-marker rate limit**: a single physical card cannot fire more than once per 1.5 s, even with multiple holders. Prevents marker-flicker from registering as two distinct events.
- **Per-participant rate limit**: a single attributed person can not fire more than 6 events per minute across all cards. Prevents griefing or accidental dominance.
- **Co-occurrence window**: cards raised by the *same person* within 1 s of each other are bundled into one composite event with multiple `cards: [...]`. ADR 0023+ feature combinations rely on this (e.g. *theme + intent* = "I want to speak about TRUST").

Every event is written to `ParticipantEvent` with `attribution_confidence` (0..1) so reports can filter for high-confidence-only.

## Consequences

**Positive:**
- The router scales to "20 hands raised at once" without losing events.
- Holder attribution gives the data narrative power: the report can say "Anna raised the *grief* card three times during Block 4", not just "the *grief* card was raised three times".
- Composition (theme + intent) becomes natural without each combination needing its own card.

**Negative:**
- More state in the router; more tests.
- Attribution is wrong some of the time (two people standing close, one card). Mitigation: confidence scoring; reports default to >0.7 confidence.

**Risks:**
- A card on a table that flickers in and out of detection (reflective surface, bad lighting) fires repeatedly. Mitigation: the per-marker rate limit caps this regardless of detection noise.
- A clever participant gaming the rate limits across multiple cards. Mitigation: per-person rate limit closes that hole; harder still: per-second router throughput cap.

## Alternatives considered
- **Reuse operator semantics**. Misses most participant gestures.
- **Continuous per-frame events**. Drowns reports in noise; makes pulse/gesture/level distinction impossible.
- **Per-card custom semantics**. Tempting but every card needing to define its own debounce becomes unmaintainable. Three fire models is the compromise.
