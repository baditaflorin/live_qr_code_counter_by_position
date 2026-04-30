# ADR 0064 — Tournament cards: head-to-head bracket

## Status
Proposed.

## Context
Workshops are full of *"this or that"* decisions. Pizza or sushi for dinner. Block 2 next or Block 4. Lake walk or hot tub. Five proposed values, pick three. The current system has no fast way to run these — the operator either picks one (boring), runs a verbal show-of-hands (no record, half the room missed it), or improvises a vote-with-feet exercise (5 minutes per question, kills momentum).

A tournament — pairwise head-to-head with a visible bracket — is the *fun* version. Two options on screen, room votes by a single fast gesture, winner advances, next pairing in 15 seconds. The whole bracket plays out in 2–3 minutes regardless of how many options started.

## Decision
Reserve **2 IDs** (per ADR 0067): `TOURN_LEFT` and `TOURN_RIGHT`. Operator-driven flow; participants vote with one gesture per round.

**Setup.**

1. Operator types or paste-imports a set of options into `/admin`: *"Pizza, Sushi, Pasta, Burgers"*.
2. `/admin` builds a single-elimination bracket. Odd numbers get a bye in round 1.

**Round (15–20 seconds each):**

1. `/present` shows two options side-by-side, large, with `LEFT` and `RIGHT` arrows. Audio cue (per ADR 0016) marks round start.
2. **5-second vote window**: participants raise either `TOURN_LEFT` or `TOURN_RIGHT`. (Or — alternative gesture — they physically *step* to the left or right side of the room; floor zones double as voting zones for this round only.)
3. Tally appears, winner glows briefly, loser greys out and slides off.
4. Bracket advances. Next pairing.

**Bracket viz on `/project`:**

The full bracket is drawn once, off to the side. Completed match-ups fill in with the winner's name as the tournament progresses. The crowd watches their collective preference assemble into a final winner over a few minutes. Cheap drama.

**Modes.**

- **Single-elimination** (default): 8 options → 7 rounds.
- **Top-N pick**: tournament ends when N options remain. *"Pick our top 3 themes for tomorrow."*
- **Round-robin** (small sets only — ≤ 6 options): every option vs every other; ranked by win-percentage. Slower but produces a complete preference order.

**Re-ties.** A 50/50 tie within ±1 vote triggers a 5-second tiebreaker round with a visibly playful animation ("THE ROOM IS DIVIDED — VOTE AGAIN"). If still tied, operator decides.

**Data.** A `Tournament` table: `(id, t, options_json, mode, results_json, winner)`. Each round's vote is a `Vote` row tagged with `tournament_round_id`.

## Consequences

**Positive:**
- Group decisions that today take 5 minutes of debate become 2 minutes of theatre. The bracket itself is content — the workshop's collective taste, made visible.
- The mechanic transfers across many use cases: choose a venue, pick a theme song, vote on which workshop activity to extend, rank values, decide on workshop name.
- Beautiful natural artefact for the closing reel (ADR 0019): "the room voted for these three themes by 52–48".

**Negative:**
- Two more cards (`LEFT`, `RIGHT`) for the kit. Mitigation: these can also serve as the `WALK_LEFT` / `WALK_RIGHT` zones for spatial-vote variants — same physical card stands in for either gesture.
- Tournament mode breaks the formation flow — you can't run a tournament *during* a Block 4 standing-on-sides exercise. Mitigation: tournaments live between blocks, not inside them.

**Risks:**
- Bracket bias: option A vs B can come down to which one was on the *left* side of the screen (left-to-right reading bias). Mitigation: side assignment randomises per round; the operator can re-pair if a result feels off.
- Ties in a 100-person room are rare but possible. Mitigation: tiebreaker round is built in; ultimate fallback is operator coin-flip with a visible animation.
- A boring tournament (one option dominates round 1) loses the room's attention. Mitigation: round-robin or top-N modes for cases where elimination is too aggressive; operator can call mid-tournament to "merge" two close options into one.

## Alternatives considered
- **Single-shot multi-choice vote.** Simpler, less narrative. Tournaments produce a story; one-shot votes produce a number.
- **Dot-voting / weighted preferences.** Better data; worse spectacle. Tournaments are designed for the *room watching the room decide*.
- **Operator picks; no vote.** Status quo for many decisions. Faster, less collective ownership of the result.
