# ADR 0061 — Deprecate the card-grammar layer (ADRs 0042–0047)

## Status
Proposed. Supersedes ADRs 0042–0047 in their entirety.

## Context
ADRs 0042–0047 designed a *grammar* — modifier + subject + verb + object + connector + scope — as a way for participants to express richer ideas with their cards. Looked elegant on paper. **In a live room it would be the worst possible interface.**

A participant in a 4-minute round (per the slide deck) doesn't have 30 seconds to assemble a five-card sentence. They have one second to *react*. The grammar premise asks the room to behave like writers when the whole point of using physical cards is that they're **fast, decisive, and embodied**. Composing *"strongly want to speak, but tender"* out of five cards is ten times slower than just standing in the *yes* zone with a small frown.

What we actually want from participant cards:

- **Quick votes.** "Hold up YES, NO, or MAYBE — now."
- **Quick decisions.** "This or that. Vote with your card. Bracket continues."
- **Quick reactions.** Emoji-style ambient feedback as the workshop runs — no thinking, just noticing.
- **Quick proposals.** "I have an idea." Other people: "I'm in."
- **Quick rankings.** "Drop your priority cards on the floor."

Activation, not articulation. **Fun, not syntax.**

## Decision
Mark ADRs 0042–0047 as **Superseded** (status updates already applied inline per ADR 0041). Replace with ADRs 0062–0067:

- **ADR 0062 — Pulse polls.** Synchronised group vote with visual fireworks.
- **ADR 0063 — Reaction wave.** Emoji-style ambient cards drifting up `/project`.
- **ADR 0064 — Tournament cards.** Head-to-head bracket decided by walking left/right or holding LEFT/RIGHT.
- **ADR 0065 — Quick-rank cards.** Drop priority cards on the floor in order; camera reads the spatial sequence.
- **ADR 0066 — Idea drop + upvote.** A participant raises an IDEA card; others stand near them and raise UPVOTE; top ideas balloon up on the screen.
- **ADR 0067 — Activation kit budget.** Keep the 96-ID reservation from ADR 0042, redistribute it across the activation kit instead of the grammar layer.

What we **keep** from ADRs 0042–0047:

- The 96-ID participant range (it's still right; we just spend it differently).
- The per-holder co-occurrence window (it's still the right primitive for handling many simultaneous card raises).
- The detection / attribution machinery (works for any card class).

What we **drop**:

- All semantic composition: no modifiers qualifying atoms, no pronouns assigning subjects, no connectors joining clauses, no parsing.
- The text-rendering of compound events as prose. The audit log records `pulse_poll: yes (32 votes)`, not *"the room strongly says yes."*
- Per-card "kit" tags that mattered only for grammar slot-filling; activation cards each declare their own behaviour.

## Consequences

**Positive:**
- The participant kit becomes *playable*. A participant grabs a card and uses it without instruction.
- Workshops gain real momentum: a pulse poll resolves in 4 seconds; a tournament round in 30 seconds; a rank-drop in 60. The grammar approach would have required 30 seconds of card-assembly per gesture.
- The whole "language" framing — which sounded compelling — turns out to be *the wrong metaphor*. The right metaphor is **arcade**: clear inputs, immediate feedback, satisfying outputs.

**Negative:**
- ~3 days of design effort on ADRs 0042–0047 is now archival rather than active. The ADRs aren't deleted — they remain as history of a wrong-turn we explicitly rejected. Future contributors can see what we tried and why we backed away.
- Some genuine signal that grammar would have captured (e.g., *"tender BECAUSE lived"*) doesn't have a direct replacement. Mitigation: the operator's vibe channel (ADR 0037) absorbs that — when something nuanced happens, the operator types one word, and the cards stay simple.

**Risks:**
- Future me reads ADR 0061 and thinks the grammar idea was obviously bad. It wasn't *obviously* bad — it was *plausibly* bad, and we found out the right way (by writing it down and looking at it). The lesson is the lifecycle (ADR 0041) caught it early; the cost was 6 ADR files, not 6 months of code.

## Alternatives considered
- **Keep grammar as an advanced layer.** Optional, opt-in, layered on top of activation cards. Tempting; rejected because the budget pressure (96 IDs) is real and grammar primitives crowd out activation cards. *Pick one.*
- **Slim the grammar to just modifiers** (`STRONGLY`, `NOT`). Smaller; still a syntax exercise. The fundamental issue is the cognitive load of assembling, not the size of the vocabulary.

## Postscript
This ADR is the lifecycle (ADR 0041) doing its job. Six previous ADRs went to *Superseded* in a coordinated update; one new ADR explains why. The cost of building a wrong direction in *prose* is small; the cost of building it in *code* would have been months and probably a damaged pilot workshop. Catching it now is the win.
