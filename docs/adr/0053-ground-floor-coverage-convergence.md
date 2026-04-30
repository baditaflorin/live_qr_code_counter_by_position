# ADR 0053 — Ground-floor coverage convergence: the room solves its own coverage

## Status
Proposed (depends on ADR 0034 planner, ADR 0051 phone cameras, ADR 0052 dynamic mesh).

## Context
ADR 0034 is a **top-down** planner: an operator sits at a laptop *before* the workshop, fiddles with virtual camera positions on a floor plan, and tries to colour the diagram green. That's right for a six-camera fixed installation. It is exactly wrong for the phone-camera world introduced in ADRs 0051 / 0052.

When 30 phones are joining, leaving, and re-aiming continuously, "the plan" is meaningless. What matters is "what coverage do we *actually have*, right now?" — and when the answer is "we have a blind spot in the back-left", the question becomes "which phone is closest to that blind spot, and can we ask its holder to turn?"

The user's framing: *can we make convergence from the ground floor?* — yes, by treating coverage as a **feedback loop** between sensor and asker, not a precomputed static plan.

## Decision
Add a **live coverage planner** at `/admin/coverage` and a **convergence ping** loop that nudges specific phones to fill specific gaps.

**Live coverage diagram.**

- Reuses ADR 0034's SVG floor diagram, redrawn every 1 s from the active-camera floor projections (per ADR 0050).
- Cell colouring:
  - **Green**: ≥ 2 cameras cover this floor square at acceptable resolution (per ADR 0031 thresholds).
  - **Yellow**: exactly 1 camera. No redundancy — losing that camera blinds the cell.
  - **Red**: 0 cameras. Blind spot.
- Numbers: `coverage 87 %  ·  redundant 64 %  ·  blind spots: 2 (3.4 m², 1.1 m²)`.

**Coverage debt.**

A floor cell that's been red for **> 10 seconds** accumulates *coverage debt* — a small score per cell, growing the longer it stays uncovered. Total debt is published on `/admin` as a single number; an operator wants this near zero.

Coverage debt is the alarm clock that drives the convergence loop.

**Convergence pings.**

When a cell's coverage debt exceeds a threshold, the system picks the **best candidate phone** — currently active, with this cell's gap inside its physical reach, currently aimed away from the gap. The candidate's UI shows a directional arrow:

> *"Coverage gap to your left — pan camera 30° → "*

The arrow updates in real time as the phone re-aims; when the phone's view starts including the gap cell, the arrow disappears, the cell's debt resets, and the participant gets a small acknowledgement (a green tick, or the contribution meter ticks up).

If no candidate phone exists that *could* cover the gap from its current position, a softer alert goes to `/admin`: *"Blind spot in back-left has had 0 cameras for 25 s. Consider asking someone to walk over with their phone."* The operator decides whether to interrupt the room.

**Convergence cadence.**

- Coverage diagram updates: 1 Hz.
- Convergence pings: at most 1 active per phone (no spamming a single phone with multiple pings).
- A phone that ignores 3 consecutive pings gets a 60-second cooldown — maybe its holder is mid-conversation.

**Comparison to ADR 0034.**

ADR 0034 is the *blueprint* — pre-event planning. ADR 0053 is the *runtime* — measured coverage with a feedback loop to fix gaps. They co-exist: an operator can use ADR 0034 to lay out the *fixed* gallery cameras, and let ADR 0053 close the rest of the gaps with phones in real time.

## Consequences

**Positive:**
- The planner becomes an *active* tool, not a *predictive* one. Operators see real coverage; participants see how to help; gaps close themselves.
- The slide deck's *"the gallery sees them"* line gets a literal new meaning — the gallery, the floor, every phone in the room, all contributing to a coverage that the system continuously rebuilds.
- "Bottom-up convergence" is now a thing the system *does*: each blind spot is a request the room collectively answers.

**Negative:**
- A noisy convergence loop can be itself disruptive — phones flashing arrows during a vulnerable round breaks the slide deck's silence. Mitigation: the convergence loop respects per-question `silent_mode` (ADR 0016); during privilege-walk formations no convergence pings fire.
- The "best candidate phone" computation is non-trivial when many phones are partially-aimed at the gap. Mitigation: pick by smallest pan angle to cover the gap; ties broken by highest current contribution score (ADR 0052).

**Risks:**
- A holder who doesn't speak the system's language follows the arrow but misunderstands. Mitigation: arrows are visual-first, not text-dependent; the briefing covers them in 30 seconds.
- Coverage debt thrashes when phones rapidly re-aim. Mitigation: 5-second hysteresis on debt accumulation; pings only fire when debt has been steady for >10 s.
- A persistent gap with no one nearby — the convergence loop can't fix structural problems. Mitigation: that's *correct*; the alert escalates to the operator who can ask someone to walk over.

## Alternatives considered
- **Operator-only coverage view, no convergence pings.** The operator becomes the dispatcher, manually asking participants to re-aim. Works but consumes the operator's attention; the convergence loop is *the* automation that makes phone-cameras viable for a busy workshop.
- **Auto-pan via gimbal.** Hardware solution, expensive, brittle, anti-flexibility. The whole point is participants are the gimbals.
- **Static blueprint only (ADR 0034).** Predicted coverage; doesn't adapt to dropouts or reconfiguration during the session.
