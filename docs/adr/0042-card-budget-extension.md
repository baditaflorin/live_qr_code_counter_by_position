# ADR 0042 — Participant card budget extension: 32 → 96 reserved IDs

## Status
**Superseded by ADR 0061.** The budget extension *is* still useful (we genuinely need more than 32 IDs); ADR 0067 keeps the 96-ID reservation but spends it on fun activation cards instead of grammar primitives.

## Context
ADR 0021 reserved **32 IDs** (202–233 in `DICT_4X4_250`) for participant cards. By the time ADRs 0023–0029 were written, the actual demand was already over budget:

| ADR        | Cards | Class                       |
| ---------- | ----- | --------------------------- |
| 0023       | 8     | reactions                   |
| 0024       | 8     | themes                      |
| 0025       | 8     | intents                     |
| 0026       | 8     | compositions                |
| 0027       | 1     | witness                     |
| 0028       | 2     | memory (`KEEP`, `PUBLIC`)   |
| 0029       | 2     | promise (`PROMISE`, `SHARED`)|
| **Total**  | **37**| → already 5 over            |

ADRs 0043–0047 (modifiers, pronouns, quantity, connectors, grammar) propose another **32 primitive cards**. Total demand is **69**. The 32-ID ceiling can't carry the kit.

There's no scarcity: `DICT_4X4_250` has 250 IDs total. Operator commands need 16 (ADR 0011). Person markers were sized for "≥100 people"; the prod default is `DICT_4X4_250` so the floor is 200+. We have room.

## Decision
Reserve a contiguous range of **96 IDs** for participant cards. Concretely, in `DICT_4X4_250`:

```
ID range          Reserved for                Count
────────────────  ──────────────────────────  ─────
0–137             person markers              138
138–233           participant cards           96     ← was 202–233 (32)
234–249           operator control markers    16
```

138 person IDs comfortably covers the planned 100-person workshops (ADR 0039 destination) with headroom for cohort growth. If a workshop ever sells past 138 attendees, that's a separate problem (`DICT_4X4_1000` becomes the right default).

Inside the 96 participant slots, allocate by class:

```
class                    range       cards   ADR
───────────────────────  ──────────  ──────  ────
reactions                138–145     8       0023
themes                   146–153     8       0024
intents                  154–161     8       0025
compositions             162–169     8       0026
witness                  170         1       0027
memory                   171–172     2       0028
promise                  173–174     2       0029
modifiers                175–182     8       0043 (new)
pronouns                 183–190     8       0044 (new)
quantities               191–198     8       0045 (new)
connectors               199–206     8       0046 (new)
spare / operator-defined 207–233     27      future expansion + ADR 0030 custom
```

Total used: **69** of 96. Spare: **27** for the custom-deck mechanism (ADR 0030) and future ADRs without further budget changes.

The reservation is enforced in `_next_aruco_id()` (already skipping the operator range; extend to skip 138–233). Existing markers in the 138–201 range — there shouldn't be any in production, but if a dev DB has them — get an explicit migration that emits warnings but doesn't auto-renumber (re-numbering invalidates printed cards).

## Consequences

**Positive:**
- The grammar layer (ADRs 0043–0047) becomes implementable without further negotiation.
- Spare 27 IDs absorbs the next round of expansion (custom decks, workshop-specific cards) without another budget ADR.
- Person-marker capacity stays well above the 100-person workshop target.

**Negative:**
- Reduces person-marker capacity from 202 to 138. Acceptable per ADR 0039's destination (workshops cap at ~100 attendees).
- One more lifecycle change for ADR 0011 / 0021 to track per ADR 0041.

**Risks:**
- A dev DB with markers numbered ≥138 silently breaks. Mitigation: the migration emits a clear "marker #N is now in the participant range, will not detect as a person" warning at startup.
- A future ADR claims it needs more than the 27 spare. Mitigation: if it does, write *that* ADR; the budget is bookkeeping, not theology.

## Alternatives considered
- **Stay at 32 and trim each class.** Forces ugly tradeoffs (do we drop tender reactions or theme cards?) without any underlying need.
- **Reserve 128 (half the dictionary).** Wasteful — leaves only 106 person markers, undermines the "100-person workshop" destination.
- **Use a second dictionary for participant cards.** Doubles detector cost and conflicts with the printable-on-one-PDF property of the kit.
