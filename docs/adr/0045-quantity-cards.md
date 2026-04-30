# ADR 0045 — Quantity cards: numeric primitives

## Status
Proposed (depends on ADR 0042, 0047 grammar).

## Context
The slide deck includes questions whose answer is *a number* — *"how much sleep did you get this week?"*, *"how nervous are you?"*. Today the system maps these to a 5-stripe line formation, which forces a continuous answer into 5 buckets and gives the operator no way to ask *"on a scale of 1–10, how nervous?"* without redrawing zones.

It also includes questions whose answer is *a count* of something — *"how many people in this room would you call at three in the morning?"*. The current kit has no clean way to record an integer.

A small set of quantity cards — *0, 1, 2, 3, 5, 10*, plus *all/none/more/less* — turns the participant card kit into something that can answer numeric questions natively. Pair the question with a `QUANTITY` request, the room raises numbers, the system aggregates.

## Decision
Reserve **8 quantity cards**, IDs 191–198 per ADR 0042. All `pulse`-mode (per ADR 0022).

| Card    | Value when raised                                             |
| ------- | ------------------------------------------------------------- |
| `Q_0`   | Zero. *"I haven't done X."*                                   |
| `Q_1`   | One.                                                          |
| `Q_2`   | Two.                                                          |
| `Q_3`   | Three.                                                        |
| `Q_5`   | Five.                                                         |
| `Q_10`  | Ten.                                                          |
| `Q_ALL` | "Everyone / everything / total". Composes with `OF + US` to mean "all of us". |
| `Q_NONE`| "Nobody / nothing".                                           |

Composition (per ADR 0047) gives the rest:

- `Q_3 + Q_2` raised together → 5 (sum semantics for non-conflicting numerals).
- `Q_5 + AGAIN` (ADR 0043 modifier) → "five, again" → 10. (Or *"five, and another five"*, depending on intent. The grammar logs the raw cards and the inferred number.)
- `MORE + Q_5` → "more than five".
- `LESS + Q_3` → "less than three".

The intermediate range (4, 6, 7, 8, 9) is reachable by composition: 5+1, 5+2, 5+5−1+1 — though in practice the kit's resolution is built around the round numbers people *think* in. For any answer requiring sub-integer precision, the operator should use a 10-stripe line formation instead.

Two surfaces:

- **Numeric questions.** A `Question.numeric: true` flag makes the active question expect a quantity answer instead of a zone answer. `/present` shows a histogram of raised numbers in real time. Snapshots record the participant's number, not their zone.
- **Quantitative gestures elsewhere.** `Q_5 + INTENT_PAIR` reads as *"I want to pair with five people across the workshop"* — a structured multi-pair request. The operator's queue (ADR 0025) shows pairing intents grouped by quantity.

## Consequences

**Positive:**
- The kit answers numeric questions natively. The line formation stops being the only way to say "more or less".
- Reflection cards (ADR 0017) gain quantitative facts: *"You answered '3' to three questions and '10' to one."*
- The quantity primitive is a building block — pair it with composition cards and modifiers and most workshop-relevant numeric questions become expressible.

**Negative:**
- Eight more cards in a kit that's already at 60+. Mitigation: numeric questions are an *opt-in* mode per question; workshops that don't ask quantitative questions never need to introduce these cards to the room.
- Composition arithmetic (`Q_3 + Q_2`) is non-obvious to participants. Mitigation: the briefing covers single-card answers; multi-card sums are an advanced behaviour the system *accepts* but doesn't *require*.

**Risks:**
- A participant misunderstands the kit and raises `Q_5` for "I'm somewhat in the middle on a 10-point scale". The data is wrong. Mitigation: numeric questions on `/present` show the visible histogram so the participant can see how their answer compares; obvious confusion gets flagged.
- `Q_ALL` is ambiguous without context (all of *what?*). Mitigation: `Q_ALL` requires a co-raised pronoun (`Q_ALL + US`, `Q_ALL + THEM`) to fire; solo `Q_ALL` is recorded as `solo: true` with a parse warning per ADR 0043.

## Alternatives considered
- **Don't add quantity primitives** — push numeric questions through the line formation. The line gives 5 buckets; that's the resolution we're stuck with.
- **One card per number 0–10** (eleven cards). Brittle (which numbers? what about 17?) and uses too much budget.
- **Raised fingers on the marker hand, computer-vision counts.** Possible, fragile, and conflates "I'm raising my hand" with "I have an answer".
