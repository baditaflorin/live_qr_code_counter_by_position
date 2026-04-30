# ADR 0066 — Idea drop + upvote: the room proposes, the room decides

## Status
Proposed.

## Context
The slide deck's outlier moment (slide 9) hands the floor to one person at a time, picked by the operator. Powerful, but it's *operator → participant*. The room never directly **proposes** what to talk about next.

In moments where the agenda is open — *"what should we do with the next 20 minutes?"*, *"what's a question you'd like the room to answer?"*, *"what value should we hold this week?"* — the workshop benefits from the room generating *and selecting* options without operator gatekeeping. Today there's no mechanic for it. Verbal idea-and-vote is chaotic with 100 people; sticky notes are slow; phone tools break embodiment.

A simple two-card mechanic — *idea drop* and *upvote* — turns the room into a generator of options that the room itself ranks in real time, with a satisfying balloon-rising visual.

## Decision
Reserve **2 IDs** per ADR 0067: `IDEA` and `UPVOTE`.

**Phase 1 — Generation (60 seconds).**

A participant raises the `IDEA` card. The system:

1. Plays a short audio cue (per ADR 0016).
2. Records the holder's marker id, position, and timestamp as `IdeaEvent(id, holder, t)`.
3. Pings `/admin` so the operator can type a 1-line summary of the idea (or the operator can defer and the participant can type their own via the `/me` page on their phone — same flow as ADR 0051's join page).
4. As soon as the idea has text, it appears on `/project` as a **balloon** at the holder's floor position, with the idea text on it, drifting up slowly.

Multiple `IDEA` raises during the 60-second window each produce a balloon. Twenty participants raising ideas → twenty balloons drifting upward on `/project`.

**Phase 2 — Voting (60–120 seconds, configurable).**

Once the generation phase ends, the operator says "now, walk to an idea you support and raise the `UPVOTE` card." Each `UPVOTE` raise:

1. Looks up the holder's floor position.
2. Finds the **nearest balloon** within 1.5 m of the upvoter — the proximity is the vote.
3. The balloon's votes increment; visually the balloon **inflates** and **rises faster**.

Participants can move from balloon to balloon, raising `UPVOTE` once per idea. Per-person rate-limit (per ADR 0022) prevents spam.

**Phase 3 — Result.**

After 60+ seconds, the top 1–3 balloons (configurable) are *adopted* — they grow large, glow, and move to the centre of `/project`. Lower-vote balloons gracefully sink and pop. The adopted ideas are written to a `Topic` table for the operator to use as the next conversation starters.

**Aesthetic notes:**

- Balloons gently bob in the wind even without votes — the screen is alive.
- A balloon with no upvotes within 60 s pops — the room's silence is the room's verdict.
- The balloon's rise speed maps to vote rate, so a fast-trending idea visibly accelerates.

**Schema.** New `Idea` (`id, t, holder_aruco_id, text, position`) and `IdeaVote` (`id, idea_id, voter_aruco_id, t`) tables.

## Consequences

**Positive:**
- The room generates *and curates* its own next moves. Massive operator-attention savings on open-agenda moments.
- The mechanic is visibly *fun*. Balloons inflating, sinking, popping is theatre. Ideas gain or lose visibly. Nobody's idea quietly disappears — it pops.
- The adopted top-N becomes a real artefact: the workshop's emergent agenda, with attribution to the proposers.

**Negative:**
- The text-entry phase has friction — somebody has to type each idea. Mitigation: voice-to-text (whisper.cpp, locally — same path as ADR 0029 promise cards) lets the proposer speak the idea while raising the card; transcription appears on the balloon.
- A participant proposing an idea no one upvotes for sees their idea pop, possibly stings. Mitigation: the pop animation is gentle; the operator can manually rescue a popped idea worth keeping; the proposer's reflection card (ADR 0017) records *"you proposed: ___"* regardless of votes — the contribution is honoured even if not adopted.

**Risks:**
- Cliques voting in blocks (a tight friend-group all upvoting one of their own ideas) can dominate. Mitigation: the visualisation makes block-voting *visible* (a cluster of voters around one balloon); the operator can re-run with a "blind" vote variant if it's a problem.
- Idea quality varies. Some balloons are workshop-changing; some are jokes. Mitigation: that's *fine* — sometimes the joke is the right next move; the operator has final discretion to use any/all of the top-N.

## Alternatives considered
- **Operator-curated agenda.** Status quo. Misses the room's wisdom.
- **Sticky notes + dot voting.** Slow, no record, no visualisation.
- **Phone-app idea board.** Same data, no embodiment, no balloon theatre.
- **Pure spatial vote** (walk to your favourite zone) — works for closed lists; misses the *generative* phase that lets the room author its own options.

## Postscript
With ADRs 0062–0066 the participant kit becomes a small **arcade of decisions**: pulse poll for fast yes/no/maybe, reaction wave for ambient texture, tournament for *this-or-that*, quick-rank for priority orders, idea-drop for *generate then choose*. Each is a single gesture, each completes in seconds, each produces a visible group artefact. *Activation, not articulation.*
