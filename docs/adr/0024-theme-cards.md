# ADR 0024 — Theme cards (8 of the 32 participant IDs)

## Status
Proposed (depends on ADR 0021, 0022; complements ADR 0030).

## Context
Workshops accumulate vocabulary over five days. Day 1 has *trust*; Day 3 conflict has *grief* and *anger*; Day 5 has *carry-home*. The slide deck is full of these words — they are the lexicon participants leave with.

The system today has zero relationship to that lexicon. Snapshots, votes, tracking samples are all numerical or zonal. There's no way for the data to say *"the trust questions clustered the room differently than the grief questions"* — even though that's exactly the kind of insight a facilitator wants for the closing reflection.

A small deck of physical theme words, raised by participants alongside their answer, becomes a participant-driven taxonomy of the workshop. The room labels its own data.

## Decision
Reserve **8 participant card IDs** (per ADR 0021) for theme cards. Each card has a printed thematic word on its face. The default 8 for Czocha Day 1 are drawn directly from the slide-deck vocabulary:

`TRUST`, `GRIEF`, `JOY`, `FEAR`, `PRIDE`, `LONELY`, `OPEN`, `CARRY`.

The card list is **per-workshop-deck** (ADR 0030 codifies the kit-mint mechanism). For the conflict-and-listening day, the default 8 might be `ANGER`, `WOUND`, `BOUNDARY`, `RECONCILE`, `WITNESS`, `PRESSURE`, `RELEASE`, `BLAME`.

Theme cards are `level`-mode (per ADR 0022): they're "active" while held. Their effect is **tagging**:

- While raised, the holder's marker is tagged with that theme for the current snapshot. If the participant raises the card during a snapshot capture, that snapshot row gets `themes: ["TRUST"]`.
- For tracking sessions: theme card events are written to `ParticipantEvent` and aggregated per-question in the report. Reports gain a "themes" axis: *"the questions in Block 4 (How You Trust) were most often tagged TRUST and LONELY"*.
- For reflection cards (ADR 0017): the card includes "the themes you raised most: *trust* (5x), *open* (3x)."

Theme cards combine via the co-occurrence window in ADR 0022: a participant raising `TRUST` *and* `REACT_YES` simultaneously creates a composite event "yes, themed trust" — richer than either alone.

## Consequences

**Positive:**
- The dataset gains a vocabulary the room itself authored. Reports become readable as workshop reflections, not just stats.
- Closing reels and per-person cards include themes — the participant takes home not just *where they stood* but *which word they raised*.
- Cross-workshop comparison: how does the *trust* axis on this cohort look vs. last quarter's? (Privacy-respecting because no individual is named.)

**Negative:**
- Themes per-deck means workshops can't easily mix data across days unless their theme decks share words. Mitigation: a small canonical vocabulary (the 8 above) is the default; workshops add a custom deck via ADR 0030 and the system tracks them as separate dimensions.
- Tagging is opt-in; a quiet participant ends up untagged in the data. Mitigation: that's the point; absence of tagging is data too.

**Risks:**
- Cards left on the floor get raised by anyone, possibly inverting their meaning. Mitigation: theme cards are most useful when raised *with* a participant marker visible (attribution per ADR 0022); orphan-raised cards are still recorded but flagged low-confidence.
- Theme word choice carries weight. *FEAR* on a card means something different from *ANXIOUS*. Mitigation: per-workshop curation in ADR 0030; no auto-generated theme decks.

## Alternatives considered
- **Sticky notes on a wall** — analog, satisfying, but not in the data. The cards do both.
- **Voice-tagged annotation** — operators speak themes during the session, system transcribes. Higher-effort, lossier, breaks the slide-deck silence.
- **No themes** — current state. Reports are statistically rich but linguistically empty.
