# ADR 0046 — Connector cards: logical primitives

## Status
Proposed (depends on ADR 0042, 0047 grammar).

## Context
ADRs 0043–0045 introduce *qualifier*, *subject*, and *quantity* primitives. Each modifies a single atom card. To say more — *"I am tender **and** I want to speak"*, *"yes **but** also unsure"*, *"speak now **or** never"* — the kit needs the connectives that join clauses.

Without connectors, two simultaneous gestures get bundled into one ambiguous compound event. Did the participant mean "I'm tender *and* I want to speak"? Or "I'm tender *but* still want to speak"? Or "I'm tender, *therefore* I want to speak"? The room is making three distinct claims; the system records one.

The slide deck explicitly leans on this nuance — its language is full of *and*, *but*, *because*. The kit should support it.

## Decision
Reserve **8 connector cards**, IDs 199–206 per ADR 0042. All `level`-mode (per ADR 0022) — the connector is "in effect" while held.

| Card           | Means in a multi-card sentence                                        |
| -------------- | --------------------------------------------------------------------- |
| `AND`          | Both clauses apply. *"Tender AND want-to-speak"* → both true.         |
| `OR`           | Either clause. *"Speak OR listen"* → flexible request.                 |
| `BUT`          | Concession. *"Yes BUT tender"* → yes is qualified; tender is the more salient state. |
| `BECAUSE`      | Causal. *"Tender BECAUSE lived"* → the second clause causes the first. |
| `IF`           | Conditional. *"Speak IF asked"* → don't pick me unless invited.       |
| `INSTEAD_OF`   | Substitution. *"Listen INSTEAD-OF speak"* → reverse the previous request. |
| `WITH`         | Co-actor. *"Pair WITH them"* (`WITH + YOU`) → pair with a specific person. |
| `WITHOUT`      | Excluded actor. *"Pair WITHOUT them"* → a request with an exclusion. |

Composition (per ADR 0047): connectors form a tree. `I + WANT + SPEAK + BUT + I + AM + TENDER` parses as a binary tree with `BUT` at the root and two clauses below. The router records the parse plus the raw card list, so an operator can review the source if the parse misreads.

`BECAUSE` is the most expressively powerful — it makes the *reason* part of the data. *"Anna raised TENDER + BECAUSE + LIVED"* tells the operator something the count of `TENDER` raises alone doesn't: the source is lived experience, not a hard question.

`IF` is the most operator-useful. *"INTENT_SPEAK + IF + ASKED"* (with `IF + ASKED` standing in for "if you want me to") becomes a *conditional* entry in the operator's queue — flagged as "available, not pushing". The operator's outlier-pick can prefer or avoid conditional offers based on the room state.

## Consequences

**Positive:**
- The kit becomes *linguistically complete enough* — the four primitive layers (qualifier / subject / quantity / connector) plus atoms cover the vast majority of expressions a workshop needs.
- `BECAUSE` and `IF` are particularly valuable for the slide-deck's *outlier moment* — an operator can pick "the participant who said `INTENT_SPEAK BECAUSE LIVED`" with much higher confidence than "anyone who raised `INTENT_SPEAK`".
- Reports gain narrative quality. *"Five participants raised `TENDER BECAUSE GRIEF`"* is a sentence; *"5 raises of TENDER"* is a number.

**Negative:**
- Multi-card sentences are slow to compose (the participant has to find and raise multiple cards). Mitigation: most workshops use single-atom cards 95 % of the time; connectors are the affordance for the 5 % of moments where nuance matters.
- Parse ambiguity grows with sentence complexity. Mitigation: ADR 0047 caps sentences at 5 cards and emits a parse warning when ambiguity exceeds a threshold.

**Risks:**
- Participants over-compose because *the option exists*. The room becomes a syntax exercise rather than a workshop. Mitigation: the briefing emphasises that connectors are *available, not expected*; the audit log of average-cards-per-sentence is a vibe metric the operator monitors.
- `WITHOUT` could be used to single out a specific person to exclude. Mitigation: `WITHOUT + YOU` events are operator-private and flagged for review per ADR 0009.

## Alternatives considered
- **Connectors as gestures** (raise two cards in sequence, second raise within 0.5 s = `AND`; lift second card before lowering first = `BUT`). Cleaner card budget; very hard to brief.
- **Restrict to AND/OR only** (the bare minimum). Loses `BECAUSE` and `IF` which are the most operator-useful.
- **No connectors; single-clause only.** Forces every nuance into atom cards, defeating the grammar approach this ADR series is built on.
