# ADR 0040 — 💚 Green Hat · Twelve wild ideas, on the record

> *Green Hat: creativity, alternatives, "what if". Generate without judging.*

## Status
Proposed (none of the twelve is itself a decision; this ADR is a decision *to remember them*).

## Context
Most discarded ideas are discarded *silently*. They become tribal knowledge ("we tried that, it didn't work"; "that won't work because—"; "we considered that") that nobody can verify, supersede, or revive when conditions change. The space of *not-yet-implemented* ideas is much bigger than the space of *currently-implemented* ones, and we have no inventory of it.

The other 35 ADRs are *implementable* — each has a concrete decision attached. Wild ideas tend to fail the implementability test on first read and get filtered out, even when six months later they would be obviously the right next step.

Worth committing twelve to paper, knowing eleven will look bad in retrospect.

## Decision
Twelve ideas. Each gets one paragraph, one *might-be-magical* line, one *might-be-terrible* line. None is promoted to its own ADR until evidence demands it.

1. **AI co-facilitator.** A small local model reads cluster events live and suggests next-question candidates from the active deck — whispered in `/admin`, never to the room.
   *Magical*: the operator gets a quiet sparring partner.
   *Terrible*: the model normalises the room toward whatever pattern its training data thinks is "good".

2. **AR phone overlay.** A participant points their phone at the room; arrows point at people they haven't met. Mingling becomes a quest.
   *Magical*: gamification makes the awkward part easy.
   *Terrible*: phones in hand kill the slide-deck "embodiment" thesis.

3. **Generative ambient music.** Cluster size → tempo. Cluster count → harmony. The room scores itself in real time.
   *Magical*: the soundscape *is* the room.
   *Terrible*: continuous music drowns out the silences the workshop is built around.

4. **Per-question soundscape library.** Each question has an associated 90-second ambient track authored by the operator. Composes with ADR 0016.
   *Magical*: the same 30 questions feel new each time because the soundscape changes.
   *Terrible*: now a workshop also requires audio production.

5. **Outlier prediction.** A small model predicts who is likely to be the outlier on the next question, given their stand history. Pre-computes the operator's pick.
   *Magical*: the operator's outlier-pick gets a pre-flight check.
   *Terrible*: the room's emergent behaviour gets short-circuited by a confident model.

6. **Audio "weather report".** At the end of each block a 30-second narrated summary: *"Thirty-two stood for the trust question. The room is open. Light grief in the back-left."*
   *Magical*: the room hears itself summarised in real time.
   *Terrible*: written narration exposes the system's interpretive layer to the room, which is sometimes wrong.

7. **Cross-workshop social graph.** With explicit consent, a participant who attended two workshops six months apart can see who they crossed paths with at both.
   *Magical*: the network effect of small workshops aggregating into a community.
   *Terrible*: the privacy surface area is enormous and the consent is fragile.

8. **Haptic marker badges.** A marker badge with a small vibration motor. The system pulses it briefly when its wearer is the operator's outlier-pick.
   *Magical*: a private "you've been chosen" signal that doesn't break the room.
   *Terrible*: now the marker is electronics, not just paper. Cost, batteries, sourcing, e-waste.

9. **Photogrammetric room model.** Replace the floor trapezoid with a learned 3D mesh of the actual hall. Zones become 3D regions; clusters get volumetric. Useful for halls with uneven floors.
   *Magical*: rooms with stages and balconies stop being approximations.
   *Terrible*: 90 % of workshops happen on a flat floor and don't need this.

10. **Workshop sundial.** The 90-minute exercise visualised as a literal sundial face on `/project` — the workshop's progress mapped to a slow rotation.
    *Magical*: the room sees its own pacing without a digital clock.
    *Terrible*: the metaphor charms exactly half the audience and bewilders the other half.

11. **Marker dictionary as art.** Render the entire `DICT_4X4_250` as an A1 poster — 250 little squares, each one a person who could have been. A souvenir of the workshop's full set.
    *Magical*: the kit gets an artefact of its own existence.
    *Terrible*: it's an inside joke that means nothing to a participant.

12. **Print the workshop as a poster.** An A1-sized auto-generated infographic per workshop: the cluster timeline, the witness graph, the most-raised cards, the most-witnessed person, the room's weather. Hung at the venue afterwards.
    *Magical*: every workshop produces a memorable physical artefact.
    *Terrible*: the data alone is meaningless; the design effort is huge; bad infographics are worse than none.

## Consequences

**Positive:**
- Twelve ideas survive that would otherwise have died in chat. Six months from now we can re-read and pick the one that *did* turn out to be right.
- Future-me has something to argue with. *"We thought about this."* with a date attached is more honest than *"we thought about this."* without one.
- The list is also a recruiting tool — collaborators can see what's in the imagination of the project, not just what's in the backlog.

**Negative:**
- The list bloats. Adding to it is easy; removing requires writing a *deprecation note*, which is more work than the addition was.
- Twelve more headers to scan in `docs/adr/`.

**Risks:**
- The list becomes a backlog. Mitigation: each idea is explicitly framed as *might be magical / might be terrible*, not *will ship*. Status of this ADR remains Proposed forever; individual ideas are promoted to their own ADRs (numbered separately) only when evidence justifies them.
- A wild idea sounds good in 2026, looks naive in 2028. Mitigation: that's *the point of the list* — preserved naivety is also a record.

## Alternatives considered
- **Don't write the wild ideas down.** They die silently. Worst option.
- **Write them as twelve separate ADRs.** Pollutes the numbered sequence; implies decision-readiness none of them have.
- **Maintain a separate `ideas.md` file.** Almost identical; lives outside the ADR mental model and gets less attention.
