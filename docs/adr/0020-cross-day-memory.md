# ADR 0020 — Cross-day participant memory

## Status
Proposed (depends on ADR 0010 workshop scoping, ADR 0017 reflection cards).

## Context
The Czocha workshop is an arc:

- Day 1 — *The Opening*. Strangers arrive.
- Day 2 — *Stories*.
- Day 3 — *Conflict & Listening*.
- Day 4 — *The Vulnerable Act*.
- Day 5 — *The Return*.

The slide deck explicitly frames the entire week: *"they walk in as strangers; they leave the hall having seen each other"*. Each day's exercise builds on the patterns from the previous day. The Day 1 privilege walk seeds Day 3's conflict pairings. The Day 1 opposites become Day 3's listening partners.

The system today knows nothing about the through-line. By Day 2, marker #47 is just marker #47 again — even though by Day 2 we've spent four hours watching them. The slide deck says "the gallery sees them"; the system, structurally, does not remember.

The architectural shape of "by Day 2 the system already knows you" is small but it's *the* feature that turns five disconnected sessions into one workshop.

## Decision
Markers — and the people behind them — persist across the workshop's days. Three coordinated changes:

1. **`WorkshopDay` table**, scoped under `Workshop` (ADR 0010): `day_index`, `name`, `started_at`, `ended_at`. The active day is selectable in `/admin`. All snapshots, tracking sessions, votes are scoped to a `(workshop_id, day_index)` pair.

2. **First-seen-this-day events.** When a known marker is detected on day N (where N > 1) for the first time that day, the WS payload emits a `welcome_back` event with the person's name and a 1-line context: *"Last seen on Day 1, stood for 'I have a friend I would call at three in the morning.'"* `/present` renders this as a brief 2-second fade-in greeting on the projection. Subtle. Unmissable.

3. **Per-participant arc page (`/recap/{aruco_id}`)**. A page (and printable card) that shows what *this person* did across each prior day:
   - Day 1: where they stood on the privilege walk.
   - Day 2: who they shared stories with most.
   - Day 3: who they were paired with on conflict.
   - Day 4: what they offered.
   - Day 5: filled in live, and ends with a single question shaped like the slide deck's framing — *"What do you carry home?"*

The Day 5 closing reel (ADR 0019) auto-includes per-person trajectories: each participant's position across the five days as a single visual line. The reel is no longer "what happened tonight"; it's "what happened *to* you, this week".

## Consequences

**Positive:**
- The week feels coherent. Day 2's opening line — said by the system, projected on the room — is "we remember you." That's the whole point of the slide deck's "from strangers to witnesses" thesis. Now the system *embodies* it.
- Reflection cards (ADR 0017) become richer at end-of-week: they're not just "tonight" but "this week".
- Operators get a per-day pacing tool: they see continuity gaps before they happen.

**Negative:**
- The day-switching UX in `/admin` is one more concept. Setting the wrong active day silently corrupts the data. Mitigation: confirmation banner showing the active day on every operator page.
- More schema; more migration; tied to ADR 0002 and ADR 0010 landing first.

**Risks:**
- A marker re-issued to a different person between days (someone lost theirs and got a new one) gets misattributed. Mitigation: `Marker.replaced_at` and `Marker.replaces` fields create a chain; reports follow the chain so the new person carries the old person's history correctly *only if explicitly re-bound*.
- The "welcome back" greeting could embarrass someone whose Day 1 answer was vulnerable. Mitigation: the greeting never repeats the *content* of a vulnerable answer; only neutral context ("you were here on Day 1").

## Alternatives considered
- **Treat each day as a separate workshop** — current state if ADR 0010 lands without this; loses the entire arc.
- **Manual operator notes per participant** — high effort, low fidelity; doesn't scale to 100 people.
- **No memory** — sufficient for a 1-day pilot, insufficient for the 5-day program the slide deck describes. The whole *point* of the system at Czocha is the through-line.
