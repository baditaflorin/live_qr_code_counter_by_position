# ADR 0062 — Pulse polls: 3-second synchronised group vote

## Status
Proposed.

## Context
Operators today have two ways to read the room's opinion: the formation (people stand on a side — slow, embodied, takes 90 seconds per round) and the snapshot (records who's where right now — silent, no theatre).

Neither is a *vote*. Neither has the moment of collective release where the whole room *answers at once* and you can feel the temperature shift in three seconds.

A pulse poll is the simplest thing that delivers that: operator says *"YES, NO, or PASS — one, two, three, GO!"*; everyone raises one card from a tiny personal hand; the system reads the 30+ simultaneous raises and shows the result on screen instantly. Four seconds, room-shifting, fun.

## Decision
Reserve **6 IDs** for pulse-poll cards (per ADR 0067 budget): `PULSE_YES`, `PULSE_NO`, `PULSE_MAYBE`, `PULSE_PASS`, `PULSE_LEFT`, `PULSE_RIGHT`. Each participant carries the relevant subset on a small fan of cards (e.g., a stitched lanyard with three flippable mini-cards: yes / no / maybe).

**Operator gesture:**

1. The operator activates pulse-poll mode in `/admin` with one click — or via a control marker (per ADR 0014).
2. `/present` flashes the question (e.g., the active question's text, or an ad-hoc prompt typed in `/admin`).
3. A 3-second countdown — *3 — 2 — 1 — GO* — large on `/present`, with audio cues (per ADR 0016) on each beat.
4. **3-second vote window**: every pulse card detected during this window is counted. One card per participant — re-raises within the window are deduped.
5. **Reveal**: `/present` shows the tally with bar-chart fireworks, big numbers, animated. *YES 47, NO 12, MAYBE 8, PASS 5*.
6. The operator can immediately follow up: "say more" → returns to the conversation. Or "again" → repeats the poll on a refined question.

**`/project` choreography** (the spectacle layer):

- During the 3-second vote window, `/project` shows a **shower** — every detected pulse card paints a coloured pixel-burst at the holder's floor position, colour-coded by vote. The room *sees its own answer pour onto the floor*.
- Reveal frame freezes the pattern for 4 seconds, then dissolves.

**Schema.** A `PulsePoll` row per invocation: `(id, t, prompt, window_ms, attached_to_question_id, results_json)`. Vote rows reuse the existing `Vote` table with a `pulse_poll_id` foreign key.

**Re-vote.** The operator can press "again" within 5 seconds of a result and re-run the same poll. Vote rows from the second run replace the first (audit-logged). Useful when the room said *"wait, can we vote again?"* — common, and currently impossible to honour.

## Consequences

**Positive:**
- The room gains a *moment of collective release* every few minutes. The pulse poll is the workshop's heartbeat.
- 4 seconds beats 90 seconds for binary opinion-reads. The formation stays for embodied/spatial questions; the pulse handles "do we want to go deeper or move on?"
- The shower visual on `/project` is the kind of thing that ends up on Instagram. Cheap recruitment.

**Negative:**
- Adds 6 new card IDs and a small fan of personal cards to the participant kit. Mitigation: the fan is part of the lanyard already used for the chest+back markers (ADR 0049); minimal extra production.
- Synchronisation requires audio cues — venues with poor acoustics get garbled timing. Mitigation: the visual countdown is large and visible from anywhere in the hall; audio is a complement, not a requirement.

**Risks:**
- Late raises (after the 3-second window). Mitigation: the window has a 200 ms grace period; raises after grace are recorded but flagged `late: true` and shown to the operator as a separate count.
- Peer pressure — participants see neighbours' cards and conform. Mitigation: a "blind mode" toggle has the cards held *behind their head* during the count, results revealed only on the big screen. Optional; default off because the *visible group answer* is part of the magic.

## Alternatives considered
- **Phone-app voting.** Faster individually, no group-release moment, breaks the slide-deck embodiment thesis.
- **Hand-raise vision** (count people raising hands without cards). Possible, less reliable, no per-vote attribution.
- **Existing two-camps formation as the pulse.** Already in the system — but takes 90 s to settle. The pulse is the *fast complement*, not a replacement.
