# ADR 0025 — Intent cards (8 of the 32 participant IDs)

## Status
Proposed (depends on ADR 0021, 0022).

## Context
The operator's role in the slide deck is to *pick the outlier* — to "hand them the moment". That's gatekeeping by design: the operator chooses who speaks, when, and why. The room has no formal way to *propose* itself — to say "I want to speak", "I want to listen to that person", "I want to leave the room and come back".

In a 100-person workshop, a hand raised in a sea of people is invisible from the gallery. By the time the operator notices, the moment has passed.

A small set of intent cards turns each participant's wish into a *queryable queue* — a subtle backchannel between the room and the operator. The participant raises a card; their request appears in the operator's console and on the projection (with their name muted by default).

## Decision
Reserve **8 participant card IDs** (per ADR 0021) for intent cards, all `gesture`-mode (per ADR 0022) — raised, lowered, fired once.

| Card                | Intent                                                         |
| ------------------- | -------------------------------------------------------------- |
| `INTENT_SPEAK`      | "I have something to say about this question"                  |
| `INTENT_LISTEN`     | "I want to be paired with someone to hear them"                |
| `INTENT_PAIR`       | "I want a partner for the next exercise"                       |
| `INTENT_PAUSE`      | "I need a moment" (room slows; whispered to operator)          |
| `INTENT_QUESTION`   | "I have a question for the room"                               |
| `INTENT_WITNESS`    | "I want to be a witness for someone else's moment"             |
| `INTENT_REST`       | "I'm stepping out — please don't pick me"                      |
| `INTENT_OFFER`      | "I have something to offer the room" (for the *Vulnerable Act*)|

Intents are written to `ParticipantEvent` and surfaced two ways:

- **`/admin` queue.** A new "Room queue" panel that shows pending intents, ordered by raise-time, oldest first. Operator can dismiss, acknowledge, or pick from the queue. Picking from the queue is the analog of the slide-deck *"we hand them the moment"* — only now the room itself is suggesting candidates.
- **`/present` whisper.** Discreet 1-line ticker in the bottom-right showing the count of pending intents (no names). The operator alone knows who's in the queue; the room sees only "3 intents pending".

`INTENT_PAUSE` is special-cased: it triggers an immediate operator audible cue (ADR 0016) and adds a yellow border on `/present`. It is the room's equivalent of the operator's "don't rush a vulnerable round into a light one" cue from slide 18.

`INTENT_REST` is anti-pickable: while the card is held, the holder's marker is excluded from the outlier-pick list. A way to opt out without leaving.

## Consequences

**Positive:**
- The operator's outlier-pick changes from *guess* to *informed*. The room can volunteer.
- Quiet participants gain a non-verbal channel to enter the conversation.
- `INTENT_REST` is the most important: it formalises consent. The body language for "pick someone else" is subtle and easy to miss; a card makes it unambiguous.

**Negative:**
- The room queue is one more thing the operator monitors. Mitigation: intents are surfaced as count-only on `/present` and as full list only on `/admin`; the operator can ignore the queue if a question's flow is working without it.
- Intents create a kind of "social hierarchy of requests" — first-in line gets picked. Mitigation: the queue is a *suggestion*, not a contract; the operator can pick anyone, including those not in the queue.

**Risks:**
- A participant raising `SPEAK` is then ignored — felt as a slight. Mitigation: `/admin` records when an intent is acknowledged but not picked, and the reflection card (ADR 0017) thanks them with a "you offered to speak — your offer was heard."
- `INTENT_PAUSE` abused. Mitigation: per-person rate limit (ADR 0022) caps it at 6 per minute; multiple `PAUSE` raises within 30 s collapse into one event.

## Alternatives considered
- **Hand-raise detection in vision pipeline** — possible, fragile in a crowded hall, no opt-out.
- **Phone-based queue** — cleaner UX, breaks the physical-card cohesion of the kit.
- **No queue** — operator picks blind. Works at small scale, breaks at 100 people.
