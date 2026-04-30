# ADR 0063 — Reaction wave: emoji-style ambient reactions

## Status
Proposed.

## Context
Most of what happens in a workshop isn't a *decision* the operator wants to read. It's *atmosphere* — laughter at a moment, *oof* at a vulnerable share, side-eyes at a contentious claim, hearts when something lands. The slide deck talks about *"the geometry of belief"* in the formal exercises; the *texture* of the workshop lives in these tiny continuous reactions, and today the system records exactly none of them.

A small set of emoji-style reaction cards, raised whenever a participant feels like it (no operator coordination, no countdown, no formation), gives the system a *heartbeat* of ambient response — and gives the room a visual layer on `/project` that makes participants' reactions visible to each other in real time, like Twitch chat for an embodied workshop.

## Decision
Reserve **8 IDs** (per ADR 0067) for reaction cards — emoji-coded printed faces, raised at any moment with zero ceremony.

| Card                | Visual               | Use                                              |
| ------------------- | -------------------- | ------------------------------------------------ |
| `REACT_HEART`       | ❤️                   | "I love this."                                  |
| `REACT_FIRE`        | 🔥                  | "This is hitting."                               |
| `REACT_LAUGH`       | 😂                  | "That was funny."                                |
| `REACT_TEAR`        | 😢                  | "This is moving me."                             |
| `REACT_THINK`       | 🤔                  | "I'm chewing on this."                           |
| `REACT_YES`         | 🙌                  | "Yes, yes, yes."                                 |
| `REACT_PAUSE`       | ⏸️                   | "Slow down — I need a moment."                   |
| `REACT_AGAIN`       | 🔁                  | "Say that again."                                |

`pulse`-mode (per the existing card-handling semantics) — fire on raise, fire on lower, no debounce gate. A reaction is meant to be brief and frequent.

**`/project` choreography:**

When a reaction card fires, `/project` paints an emoji-shaped bubble at the holder's floor position, drifting upward and fading over ~3 seconds. The visual budget is intentional:

- **Up to 30 simultaneous bubbles**; older ones decay first.
- **Crowd density**: when ≥ 5 of the same emoji fire within a 2-second window, the bubbles aggregate into one big bubble that floats higher and fades slower — the room's collective reaction visibly compounds.
- **Trail layer**: a fading ribbon of reactions scrolls along the bottom of `/project` so the most recent ~30 seconds of reaction wave is always visible.

**Operator surface:** `/admin` shows a tiny per-question reaction histogram. *"For 'I would call a friend at 3am': 12 ❤️, 4 😢, 3 🤔, 1 ⏸️."* Useful for the closing reflection — *"the room reacted most strongly to question 7"*.

**Reflection card surface (per ADR 0017):** a small *"You raised:"* line on the back. *"4× ❤️, 2× 😂, 1× 😢."* Personal taste of how *you* felt across the night.

**Schema.** Reaction events go into the existing `ParticipantEvent` table with `kind = "reaction"` and `reaction = "heart"` etc. No new table.

## Consequences

**Positive:**
- The system finally has a *texture* layer. The workshop's atmosphere is recorded alongside its decisions.
- The visual on `/project` makes the room feel *responsive* — a participant who raises a card sees their bubble appear, others see it too. The room feels itself.
- Replays (ADR 0008 timeline) gain emotional shape — scrubbing through a session, you can see *when the laughs landed, when the tears came*.
- Highlight reel selection (ADR 0019) can use reaction density as an interest signal: a moment with 20 ❤️ in a 5-second window is almost certainly worth keeping.

**Negative:**
- Eight more cards in the kit. Mitigation: the reaction cards live on a single A6 *fan-card* with all 8 emojis on different flips of the same physical card. One physical object, eight gestures.
- Constant motion on `/project` could be visually noisy. Mitigation: the bubble decay rate, max-on-screen, and aggregation thresholds are configurable; some workshops will turn the reaction layer down or off.

**Risks:**
- Spam — a participant raising the same card constantly. Mitigation: per-marker rate limit in `ParticipantRouter` (already exists per ADR 0022); limits are configurable per card class.
- Cultural friction — emojis aren't universal. Mitigation: ADR 0030's per-deck customisation lets workshops swap emoji sets for culture-fit. The default set above is a starting point, not a mandate.
- Performance contagion — once everyone sees others reacting, reactions might cluster around socially-safe emojis. That's *information* (a real social phenomenon), not a flaw; the data captures it accurately.

## Alternatives considered
- **One reaction card with multiple meanings selected by orientation.** Cute, fragile, hard to brief.
- **Phone-app reactions.** Same data, breaks the embodiment thesis, hands aren't free.
- **No ambient reactions; only formal pulse polls.** Loses the *texture*. The reaction wave is *exactly* the layer that pulse polls don't capture.
