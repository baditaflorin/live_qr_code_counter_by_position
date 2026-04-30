# Architecture Decision Records

One decision per file, status `Proposed` until acted on. Each ADR is self-contained — read in any order, but several reference earlier ones (noted in the Status section).

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0001](0001-bearer-token-auth.md)              | Bearer-token auth on state-mutating routes              | —          |
| [0002](0002-alembic-migrations.md)             | Adopt Alembic for schema migrations                     | —          |
| [0003](0003-floor-homography.md)               | Per-camera floor homography for real-meter proximity    | —          |
| [0004](0004-marker-tracker.md)                 | Stateful marker tracker with temporal smoothing         | —          |
| [0005](0005-multi-camera-fusion.md)            | Multi-camera fusion via floor-plane merge               | 0003, 0004 |
| [0006](0006-presenter-mode.md)                 | Presenter mode at `/present`                            | —          |
| [0007](0007-csv-roster-import.md)              | CSV roster import + bulk marker assignment              | —          |
| [0008](0008-tracking-timeline-replay.md)       | Tracking-session timeline replay UI                     | —          |
| [0009](0009-audit-log-and-structured-logs.md)  | Audit log + structured request logs                     | 0001       |
| [0010](0010-workshops-backups-retention.md)    | Workshop scoping, backups, retention                    | 0001, 0002 |

**Suggested implementation order** (smallest blast radius first, biggest leverage last):

1. **0002** — get migrations in place before any more schema churn (10 min).
2. **0001** — close the auth hole now while traffic is local-only (an afternoon).
3. **0009** — audit-log goes in cheap once auth lands; gives forensics for everything that follows.
4. **0006** — presenter mode is pure frontend; ships value to the next workshop with no backend risk.
5. **0007** — CSV import; biggest UX win for actual workshop setup.
6. **0004** — marker tracker; visible jitter goes away.
7. **0003** — homography calibration; unlocks meaningful proximity.
8. **0008** — timeline replay, reusing 0003's floor coords.
9. **0010** — workshop scoping + retention; right-sizes the data layer.
10. **0005** — multi-camera fusion; the most ambitious one, easiest after everything else is in place.
