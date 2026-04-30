# ADR 0018 — Projection mode (`/project`) — the room as canvas

## Status
Proposed (complement to ADR 0006).

## Context
ADR 0006 introduces a clean "presenter mode" optimised for *information* — question text, big numbers, dark background. That's right for a wall-mounted display the room glances at to read the question.

The slide deck however is full of *spectacle*: "the room becomes the lens"; the gallery as theater; the geometry of belief; the choreography of one hundred bodies. Information mode doesn't capture that. There's a second screen hidden in this system: the *floor itself*, lit by a projector mounted on the gallery, showing the room what it's doing — in real time, ambient, beautiful.

When the projector is pointed at the floor from above, what you project gets stepped on. People standing in a glowing cluster halo see *their own* halo under their feet. Their movement leaves trails. The visualisation is not on a screen the room watches; it's on the room itself.

## Decision
Add `/project` — a route distinct from `/present`.

- Pure-canvas, fullscreen black, WS-driven from `/ws/detect`.
- **Cluster halos**: each cluster renders as a soft radial-gradient fill *under* the participants' positions in floor coords (via ADR 0003's homography), drifting smoothly with each frame.
- **Marker trails**: the last 5 seconds of each marker's path drawn as a fading line — with one corollary, the room sees its own choreography.
- **Active formation outline**: faint guide-lines that hint where the zones are without being prescriptive.
- **Active question text**: bottom 10 % of frame, 48 px serif, slow cross-fade on change. Optional via `?text=off` for venues that don't want a caption on the projection.

Visual language is **monochrome with cluster colors**, low-frequency content, high contrast — projector blur is a real constraint and detailed graphics get lost. The whole page targets 30 fps render via `requestAnimationFrame` even when WS frames arrive at 10 fps; positions are eased so movement feels continuous.

A `?layout=floor|wall` toggle adapts the geometry — `floor` projects assuming the surface is the actual floor (positions and zones drawn directly); `wall` is for projection on a vertical surface, so the same data renders as a stylised top-down map.

## Consequences

**Positive:**
- Theatrical impact. The room becomes legible to itself. Participants see the system *seeing* them.
- Pairs naturally with ADR 0019's highlight reel — the projection and the reel are visually unified.
- For venues without a projector it still works as a wall-mounted backdrop on a TV; the visual style is good either way.

**Negative:**
- Needs a projector mounted high enough to throw onto the floor, with brightness above ~3000 lumens or the cluster halos disappear. Many venues won't have that.
- Yet another route to keep visually consistent (`/`, `/admin`, `/track`, `/present`, `/project`).

**Risks:**
- Participants gaming the system — moving for the visualisation, not for the question. Mitigation: the visual style is subtle, not a leaderboard; halos are ambient, not point-scoring.
- A bug that makes the projection flicker or draws something jarring during a vulnerable moment. Mitigation: same `silent_mode` per-question gate as ADR 0016 — projection greys out (still shows positions, no celebratory effects) during privilege-walk formation.

## Alternatives considered
- **Re-purpose `/present`** — too much information; the visual style for projection wants to be *less* legible (in a good way) than `/present`.
- **Ship a hardware product (LED tape on the floor)** — much later if at all; software-projection covers most of the want.
- **Don't build it** — acceptable; the first 17 ADRs cover function. This is the one that turns the system into theater.
