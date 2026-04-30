# ADR 0026 — Composition cards (8 of the 32 participant IDs)

## Status
Proposed (depends on ADR 0021, 0022).

## Context
The slide deck describes four formations (line, matrix, two-camps, circle) and three rhythms (4-minute round, the privilege walk, the four corners). The forms are fixed, decided in advance, executed by the operator.

But powerful workshop moments often come from *constraints applied mid-round*: "for this question, eyes closed"; "for this question, back to back". Those changes happen verbally, depend on the operator remembering to say them, and have no record in the data — so the report cannot say *"the question with eyes closed clustered the room more tightly"*.

A small kit of physical composition cards lets *anyone* propose a constraint for the next round. The participant raises a `EYES_CLOSED` card; the operator sees it on `/admin`; if accepted, the constraint is logged on the next snapshot.

## Decision
Reserve **8 participant card IDs** (per ADR 0021) for composition / modifier cards. All `level`-mode (per ADR 0022) — the constraint is "in effect" while held, and recorded as such on the active snapshot.

| Card                  | Constraint                                                            |
| --------------------- | --------------------------------------------------------------------- |
| `COMP_SILENT`         | Next round: silence — no speaking after the question is read          |
| `COMP_EYES_CLOSED`    | Next round: eyes closed when standing in the formation                |
| `COMP_BACK_TO_BACK`   | Next round: pair off, back to back — formations of 2                  |
| `COMP_OPPOSITE`       | Next round: stand with someone you disagree with                      |
| `COMP_SLOW`           | Next round: move slowly — minimum 30 s for the formation to settle     |
| `COMP_HOLD_HANDS`     | Next round: hold the hand of whoever you end up next to               |
| `COMP_MIRROR`         | Next round: mirror the closest person's posture                       |
| `COMP_SWITCH`         | Next round: at the 1-minute mark, swap with someone in another zone   |

Two activation modes:

- **Operator-accepted.** The constraint card is raised; an `INTENT_QUESTION`-like event surfaces in `/admin` saying "the room wants `COMP_SILENT` next round". The operator either dismisses it or activates it (a single click, or a confirmation card). On activation, the constraint is bound to the next snapshot/question and rendered visibly on `/present` ("This round: silent").
- **Auto-applied** (configurable per-deck, default off). If ≥ N (default 5) participants raise the same composition card simultaneously, the system applies the constraint without operator gate. The room votes itself into a constraint. This is the most emergent affordance the kit produces.

Constraint state is stored on the next-active snapshot: `Snapshot.constraints: ["silent", "eyes_closed"]`. Reports filter by constraint: *"compare cluster compactness across questions answered with eyes-closed vs eyes-open"*.

## Consequences

**Positive:**
- The room can change the rules. A workshop is no longer a script — it's a negotiation between the operator's plan and the room's needs.
- Constraints become *data*. Reports gain a new explanatory variable; *"silent rounds clustered the room 30 % tighter"* becomes a knowable fact.
- Composes naturally with the other cards: theme + composition + intent → "I want to speak about *trust*, in silence, after a slow round". The kit becomes a sentence.

**Negative:**
- Auto-apply is powerful and dangerous; a few participants can hijack the round. Mitigation: per-card auto-threshold is configurable; defaults are conservative; operator can disable auto-apply on the fly.

**Risks:**
- Constraint conflicts (`SILENT` + `HOLD_HANDS` are fine; `EYES_CLOSED` + `MIRROR` is contradictory). Mitigation: per-deck conflict matrix; conflicting constraints can't be simultaneously active and `/admin` shows the conflict for resolution.
- Constraint fatigue. Every round being modified loses the baseline. Mitigation: `/admin` shows "% of last 10 rounds modified" as a gentle nudge.

## Alternatives considered
- **Operator-only constraint announcement.** Verbal, no record, no data. Current state.
- **Pre-scripted constraints per question** in the deck file. Loses the *room-emergent* quality.
- **Voice command "everyone close your eyes"** — works once; doesn't compose with anything else.
