# ADR 0038 — 🖤 Black Hat · Premortem & runbook

> *Black Hat: caution, judgment, risk. What can go wrong? What is this system's worst day?*

## Status
Proposed.

## Context
We have 35 ADRs of *features* and zero documented *failure responses*. The first time the WS connection dies mid-snapshot, the operator improvises. The first time the camera disappears at 09:55 on the day of, the operator panics. The first time TLS expires under load, the workshop ends with `ERR_CERT_DATE_INVALID` on the projection.

Every workshop incident I can imagine has the same structure:
1. A small recurring failure mode (Wi-Fi craters; cert expires; DB writes block).
2. Encountered without preparation.
3. Resolved by panic, not training.
4. Postmortemed informally and forgotten by the next workshop.

That cycle is broken once: write the failures down, rehearse them in staging, link each one to a recovery procedure.

## Decision
Maintain a `deploy/RUNBOOK.md` next to [`DEPLOY.md`](../../deploy/DEPLOY.md). Each scenario follows the same structure:

```
## <Scenario name>

**Symptom.** What the operator sees.
**Probable cause.** Top 1–2 root causes ordered by frequency.
**Recovery.** Numbered steps. Cap at 7 steps; if longer, the runbook is too generous and the system needs an actual fix.
**Workshop-side workaround.** What to tell the room while you fix it.
**Prevention.** What ADR or operational change would stop this happening again.
```

Initial scenarios — the ones we know will happen:

| Scenario                                              | Frequency    |
| ----------------------------------------------------- | ------------ |
| WS connection drops mid-snapshot                      | almost every workshop |
| Camera selected but `getUserMedia` rejects            | once a quarter        |
| Wi-Fi craters during peak detection                   | once a quarter        |
| Tracking session shows zero samples after Stop        | rare, catastrophic    |
| TLS cert expires at the wrong moment                  | once, eventually      |
| Operator deletes wrong question / zone / person       | will happen           |
| Marker prints stop being detected (curling, lighting) | once per workshop     |
| `/track` accepts frames but writes none silently      | rare, masked          |
| Power loss at the host VM                             | once                  |
| ArUco dictionary at 100 % capacity (the original bug) | already happened      |

Each scenario links to a one-line audit-log query (ADR 0009) that confirms diagnosis before recovery, and to the metric (ADR 0036) that should have warned earlier.

**Quarterly chaos drill.** One team member breaks something *in staging* (network partition, DB lock, simulated cert expiry). The on-call operator walks the runbook with the clock running. The drill is recorded; failures of the runbook itself are filed as runbook bugs and fixed before the next workshop.

## Consequences

**Positive:**
- The first time something fails in production is the *second* time it's failed (the first was the drill).
- Operators arrive on the day with the runbook on their phone, not in someone's head.
- Postmortems become append-operations to a living document instead of forgotten chat threads.

**Negative:**
- Runbook drift — written once, ignored, rots into uselessness. Mitigation: every drill report dates the relevant section; entries older than 12 months auto-flag for review.
- Chaos drills require a staging environment that mirrors prod closely enough — dependent on ADR 0010 workshop scoping landing first.

**Risks:**
- Drill-induced false confidence. The drill scenarios are the ones we *thought of*. The next real incident is the one we didn't. Mitigation: the runbook has a *"unknown failure mode"* generic procedure as scenario zero — establish stable observability, contain blast radius, escalate.
- A drill in staging accidentally hits prod (wrong env var, wrong terminal). Mitigation: every drill command starts with an explicit `STAGING=true` assertion; prod refuses commands with that env set.

## Alternatives considered
- **No runbook.** Current state. Each operator absorbs failures personally.
- **A monitoring dashboard alone.** Surfaces *that* something is wrong; doesn't tell anyone *what to do*.
- **A vendor runbook tool (PagerDuty, FireHydrant).** Right scale for an enterprise on-call rotation; overkill for a self-hosted facilitation tool.
