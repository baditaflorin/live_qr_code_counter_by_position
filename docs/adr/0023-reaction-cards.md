# ADR 0023 — Reaction cards (8 of the 32 participant IDs)

## Status
Proposed (depends on ADR 0021, 0022).

## Context
The basic gesture in this workshop is *standing on a side*. It's powerful — *the body answers before the mouth does* (slide 4) — but it's binary, slow, and forces every participant to choose the dominant axis the question proposes.

The participant who agrees with the statement *and yet holds a reservation* has no channel. The participant who has lived something the room hasn't named yet has no channel. The slide deck pre-empts this for the operator (the outlier moment, the hinge) but not for the room itself.

Eight printed reaction cards give every participant a side channel — a way to register "yes-but-uncertain", "no-but-painfully", "I have lived this thing", "I see you doing the work" — without breaking the formation they are standing in.

## Decision
Reserve **8 participant card IDs** (per ADR 0021) for reaction cards. Each is `pulse`-mode (per ADR 0022) — fires once when raised, once when lowered.

| Card             | Means                                                              | Where it shows                                |
| ---------------- | ------------------------------------------------------------------ | --------------------------------------------- |
| `REACT_YES`      | Affirm — "this is true for me"                                     | Live count badge next to the question         |
| `REACT_NO`       | Reject — "this is not true for me"                                 | Live count badge                              |
| `REACT_UNSURE`   | "I don't know yet"                                                 | Surfaced in `/admin` for outlier-picking      |
| `REACT_PASS`     | "I want to skip this one"                                          | Counted but excluded from snapshot tallies    |
| `REACT_TENDER`   | "This is hard to answer"                                           | Whispered to operator; not shown to room      |
| `REACT_LIVED`    | "I have lived this; ask me later"                                  | Queued in the post-question outlier list      |
| `REACT_AMEN`     | "I see you" (when raised toward another participant)               | Visible in `/project` as a glow toward target |
| `REACT_DOUBT`    | "I want to push back on this question"                             | Surfaces "the room wants to question this"    |

`REACT_AMEN` cross-references ADR 0027 (witness pairing). Other cards stand alone.

Aggregate counts per question are stored on the snapshot, alongside the zone counts. Reflection cards (ADR 0017) draw from this data: "you raised *TENDER* three times — those questions are noted."

## Consequences

**Positive:**
- The dominant axis of any question stops being the only thing the room can say. The "yes-but" answer finally has a place.
- The operator's **outlier moment** (slide 9) gains depth — instead of guessing who to invite, they pick from the people who raised `LIVED` or `TENDER`.
- `TENDER` is privately surfaced — a discreet way for someone to flag a hard question without standing out.

**Negative:**
- Eight new cards to print, label, and brief participants on. Mitigation: a pre-workshop briefing slide explains them in 60 seconds; the cards have human-readable labels.

**Risks:**
- Performance bias — participants who know the cards exist may feel pressure to raise one. Mitigation: cards are explicitly *optional*; the briefing emphasizes that *standing in a zone* is still the primary signal.
- `TENDER` privacy. The card's existence is visible to the room (someone is holding it) even if the count isn't. Mitigation: the card design is small and discreet; the operator is trained to receive it without acknowledgement.

## Alternatives considered
- **Coloured wristbands** — physical, simpler, but cannot be picked up or put down round to round.
- **Phone-based reactions** — same data, loses the held-up-on-the-floor visual signal that the rest of the room can read.
- **Just more zones** — works for the formal axes; doesn't help the *yes-but* shading the cards capture.
