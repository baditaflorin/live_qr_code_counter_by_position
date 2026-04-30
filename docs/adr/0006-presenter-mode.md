# ADR 0006 — Presenter mode at `/present`

## Status
Proposed.

## Context
The Live page (`/`) is the operator's console: webcam selector, FPS readout, dropdowns, status pill, prev/next buttons, detected-list, snapshot controls. From the gallery, the operator drives a 90-minute exercise on a laptop. There is **no audience-facing view**.

In a real workshop the natural setup is:
- Operator on the gallery: laptop with the operator console.
- Audience-facing wall: a projection or large display showing only what the room needs to see — the current question, the formation hint, the live counts.

Today the operator must clean up the Live page (close dropdowns, scroll past controls) and put the browser in fullscreen, which still shows operator chrome. There is no clean projection.

## Decision
Add a dedicated `/present` route.

- Pure-render page, no controls. WebSocket connects to `/ws/detect` like Live but reads only the `active_question` and `zone_counts`.
- Layout:
  - Top 30%: question text at 96 px, block name and formation badge at 24 px.
  - Bottom 70%: per-zone counts. Big numbers (160 px) in a row, zone label underneath at 36 px. Colours match zone polygons.
- Auto-advances when the active question changes. A 1-second cross-fade announces the transition.
- Esc / `?menu=1` returns to Live; otherwise no UI affordances.
- Optional `?theme=light` for projectors that handle dark backgrounds poorly.

## Consequences

**Positive:**
- Clean projection from the gallery without window-manager gymnastics.
- A second laptop can run `/present` mirrored to the projector while the operator drives `/admin` and `/`.
- Decouples audience-facing display from operator UX — they can evolve independently.

**Negative:**
- One more page to keep visually consistent with the formations.
- Active-question logic is now a contract that three pages depend on (`/`, `/admin`, `/present`).

**Risks:**
- A live page that occasionally races with `/present` (e.g. operator advances the question while presenter is mid-fade) needs a clean re-sync. Mitigation: presenter ignores stale messages and always renders the latest `active_question.id`.

## Alternatives considered
- **Fullscreen API on Live** — still shows operator dropdowns and the camera feed.
- **CSS-only "presenter" theme on Live** — distinct route is cleaner; saves a query string and lets us tune layout independently.
- **Split-view with operator + presenter on the same page** — visually noisy on small operator laptops.
