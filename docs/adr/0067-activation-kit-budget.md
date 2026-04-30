# ADR 0067 — Activation kit budget: how the 96 IDs get spent (post-grammar)

## Status
Proposed (replaces the allocation in ADR 0042; keeps that ADR's 96-ID reservation).

## Context
ADR 0042 reserved 96 participant card IDs (138–233) but allocated them across the now-deprecated grammar layer (ADRs 0042–0047). With the grammar layer gone (ADR 0061), the 96 IDs need re-allocation across the *activation kit* (ADRs 0062–0066).

The reservation itself is still right — ADRs 0023–0029 already used 37 IDs for the original "specific" cards, and the activation kit (0062–0066) needs another ~23 IDs. Together that's still well under 96, leaving room for ADR 0030 custom decks plus future expansion.

## Decision
Keep the ID range from ADR 0042 (138–233 in `DICT_4X4_250`), redistribute internally:

```
class                              IDs           count   ADR
─────────────────────────────────  ──────────    ─────   ────
reactions (atom)                   138–145       8       0023
themes                             146–153       8       0024
intents                            154–161       8       0025
compositions                       162–169       8       0026
witness                            170           1       0027
memory                             171–172       2       0028
promise                            173–174       2       0029
─────────────────────────────────  ──────────    ─────   ────
[grammar layer]                    —             0       0042–0047 (superseded; freed)
─────────────────────────────────  ──────────    ─────   ────
activation: pulse poll             175–180       6       0062
activation: reaction wave          181–188       8       0063
activation: tournament             189–190       2       0064
activation: quick-rank             191–195       5       0065
activation: idea + upvote          196–197       2       0066
─────────────────────────────────  ──────────    ─────   ────
spare / ADR 0030 custom            198–233       36      future
```

Total used: **60** of 96. Spare: **36** for the custom-deck mechanism (ADR 0030) and any future activation cards.

ADR 0021's foundation idea (reserve a contiguous range, route to a participant router) remains the spec; ADR 0042's *count* of 96 remains; only the *allocation* changes.

The `ParticipantRouter`'s detection-routing logic gets the new IDs as part of the same lookup table that already drives ADRs 0023–0029. No code-architecture change — the activation cards' fire models (pulse / level / gesture) reuse the same handler kinds the existing cards use.

## Consequences

**Positive:**
- Ambiguity removed. New contributors reading the kit definition see *one* current allocation, not the allocation + the deprecated grammar allocation.
- Spare 36 IDs absorbs the next round of activations (ADR 0030 custom decks, future fun mechanics) without another budget ADR.
- The kit description is now physically *printable*: 60 distinct cards on a single PDF, organised by class. ADR 0011's printable-PDF affordance just needs to enumerate the new allocation.

**Negative:**
- One more lifecycle change to ADRs 0021 and 0042 to track per ADR 0041. Mitigation: the change is small — a single status update to ADR 0042 already applied.

**Risks:**
- Existing prod databases with markers in IDs 175+ (the ones the grammar layer would have used) silently break under the new meaning. Mitigation: no prod has shipped any of 0042–0047, so there is nothing to break. Future-proof: `ParticipantCard.kit` is the source of truth for any active deployment; reseed via ADR 0030 if needed.
- The activation kit could grow past 23 IDs as ADRs 0062–0066 accrete details. Mitigation: 36 spare IDs cushion expansion; if the activation kit ever exceeds 36+23 = 59 the budget is revisited.

## Alternatives considered
- **Re-number the activation cards into the freed grammar slots** (175–197 below). Done — that's the allocation above. Conserves contiguity.
- **Leave the grammar slots empty as a memorial.** Wastes 23 IDs for sentimentality.
- **Compress all activation cards into 16 IDs.** Would force trimming reaction emojis or quick-rank levels; not worth the friction.

## Postscript
ADR 0042's *budget* was right; its *allocation* was wrong. The mechanical separation of "how many slots" from "what goes in them" is what made the cleanup cheap — flip the allocation table, the rest of the system doesn't notice.
