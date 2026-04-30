# ADR 0057 — MVP slice & 90-day rollout plan

## Status
Proposed.

## Context
55 ADRs is paralysis-by-options. A new contributor reading the repo can't tell which decisions are *aspiration* from which are *next up*. Every ADR has the same status (`Proposed`) and roughly the same prose weight. There's no concrete *"if we built X, Y, Z over the next 90 days, what's the smallest set that delivers a real workshop?"*

Without a phased plan:

- Implementation order is decided ad-hoc, often by whichever ADR was most recently exciting.
- Pilot workshops (ADR 0058) can't run because the prerequisites aren't sequenced.
- The team can't commit to a deliverable date because the deliverable isn't defined.

The honest path: pick the *smallest* set of ADRs whose union is a *useful* workshop tool, time-box implementation, and ship through three real workshops.

## Decision
Three phases over **90 days**, each ending with the system actually used at a real workshop.

### Phase 1 — Make the existing prod presentable (Days 0–21)

Goal: the system as it stands today, locked-down and observable.

| ADR  | Slice                                                            |
| ---- | ---------------------------------------------------------------- |
| 0001 | Bearer-token auth on `POST/PUT/PATCH/DELETE`                     |
| 0002 | Alembic migrations replacing `_migrate_questions()`              |
| 0009 | Audit log table + middleware (no UI yet)                         |
| 0036 | 5 starter metrics: `detection.latency_ms`, `detection.markers_seen`, `tracking.sample_writes_per_minute`, `ws.bandwidth_mbps`, `db.report_compute_ms` |

**Deliverable workshop**: an internal team workshop (~10 people, single camera, 60 minutes) using the unchanged feature set. Run by us. Success = it works as well as it does now, with auth + audit + 5 metrics shipping data.

### Phase 2 — Polish + presenter mode (Days 22–49)

Goal: the system is *pleasant* to use; first external operators can run it.

| ADR  | Slice                                                            |
| ---- | ---------------------------------------------------------------- |
| 0006 | Presenter mode at `/present`                                     |
| 0007 | CSV roster import + bulk markers                                 |
| 0016 | Audio cues — minimum: snapshot bell, cluster chord, page-turn    |
| 0011 | Control-marker foundation (reserved IDs only; no actions yet)    |
| 0014 | Hands-free session control: `TRACK_START`, `TRACK_STOP`, `Q_NEXT`, `Q_PREV` only — defer the rest |
| 0017 | Personal reflection card — minimum: identity strip + stand timeline + top-3 partners |

**Deliverable workshops**: three external workshops with sponsor-facilitators. Pre-event hardware is Tier 2 from ADR 0056. Operator runs it; we observe and capture per ADR 0058.

### Phase 3 — Ground-floor sensing pilot (Days 50–90)

Goal: prove the phone-camera idea works in a real room.

| ADR  | Slice                                                            |
| ---- | ---------------------------------------------------------------- |
| 0048 | 6-DOF pose estimation — needs ChArUco calibration step           |
| 0049 | Multi-placement markers — *just hat + chest*, defer back markers |
| 0051 | Phone-as-camera join flow (active state only; no rebalance loop) |
| 0054 | Self-calibration tier 1 (anchors only); skip tiers 2 / 3         |
| 0053 | Live coverage view — read-only first; no convergence pings yet   |
| 0036 | Telemetry expansion: `scene.coverage_pct`, `scene.triangulated_pct`, per-camera `Q` (groundwork for ADR 0055) |

**Deliverable workshop**: one workshop where a fixed-camera baseline runs alongside a fleet of phone-cameras held by participants. Compare `TrackingSample` data across both — does the phone-fleet produce comparable cluster-detection? Where does it fail?

### What's deliberately *not* in 90 days

- Multi-camera fusion (ADR 0005) at full scale — single-camera + opportunistic phone-cameras is enough for Phase 3.
- Highlight reel (ADR 0019), promise cards (ADR 0029), cross-day memory (ADR 0020), grammar layer (ADRs 0042–0047) — all post-90.
- Wooden box (ADR 0039) — that's a 3-year arc; this plan is 90 days.

### Acceptance criteria per phase

Each phase has a single integration milestone:

- **Phase 1** done = a real workshop ran end-to-end with no manual recovery, audit log shows expected events, metrics show expected values.
- **Phase 2** done = three operators outside the original team ran workshops; their feedback is in `docs/pilots/`; at least one bug surfaced and was fixed.
- **Phase 3** done = phone-camera + fixed-camera dual-feed at one workshop, side-by-side data comparison written up as a `docs/pilots/2026-XX-XX-phone-camera-pilot.md`.

### Risk to schedule

- Phase 1: smallest, lowest risk. Auth + Alembic are well-understood.
- Phase 2: biggest risk is presenter-mode design polish — the visual style needs an iteration the engineering team usually skips.
- Phase 3: highest risk. Calibration UX on phones is unproven; quality-weighted fusion (deferred ADR 0055) might turn out to be needed earlier than planned.

Mitigation: each phase has 1 week of slack baked in. Phase 3 is allowed to fall back to "phones contribute a 2D position only, no orientation" if pose estimation on phones is too rough.

## Consequences

**Positive:**
- Implementation order is decided once, in writing, with dates.
- Three real workshops in 90 days produces real bug reports — the only kind that matters.
- The "what's not in scope" list closes the door on sprint-creep before it opens.

**Negative:**
- Locks out tactical opportunities for ~3 months (a great new ADR idea has to wait). Mitigation: queued for the next 90-day plan written at day-90 retro.
- Phase 3's deliverable workshop is ambitious and could slip. Mitigation: the fallback (phones as 2D-position contributors, no pose) is the *minimum* viable; we ship that even if pose is incomplete.

**Risks:**
- Three external workshops in a 4-week Phase 2 window depends on facilitator availability; we don't fully control the calendar. Mitigation: Phase 2 runs against a *target* of three workshops; if only one can be scheduled in the window, the phase still completes on the one workshop, with two more deferred to early Phase 3.
- The whole plan assumes the team has bandwidth. In practice, work on the system competes with other things. Mitigation: this ADR is a *contract* — taking on something else within 90 days requires a new ADR superseding this one.

## Alternatives considered
- **No phased plan.** Status quo; everything happens "next" forever.
- **Six-month plan.** More features, less rigour. The 90-day window is tight enough to force prioritisation.
- **Single MVP slice (no phases).** Doesn't recover gracefully — if anything in the slice fails, the entire 90 days fail. Phasing means each 3-week window can be re-planned.

## Postscript
This ADR is a sequence of bets, not a specification. Phase 1's bet is "auth + observability before anything else"; Phase 2's bet is "polish unlocks adopters"; Phase 3's bet is "phone-cameras are a real thing, not just a concept ADR." Each bet is falsifiable inside its own phase. By day 90 we know which bets paid out and which didn't, and the next plan reflects that.
