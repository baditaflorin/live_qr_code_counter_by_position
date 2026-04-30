# ADR 0019 — Auto-generated session highlight reel

## Status
Proposed (depends on ADR 0008 timeline data, ADR 0010 retention policy).

## Context
The slide deck explicitly promises a closing reel: *"What we capture becomes the closing reel of Day 5"*. In practice this means an editor sits at a workstation for hours after each session, scrubbing through six camera feeds, picking the moments that mattered. By the time the reel exists the workshop is over; it lands a week later in a Vimeo link nobody opens.

But the data already knows what the moments were. The system has, per session, every cluster formation, every snapshot, every formation transition. Statistically, *interesting* is detectable — and for each interesting moment, the corresponding 4-second window of camera footage is the clip you'd cut. Stitch the clips, you have the reel.

The slide deck is structurally asking for this to be automated. Operators, post-workshop, are tired and want the reel *that night*, not next week.

## Decision
Add a highlight-reel pipeline.

**During recording.** When `record_frames=true` is set on a `TrackingSession` (off by default for privacy), the WS detection loop additionally writes one full JPEG frame to disk per second, into `data/frames/{session_id}/{ts}.jpg`. Frames are kept for 24 h, then auto-pruned (configurable per ADR 0010 retention).

**At session end.** `POST /api/tracking/sessions/{id}/highlights` runs an interest-detection pass over the session's TrackingSamples and picks the top K (default 10) moments:

- The **largest cluster** of the session.
- The **fastest reformation** — a cluster of ≥6 that formed within 5 s.
- The **longest-held outlier** — a person who stood alone the longest.
- The **everyone-agrees** moment — every marker in one zone for ≥3 s.
- The **biggest spread** — formation change with the largest delta in position spread.

For each moment, the pipeline pulls a 4-second window of stored frames around that timestamp, composites the live overlay on top (cluster hulls, question text — same code as `/project`), and concatenates clips into an MP4 with cross-fades. ffmpeg does the encode, all server-side. The result is downloadable at `GET /api/tracking/sessions/{id}/highlights.mp4`.

## Consequences

**Positive:**
- The slide-deck promise of "the closing reel" arrives with zero post-production. Sharable that night.
- Becomes the workshop's calling card — the reel is the most-shared artifact from the whole event.
- Composes with ADR 0017 (the personal cards): the reel is the group narrative, the cards are the individual ones.

**Negative:**
- Frame storage eats disk. 1280×720 JPEG @ 1 Hz × 90 min × 50 KB ≈ 270 MB / session. Manageable but real. Mitigation: keep frames only until the reel is generated, or for 24 h, whichever is shorter.
- ffmpeg is a non-Python dep added to the container.

**Risks:**
- **Privacy.** Stored frames contain everyone's faces; the reel is a recording of the room. Frame storage is opt-in per session and *requires* the workshop to have collected consent at registration. The reel itself can be marked "internal only" or "shareable" via a per-workshop toggle (ADR 0010 scoping makes this enforceable).
- **Wrong moments.** The interest detector picks based on geometry; sometimes the *human* moments are subtler. Mitigation: the operator can mark a snapshot as "highlight: yes" mid-session (a control marker, ADR 0014) and the pipeline always includes those.

## Alternatives considered
- **External video editor + manual cut** — current default. Hours of work, often skipped.
- **Pure overlay-only reel (no camera footage)** — privacy-safe but loses the human warmth of seeing actual people.
- **Stream the reel pipeline to S3** — adds external dep; defer until the workshop sponsors require it.
