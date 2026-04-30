# ADR 0039 — 💛 Yellow Hat · The 2028 destination

> *Yellow Hat: optimism, benefits, value. What if the system worked perfectly? What does success look like, written down?*

## Status
Proposed.

## Context
35 ADRs of next steps. Zero ADRs of *destination*.

The risk of a tactical-only ADR set is that it accumulates without coherence. ADR 41 has the same structure as ADR 4: a concrete next step. None of them tells us where we're walking *toward*. Every "yes" to the next ADR is also an implicit "yes" to a vague trajectory whose shape no one has had to defend.

A destination ADR is a mirror. Every subsequent decision can ask "does this take us closer or further?" — and an honest answer is sometimes "further", which is okay if we know it.

## Decision
Articulate the destination as it should look in **2028**, three years out. Concrete enough to argue with, soft enough that the path can vary.

By **2028**:

1. **Fifty facilitators outside the original team** are running workshops with this kit. Most of them never opened a Python file. The kit is documented, deployable, and forgivable.

2. **A thousand recorded workshops** have happened, with privacy-respecting consent, contributing to a corpus that the broader facilitation community can reason about. *"Trust questions cluster the room differently than fear questions"* is a sentence backed by data, not just intuition.

3. **Three peer-reviewed papers** cite the proximity-graph methodology — one from a sociology lab, one from a leadership-development programme, one from a theatre/performance department. The system is taken seriously as a research instrument, not just a counter.

4. **The kit ships in a wooden box.** A Raspberry Pi 5 with the system pre-loaded, four corner-anchor markers, the operator + participant card decks, a portable wide-angle webcam, a folded projector, a SIM card with a data plan. Plug into mains, open laptop, run. The download is a fallback, not the default.

5. **A public deck library.** The custom-deck mechanism (ADR 0030) has matured into a curated repository of 30+ decks: grief workshops, conflict mediation, theatre rehearsals, cohort kickoffs, school assemblies, board retreats. Each deck is attributed to its facilitator and reusable under a clear licence.

6. **The closing reel and the personal reflection card are the most-shared artefacts** of every workshop that uses the system. Participants post the reel; facilitators print the cards; both end up on walls, in journals, on LinkedIn, in dissertations.

7. **One person can run a workshop end-to-end** without a developer in the room — install, configure, calibrate, run, debrief, archive. The kit is a *tool*, not a *project*.

This is not a roadmap. It's a yardstick. New ADRs are tested against it: *does this take us toward the wooden box, or away from it?* Most should take us toward it. A few will be *deliberately* about something else (research instrumentation, multi-tenant SaaS, enterprise auth) and that's okay — the destination is one chosen lane among many.

## Consequences

**Positive:**
- Tactical decisions get a strategic reference. *"Should we add Postgres support?"* becomes a question with a clear lens: it doesn't matter unless we're heading toward enterprise multi-tenancy, which we aren't (per #4–#7, single-box self-hosted is the destination).
- The Yellow Hat exists to balance the Black Hat. The premortem catalogues what kills us; this ADR catalogues what we're *for*.
- Recruits, contributors, and partners have something to align with that isn't a feature list.

**Negative:**
- The destination is opinionated and might be wrong. *Maybe* the right destination is enterprise-SaaS facilitation analytics; this ADR says no, and that's a bet.
- A destination this concrete invites quibbles (*"why a Pi 5 specifically?"*) that distract from the core shape.

**Risks:**
- Destination drift — the ADR is written, ignored, never revisited. Mitigation: tied to ADR 0041's lifecycle; revisit the destination annually and supersede if the bet changed.
- Scope creep dressed as alignment ("this wild idea totally fits the wooden box, look"). Mitigation: bullets are concrete; alignment is an evidence question, not an interpretive one.

## Alternatives considered
- **No destination ADR.** Status quo. Tactical clarity, strategic mush.
- **A more abstract destination** ("be the leading facilitation tool"). Not falsifiable; not useful.
- **A more aggressive destination** (10,000 facilitators by 2028). Possible; not matched by current organisational capacity. Honesty matters more than ambition here.
