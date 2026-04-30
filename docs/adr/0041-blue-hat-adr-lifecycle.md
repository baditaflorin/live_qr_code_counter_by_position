# ADR 0041 — 💙 Blue Hat · ADR lifecycle, who decides, when we re-read

> *Blue Hat: process and control. How do we think about thinking? How do we make decisions about decisions?*

## Status
Proposed (this is the meta-ADR; it governs all the others).

## Context
40 ADRs (after this one). Every single one is *Proposed*. None has been **accepted, implemented, deprecated, or superseded** because the project has no convention for moving an ADR through a lifecycle.

The cost is real:

- A reader can't tell what's *intent* (we plan to do this) vs. what's *aspiration* (we wrote this down once).
- New decisions silently contradict old ones. ADR 0033 mentioned "we may revisit ADR 0004's smoothing"; without a supersede mechanism, the contradiction lingers.
- ADRs ossify. A "Proposed" ADR sitting for 18 months looks identical to one written yesterday; the reader can't see staleness.
- New contributors don't know what to read first, or what to take seriously.

This ADR is the smallest possible process layer that fixes the problem.

## Decision

**Five lifecycle states.** A status line at the top of every ADR:

```
## Status
Proposed (2026-04-30)
```

| State                          | Meaning                                                          |
| ------------------------------ | ---------------------------------------------------------------- |
| `Proposed`                     | Written; not yet agreed direction. Default for new ADRs.         |
| `Accepted (YYYY-MM-DD)`        | Direction agreed. Implementation pending.                        |
| `Implemented (YYYY-MM-DD)`     | Code shipped; behaviour matches the decision.                    |
| `Deprecated (YYYY-MM-DD)`      | No longer current direction. Kept as history; not deleted.       |
| `Superseded by ADR XXXX`       | Replaced by a newer ADR. The new ADR's Context cites this one.   |

**Quorum.**

- ADR touching one subsystem (zones, tracking, markers, etc.): **one reviewer** other than the author.
- ADR touching multiple subsystems or platform/limits/process (most of 0001–0010, 0031–0035, 0036–0041): **two reviewers**, one of whom is the original author or has substantially worked on the affected code.
- ADR adopting a new dependency (Alembic, structlog, ffmpeg, whisper.cpp): **two reviewers** plus a one-week minimum review window for asynchronous objections.

**Cadence.**

- Every `Accepted` ADR is re-read at **6 months** with one question: *"is this still the direction?"* Outcomes:
  - **Confirm** — append `Re-read confirmed (YYYY-MM-DD)` to status; reset clock.
  - **Supersede** — write a replacement ADR; mark this one `Superseded by ADR XXXX`.
  - **Deprecate** — mark `Deprecated (YYYY-MM-DD)` with a one-line *why*.
- Every `Implemented` ADR is re-read at **12 months** for "is the implementation still serving the decision?"
- `Proposed` ADRs older than **12 months** with no movement get an automatic *"is this still alive?"* tag at the next quarterly review; the author either argues for it or the ADR is `Deprecated`.

**Lifecycle duty.** One person per quarter (rotation: alphabetical by name, three-month term) is responsible for running the re-read pass. They produce a one-page memo: how many ADRs reviewed, what changed states, what's stale. That memo lands in `docs/adr/lifecycle/YYYY-QN.md`.

**Naming.** `00XX-kebab-case-title.md`, sequence never recycled. Numbers ≥ 1000 reserved for **retrospective** ADRs (decisions baked into code we want to back-document).

**The README** ([`docs/adr/README.md`](README.md)) is now a *living index*: it shows current state, sorted by family. Implemented ADRs drop out of "suggested implementation order" automatically.

## Consequences

**Positive:**
- The document set has *shape*. New contributors can see "current direction" vs "history" vs "open questions" at a glance.
- Stale ADRs surface themselves rather than rotting silently.
- The audit log of ADR changes is the changelog of the system's design intent.

**Negative:**
- More meta-overhead. Mitigation: the lifecycle is light — five states, one date, one line per re-read.
- Quarterly lifecycle duty is real work for one person. Mitigation: the work is bounded — a few hours per quarter — and rotates.

**Risks:**
- The lifecycle is itself ignored. The discipline of running the quarterly pass is the actual product of this ADR; the document is just scaffolding. Mitigation: tie the quarterly memo to a calendar invitation; missing one is a public miss.
- ADRs marked `Implemented` rot when the code changes underneath them. Mitigation: 12-month re-read explicitly checks code-vs-ADR alignment.

## Alternatives considered
- **No lifecycle.** Current state. ADRs accumulate without shape; readers can't navigate.
- **Heavy lifecycle (Confluence, RFC governance, CFP-style reviews).** Right scale for an org with hundreds of contributors; overkill for this project. The five-state minimum is the floor, not the ceiling.
- **Throw out ADRs that aren't Implemented after 6 months.** Loses history; the *not-yet* ADRs are themselves a record of what was thought.

## Postscript
The Blue Hat in De Bono's framing is the one that controls the others. This ADR is structurally the same: it doesn't decide anything *about the system*, it decides *how we decide*. The other 40 ADRs are now governed by this one — including, recursively, this one's own re-read at six months.
