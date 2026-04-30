# ADR 0043 — Modifier cards: qualifier primitives

## Status
Proposed (depends on ADR 0021 foundation, ADR 0042 budget, ADR 0047 grammar).

## Context
Reaction cards (ADR 0023) carry their qualifier baked in. `REACT_TENDER` already means *"this is hard for me"*. `REACT_LIVED` already means *"I have lived this"*. That's expressive at the cost of *combinatorial explosion*: every shade of "yes" wants its own card — `YES_STRONGLY`, `YES_BARELY`, `YES_AGAIN`, `YES_NOT_QUITE`. Pretty soon the kit has 80 cards and the participant can't find any of them.

The Lego analogy that this ADR series is built on offers a way out: keep the *atom* cards (`YES`, `NO`, `TENDER`) and add a small set of **modifier cards** that change the meaning of any atom raised in the same gesture-window.

`STRONGLY` + `YES` reads as "strongly yes". `STRONGLY` + `TENDER` reads as "this is *very* hard for me". `STRONGLY` + `NO` reads as "definitely no". One modifier, three new shades — without three new cards.

## Decision
Reserve **8 modifier cards**, IDs 175–182 per ADR 0042. All `level`-mode (per ADR 0022) — they're "active" while held — and they propagate to whichever atom card the same person co-raises within the 1-second co-occurrence window.

| Card        | Effect on a co-raised atom                                           |
| ----------- | -------------------------------------------------------------------- |
| `STRONGLY`  | Intensifies. `STRONGLY + YES` → `yes:strong`.                        |
| `BARELY`    | Weakens. `BARELY + YES` → `yes:weak`.                                |
| `NOT`       | Negates. `NOT + TENDER` → `not_tender`. `NOT + YES` → `no` (with provenance noting the holder used `NOT + YES`, not raw `NO` — sometimes the difference matters in reports). |
| `MAYBE`     | Hedges. `MAYBE + YES` → `yes:tentative`.                             |
| `AS_IF`     | Marks as performative / hypothetical. `AS_IF + ANGRY` → "playing angry, not actually". Useful when the workshop has a role-play element. |
| `STILL`     | Persists meaning across rounds. `STILL + TENDER` records that the participant *is still* in tender state, not just transiently. |
| `AGAIN`     | Repeats the previous gesture. `AGAIN` alone re-fires the holder's most recent atom card from <30 s ago. |
| `ALMOST`    | Near-miss. `ALMOST + YES` → `yes:almost-but-no`. The deliberately-edge state.|

Modifiers compose (per ADR 0047): `NOT + STRONGLY + YES` reads as "not strongly yes" (i.e., a soft yes), distinct from `NOT + YES` ("no").

The router writes `ParticipantEvent` with a `modifier_chain: ["strongly", "not"]` field, plus the atom. Reports (and reflection cards, ADR 0017) read the chain as a phrase rather than a single label.

## Consequences

**Positive:**
- The kit gains expressive range without growing card count.
- `AGAIN` is a small but powerful primitive — re-raising the same gesture is a common participant act and previously required holding the original card a second time.
- `NOT` makes negation cheap. The opposite of any card is the same card with NOT held.

**Negative:**
- Composition introduces ambiguity: `BARELY + STRONGLY + YES` is contradictory; how does the system parse it? Mitigation: ADR 0047's grammar declares right-to-left precedence and emits a `parse_warning` for contradictions, preserving the raw card list verbatim so the operator can review.
- One more class of card to brief participants on. Mitigation: modifiers are *optional* — every gesture without them still works exactly as it does now.

**Risks:**
- A participant raises `NOT` alone with no atom in the window. Empty negation. Mitigation: solo modifiers are recorded with `solo: true` and treated as "the participant intended to negate something but the system didn't catch the atom"; the audit log captures it for review.
- `STILL` persists meaning indefinitely. Mitigation: `STILL` decays after 5 minutes if not re-asserted.

## Alternatives considered
- **Spelling every modifier into a dedicated atom** (`YES_STRONGLY` etc.). Combinatorial explosion; scales poorly.
- **Modifiers as gestures** (rotate the card 90° to mean "strongly"). ArUco rotation is detectable but unreliable from the gallery; harder to brief.
- **No modifiers; participants accept binary expression.** Loses most of the "yes-but" channel that ADR 0023 was designed for.
