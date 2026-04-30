# Architecture Decision Records

One decision per file, status `Proposed` until acted on. Each ADR is self-contained — read in any order, but several reference earlier ones (noted in the Status section).

## Platform & ops

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0001](0001-bearer-token-auth.md)              | Bearer-token auth on state-mutating routes              | —          |
| [0002](0002-alembic-migrations.md)             | Adopt Alembic for schema migrations                     | —          |
| [0009](0009-audit-log-and-structured-logs.md)  | Audit log + structured request logs                     | 0001       |
| [0010](0010-workshops-backups-retention.md)    | Workshop scoping, backups, retention                    | 0001, 0002 |

## Detection & geometry

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0003](0003-floor-homography.md)               | Per-camera floor homography for real-meter proximity    | —          |
| [0004](0004-marker-tracker.md)                 | Stateful marker tracker with temporal smoothing         | —          |
| [0005](0005-multi-camera-fusion.md)            | Multi-camera fusion via floor-plane merge               | 0003, 0004 |

## Operator UX & workflow

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0006](0006-presenter-mode.md)                 | Presenter mode at `/present`                            | —          |
| [0007](0007-csv-roster-import.md)              | CSV roster import + bulk marker assignment              | —          |
| [0008](0008-tracking-timeline-replay.md)       | Tracking-session timeline replay UI                     | —          |

## Control markers — the room as the interface

These five all rest on the same idea: reserve a slice of the ArUco dictionary
as **system commands**, printed on cards. The operator runs the show by holding
cards up to the camera instead of clicking a laptop.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0011](0011-reserved-control-marker-ids.md)    | Reserve top 16 dictionary ids for system commands       | —          |
| [0012](0012-auto-calibration-corner-markers.md)| Auto-calibration via four floor-corner markers          | 0003, 0011 |
| [0013](0013-wand-zone-authoring.md)            | Author zones by walking the floor with a "wand" marker  | 0011, 0012 |
| [0014](0014-marker-driven-session-control.md)  | Hands-free session control: start/stop/next/snapshot    | 0011       |
| [0015](0015-anchor-drift-detection.md)         | Anchors detect camera drift and self-recalibrate        | 0011, 0012 |

## Suggested implementation order

Smallest blast radius first, biggest leverage last:

1. **0002** — get migrations in place before any more schema churn (10 min).
2. **0001** — close the auth hole now while traffic is local-only (an afternoon).
3. **0009** — audit-log goes in cheap once auth lands; gives forensics for everything that follows.
4. **0006** — presenter mode is pure frontend; ships value to the next workshop with no backend risk.
5. **0007** — CSV import; biggest UX win for actual workshop setup.
6. **0011** — control-marker infrastructure. Cheap on its own; unlocks the next four.
7. **0004** — marker tracker; visible jitter goes away.
8. **0014** — hands-free session control. First payoff of 0011 — the operator stops touching the laptop.
9. **0003** — homography model + manual calibration UI.
10. **0012** — auto-calibration via corner markers. Replaces 0003's manual UX with a 30-second floor-walk.
11. **0015** — drift detection on top of 0012's anchors. Catches silent-failure mode.
12. **0013** — wand-based zone authoring. Best done after the operator's tooling and detection are mature.
13. **0008** — timeline replay, reusing 0003's floor coords.
14. **0010** — workshop scoping + retention; right-sizes the data layer.
15. **0005** — multi-camera fusion; the most ambitious one, easiest after everything else is in place.
