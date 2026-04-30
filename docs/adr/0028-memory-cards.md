# ADR 0028 — Memory cards: participant-bookmarked moments

## Status
Proposed (depends on ADR 0021, 0022, 0019 highlight reel).

## Context
The system today decides what's interesting. ADR 0019's highlight-reel pipeline picks moments by geometry — biggest cluster, fastest reformation, longest outlier. Those are *statistically* interesting; they aren't necessarily *humanly* meaningful.

The room knows things the geometry doesn't:

- A facilitator's offhand sentence that broke the tension.
- The look that passed between two people during a privilege walk.
- The moment the room laughed for the first time.

These don't show up as cluster anomalies. They are *felt*, not measured. Currently they are unrecoverable — by the time anyone thinks "we should have captured that", it's gone.

## Decision
Add **2 memory cards** (out of the 32) — `MEMORY_KEEP` and `MEMORY_PUBLIC` — both `gesture`-mode (per ADR 0022).

- **`MEMORY_KEEP`** is the participant's personal bookmark. Raise it for a beat while in or near a moment that matters to you. The system records `MemoryEvent(t, holder_aruco_id, scope: "personal")`. The moment is included in *that participant's* reflection card (ADR 0017): *"You marked these moments: 14 minutes in, 41 minutes in, 78 minutes in. The room's clusters then were…"*

- **`MEMORY_PUBLIC`** is a vote for the *closing reel* (ADR 0019). Raise it when something you'd want the whole room to remember happens. If three or more participants raise it within a 15-second window, the moment is auto-promoted to the highlight reel as a "the room marked this" clip — the only moments that pass without statistical justification.

A `MEMORY_PUBLIC` window is rendered live on `/project` as a small slow pulse — not a leaderboard, just a visual acknowledgement that the room asked to remember.

The frame-recording policy from ADR 0019 is extended: even if `record_frames=false` for the session, a 6-second window (3 s before, 3 s after) of frames around a `MEMORY_PUBLIC` consensus is preserved — those moments alone go into the reel; the rest of the recording is discarded after the reel is generated.

## Consequences

**Positive:**
- The reel becomes co-authored. The room's emotional memory is now in the dataset.
- The reflection card gains a layer that's *only* the participant's: not what the system noticed, but what *they* noticed.
- For a workshop on trust and belonging, "the room asked us to remember this" is itself a powerful moment.

**Negative:**
- More frame storage decisions, more privacy surface. Mitigation: 6-second windows around `MEMORY_PUBLIC` consensus only; everything else respects the session's `record_frames` flag.
- The "consensus = auto-include" rule could be gamed by a coordinated minority. Mitigation: threshold is configurable; the `/admin` panel always shows operator-promotable and operator-vetoable memory clips before the reel renders.

**Risks:**
- A participant raises `MEMORY_KEEP` reflexively early in the session, then realises they meant something different. Mitigation: per-person `MEMORY_KEEP` is editable from the reflection-card preview before printing.
- Privacy. A "memory" is a shared moment, but the per-person card surfaces *what was happening when you marked it* — proximity, themes. Mitigation: the per-person card never names other people in the marked moment unless they consented to be named.

## Alternatives considered
- **Operator-only highlight selection.** Works, but loses the room's voice.
- **Phone bookmarking app.** Same data, breaks the physical-card cohesion of the kit.
- **No memory cards.** The reel is what geometry decides. Statistically defensible; emotionally thin.
