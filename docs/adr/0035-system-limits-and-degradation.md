# ADR 0035 — Hard system limits and graceful degradation

## Status
Proposed (touches every other ADR).

## Context
Every system has a "supported envelope" — the conditions under which it works as designed. Outside that envelope it doesn't do nothing; it does *something subtly wrong*. The current system has no documented envelope and no detection of envelope-exceeded conditions. Concretely, the limits in play right now:

| Resource                                  | Hard limit                                | Symptom past limit                              |
| ----------------------------------------- | ----------------------------------------- | ----------------------------------------------- |
| `DICT_4X4_250` size                       | 250 marker IDs                            | `_next_aruco_id()` hands out invalid IDs (already broke once, see [`backend/main.py`](../../backend/main.py)) |
| Person-marker capacity (after ADR 0021)   | 202 IDs (250 − 16 operator − 32 participant) | New people can't be added; current error message points to dict change |
| Concurrent WS clients                     | ~10 (single-process uvicorn)              | New connections queue, get rejected, or starve existing ones |
| `tracking_samples` table size             | ~20 M rows on SQLite before perf degrades | Reports take minutes; insert latency rises     |
| Bulk markers PDF generation               | ~150 markers per request before timeout   | 500 from gateway; partial PDF                  |
| Frame-archive disk (ADR 0019)             | ~250 MB/session @ 1 fps × 90 min          | `/data` fills, container OOMs                  |
| ArUco detection CPU at 4K                 | ~40 ms/frame on a Mac M-series core       | At >25 fps the WS handler can't keep up        |
| Calibration accuracy at floor edges       | ~5 % position error past 12 m from camera | ADR 0003's homography degrades; clusters wrong |
| Audit log retention (ADR 0009)            | grows unbounded if retention disabled     | DB bloat                                        |

The system silently does the wrong thing past every one of these. Users find out when a workshop fails.

## Decision
Three things, applied as a package.

1. **Document the envelope.** A single `/api/system/limits` endpoint returns the configured + observed values, side by side. `/admin` renders this as a **System health** panel: each limit either green (well within), yellow (within 80 %), or red (exceeded). The numbers are honest — if the envelope is "100 people, single 4K camera", that's what the page says.

2. **Hard guards at the boundaries.** Each subsystem checks its limit before the user-facing operation:
   - Marker batch creation refuses past dictionary capacity (already shipped, the original 500-bug fix).
   - WS handshake refuses new clients past `MAX_WS_CLIENTS` (default 8) with a clear error rather than silent queueing.
   - Tracking-samples nightly job warns at 10 M rows, hard-suggests retention pruning at 15 M.
   - PDF generation streams pages instead of buffering — no per-request hard cap, but a memory cap that drops the request cleanly past 500 MB intermediate state.
   - Calibration UI shows the resolution warning from ADR 0031 in the same panel.

3. **Degradation strategies, declared.** When a soft limit is hit, the system degrades along a *named* path rather than failing:
   - **Bandwidth limited** (ADR 0033): drop JPEG quality, then frame rate, then resolution.
   - **CPU limited** (detection > capture rate): reduce capture rate, log a warning per minute.
   - **Disk limited** (frame archive): stop archiving frames, alert operator, keep tracking samples (which are tiny by comparison).
   - **DB limited** (tracking samples): refuse to start a new tracking session until retention pruning runs.

Every degradation event is audit-logged (ADR 0009) so the post-event review can see *exactly* when and why the system stepped down.

## Consequences

**Positive:**
- Operators can plan against a known envelope. "We're running 80 people, single 1080p camera, conference Wi-Fi" maps to a clear yellow/green/red prediction before doors open.
- Failures are loud and labelled. "Bandwidth limited at 14:32" is debuggable; "the live page started lagging" is not.
- The envelope expands deliberately: when ADR 0005 multi-camera ships, the limits panel shows new numbers reflecting the increased capacity.

**Negative:**
- Each limit needs an honest measurement, not a vibe. Some are hardware-dependent (CPU per frame at 4K varies by laptop) — those are *runtime-observed* and shown as the rolling 60-second median.
- The "System health" panel is yet another thing in `/admin` — but it's the *right* place for ops-truth.

**Risks:**
- A red light on the limits panel during a workshop is itself a stressor for the operator. Mitigation: the panel is operator-only; participants and projection routes don't see it.
- Soft-limit thresholds (80 % yellow) are heuristics; operators with unusual setups will see false yellow. Mitigation: thresholds are configurable per Camera/Workshop.

## Alternatives considered
- **No limits page; let the system fail in production.** Current state. Costs a workshop occasionally.
- **Hardcode pessimistic limits.** Excludes legitimate stretch configurations.
- **External monitoring service.** Right answer for a multi-tenant SaaS; overkill for a self-hosted single-operator tool.

## Postscript
The first 30 ADRs describe what the system *should do*. This one describes *when it stops working*, which is the other half of an honest design.
