# ADR 0044 — Pronoun & pointer cards: subject primitives

## Status
Proposed (depends on ADR 0042, 0047 grammar).

## Context
Card events today have an implicit subject — *the holder*. `INTENT_SPEAK` raised by Anna means "Anna wants to speak". `WITNESS` raised by Anna pointing at Bob means "Anna witnesses Bob". The system infers subject from holder and (for witness) target from direction.

This collapses several distinct ideas into "the holder did X":

- **The cluster acts.** *"The four of us collectively want to pause."*
- **An invitation.** *"I want **you** to speak"* — the gesture is initiated by Anna but the action is for Bob.
- **An open call.** *"Anyone could answer this question"* — no specific subject.
- **A negation of subject.** *"No one feels this"* — collective absence.

Without explicit subject cards, none of those can be expressed. The system always assumes "the person holding the card is the actor", which is wrong about a quarter of the time.

## Decision
Reserve **8 pronoun/pointer cards**, IDs 183–190 per ADR 0042. They're `level`-mode (per ADR 0022) and *attach to the subject* of any verb-card co-raised in the same window.

| Card       | Subject of a co-raised gesture                                 |
| ---------- | -------------------------------------------------------------- |
| `I`        | Default — the holder. (Often redundant; useful when grammar disambiguation matters.) |
| `YOU`      | The person being pointed at via marker orientation (same direction inference as `WITNESS`, ADR 0027). |
| `US`       | The holder's current cluster (members within proximity threshold). |
| `THEM`     | Everyone *outside* the holder's cluster. Useful for *"they don't get it but we do"*. |
| `ANYONE`   | Open call. *"Anyone can answer"*.                              |
| `NO_ONE`   | Empty set. *"No one feels this."*                              |
| `HERE`     | The holder's current zone (per ADR 0026). *"In this zone, we've decided ___."* |
| `THERE`    | Some other zone, indicated by pointing the card.                |

Examples (paired with ADR 0023 reactions and ADR 0025 intents):

- `YOU + INTENT_SPEAK` (Anna pointing at Bob) → "I want **Bob** to speak."
- `US + COMP_SILENT` → "**Our cluster** wants silence." (Distinct from the holder personally wanting silence; the cluster context matters for the operator's judgment in ADR 0026's auto-apply path.)
- `ANYONE + INTENT_QUESTION` → "Open call — anyone can take this question."
- `NO_ONE + REACT_LIVED` → "Nobody here has lived this."

Subject composition with ADR 0043 modifiers and ADR 0046 connectors gives full grammar reach: `STRONGLY + I + INTENT_SPEAK` reads as *"I really want to speak"*; `US + AND + THEM + COMP_PAUSE` reads as *"the whole room (both clusters) wants to pause"*.

The router writes `ParticipantEvent` with a `subject` field — one of the above pronoun ids, or `holder` for the implicit default — and a `subject_target_aruco_id` when the pronoun is `YOU` and direction inference resolved it.

## Consequences

**Positive:**
- The kit gains the ability to express requests *for someone else*. The operator's queue (ADR 0025) can now distinguish "I want to speak" from "I want Bob to speak" — both are useful, very differently.
- `US` enables collective gestures without coordination. A cluster in agreement raises `US + COMP_SILENT`; a single member of a cluster doing it on behalf of the cluster is honest about the scope.
- `NO_ONE` is the cleanest way to record "nobody felt this" — better than the absence of cards, because it's an *active* statement.

**Negative:**
- Direction inference for `YOU` and `THERE` is the same machinery as `WITNESS` and inherits its noise. Mitigation: `YOU` events with `attribution_confidence < 0.6` are preserved but flagged in reports.
- Pronouns add cognitive load to the briefing. Mitigation: `I` is the default and never *needs* to be raised; pronouns are an opt-in expressive layer.

**Risks:**
- A participant raises `YOU` while looking at the camera or the wall. Mitigation: same as `WITNESS` — `YOU` resolves to the closest *person marker* in the inferred direction; non-person targets produce no event.
- `THEM` could be used divisively. Mitigation: `THEM` events are surfaced to the operator (`/admin`), not amplified on `/present`. The operator decides whether to use the moment.

## Alternatives considered
- **Implicit subject only** (current state). Functional; loses the third of gestures that aren't "I do X".
- **Subject as a free-text annotation** (the holder says aloud who they mean). Breaks the slide-deck silence; doesn't compose with the rest of the kit.
- **A bigger pronoun set** (HER, HIM, THEY, THIS, THAT, THE-OPERATOR, …). Overkill; the eight above cover the vast majority of useful subjects.
