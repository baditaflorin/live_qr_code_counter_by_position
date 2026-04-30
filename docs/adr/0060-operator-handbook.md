# ADR 0060 — Operator handbook & onboarding path

## Status
Proposed.

## Context
A new facilitator can't reasonably read 60 ADRs and figure out how to run a workshop. They will not. The repo's `README.md` is a developer's view (Docker, FastAPI, OpenCV); the ADRs are a designer's view (intent, alternatives, tradeoffs). Neither is a *user's* view.

ADR 0039 destination #7 says *"one person can install, configure, run, and debrief a workshop without touching a Python file."* Today there is no path from "I am an interested facilitator" to "I have run my first workshop" that doesn't require a developer in the room. The handbook is the bridge.

Marketing copy is the wrong document for a tool whose first users are skilled facilitators with serious workshops on the line. They need *honest documentation*, not pitch.

## Decision
Maintain `docs/handbook/` with five chapters, each under **30 minutes to read end-to-end**, each ending with a concrete *"you've done this if..."* checklist.

### Chapter 1 — What this is (5 minutes)

`docs/handbook/01-what-this-is.md`

- The slide-deck thesis in plain language: *the room is the lens; positions are data; clusters tell stories.*
- What the system *does* today (the implemented ADRs).
- What it *doesn't* do (the proposed ADRs that haven't shipped — do not pretend they have).
- One screenshot of `/admin`, one of `/track`, one of a reflection card. Honest about current visual polish.
- Done if: a reader can describe in one sentence what the tool measures and can list two things it doesn't.

### Chapter 2 — Setup (60 minutes hands-on, 15 minutes reading)

`docs/handbook/02-setup.md`

- Hardware ordering (links to ADR 0056).
- Software install — *exactly five terminal commands* on a fresh Mac. No skipped steps. No "you should already have X" assumptions.
- First-calibration walkthrough with screenshots: anchor placement, ChArUco run, intrinsic confirmation, extrinsic confirmation.
- A **5-friend test workshop**: invite five people, set up at home, run a 15-minute mini-version of the Czocha Block 4 (six two-camps questions). The chapter is built so that completing it produces working data on the operator's first installation.
- Done if: the reader has run the 5-friend test and seen a report with non-zero `pair_contact_seconds`.

### Chapter 3 — Run a workshop (45 minutes reading)

`docs/handbook/03-run-a-workshop.md`

- Pre-event checklist (T−7 days, T−24 hours, T−1 hour) — drawn from ADR 0058's pilot protocol.
- Hardware-on-site setup, in order, with photos.
- The participant briefing script (verbatim, in two languages where relevant) — lifted from ADR 0058.
- Running the exercise: when to advance questions, when to record snapshots, when to start tracking, what the operator should *watch* on screen.
- Stop button (`Esc Esc Esc`) and when to use it.
- Post-event debrief format (the 30-minute alone-write from ADR 0058).
- Done if: the reader has the briefing script bookmarked, knows the stop-button keystroke without looking, and has a printed pre-event checklist on their clipboard.

### Chapter 4 — What to do when it breaks (20 minutes reading)

`docs/handbook/04-when-it-breaks.md`

- The five most common failure modes (from ADR 0038 runbook), with one-paragraph recovery each.
- "Anything weird" log discipline — keep typing while the workshop continues.
- When to escalate to the operator group chat vs. when to run the runbook solo.
- The "phone-camera is misbehaving" troubleshooting tree (when ADR 0051 is shipped).
- Done if: the reader can articulate, without looking, what to do if the live overlay freezes mid-snapshot.

### Chapter 5 — What's coming (10 minutes reading)

`docs/handbook/05-whats-coming.md`

- The 2028 destination (ADR 0039) in two paragraphs.
- The current 90-day plan (ADR 0057), so the reader knows what's expected to ship in the next quarter.
- How to contribute back: pilot reports (ADR 0058), feature requests (open an ADR), bug reports.
- Sets the right expectation: this is an *evolving* tool, not a finished product. The operator is part of the workshop *and* part of the development loop.
- Done if: the reader knows where to send their first pilot report.

### Distribution

- The handbook lives in the repo, rendered as static HTML at `https://live-qr.wemeshup.com/docs` (Pages-style hosting from `docs/handbook/`). New facilitators arrive at the docs URL, not the repo root.
- A printable-PDF version of all five chapters fits in a single 32-page A5 booklet — for the wooden box (ADR 0039 destination), this booklet is what physically ships.
- Each chapter is **versioned** alongside the code. The handbook for v0.5 differs from v0.6 if the system changed; both are kept.

### Chapter ownership

- Each chapter has a named *owner* (rotated quarterly). Owners do the 6-month re-read (ADR 0041) for *their* chapter and update for currency.
- A chapter that hasn't been re-read in 6 months gets a stale-warning banner at the top: *"This chapter was last verified on 2026-04-01."*

## Consequences

**Positive:**
- The path from "interested facilitator" to "running a workshop" exists in writing. The first user without a developer in the room can complete it.
- The handbook is also the *de-facto external spec* — what the system claims to be. It keeps the engineering team honest: implemented features are documented; documented features are implemented; the gap is closed one chapter re-read at a time.
- The 5-friend test workshop in Chapter 2 catches install bugs that the smoke test (ADR 0059) misses — like *"the docs say port 8000, the actual service uses 18050."*

**Negative:**
- Five chapters is real writing, real maintenance, real photo-taking. ~30 hours for the first cut, ~5 hours per quarterly re-read across all chapters. Mitigation: chapter ownership distributes the load; no one owner does all of it.
- The handbook *is* a marketing surface whether we like it or not — ugly screenshots in Chapter 1 hurt adoption. Mitigation: design polish for screenshots is part of each chapter's quarterly re-read.

**Risks:**
- The handbook drifts from reality (chapters describe features that broke; ADRs say one thing, handbook says another). Mitigation: the smoke test (ADR 0059) verifies install commands from Chapter 2 are still correct; the handbook stale-warning makes drift visible.
- A chapter owner leaves and the chapter rots. Mitigation: ownership rotates quarterly anyway; an unowned chapter is automatically re-assigned at the quarterly review.

## Alternatives considered
- **README only.** Status quo. Works for developers; fails for the actual users.
- **Video tutorials.** Better for some content (calibration walkthrough), worse for others (reference checklists). The handbook *includes* embedded videos for Chapter 2's calibration; it doesn't *replace* prose for chapters that are mostly procedure.
- **External docs site (Notion / Gitbook).** Splits the documentation source from the code source — leads to drift. Co-locating in `docs/handbook/` keeps them in sync.

## Postscript
This is the most concrete *make-it-real* ADR in the set. ADRs 0001–0055 build the system; ADRs 0056–0059 set up the production scaffolding around it; ADR 0060 is the last yard — the document a stranger reads on a Saturday morning and ends up running their first workshop the following Tuesday. Without it, every other ADR's value is gated by "someone in our team is in the room", and ADR 0039's destination remains aspirational.
