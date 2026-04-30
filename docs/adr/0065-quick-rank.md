# ADR 0065 — Quick-rank: drop priority cards on the floor

## Status
Proposed.

## Context
*"Rank your top 3 priorities."* It's a recurring ask in every workshop. Today it's done by passing around sticky notes, gathering them, sorting them in front of everyone (slow), or by skipping the exercise altogether.

The system has cameras, position detection, and a floor coordinate frame (per ADR 0003 / 0050). Ranking should take 60 seconds and feel like a game: hand each participant a small stack of numbered cards, they walk to a designated floor area and **drop** the cards in priority order — left to right, or top to bottom — and the camera reads the spatial sequence.

Position-as-vote is what the system was built for. Quick-rank just turns the *"stand in a zone"* gesture into *"drop a card on the floor"*.

## Decision
Reserve **5 IDs** per ADR 0067 — numbered priority cards `RANK_1` through `RANK_5` — printed as a small stack each participant carries.

**Operator setup.**

1. Operator picks a *ranking question* in `/admin` (or the active question can have `mode: rank` set).
2. `/present` displays up to 5 named options:

```
1. Trust       2. Conflict      3. Story
4. Vulnerability   5. Return
```

3. The floor has a marked **ranking lane** — a long rectangle (per ADR 0026 composition cards' `silent` mode dynamics, the lane can be laid out with floor tape, or rendered virtually as a ADR 0018 `/project` overlay).

**Participant gesture.**

Each participant takes their stack of `RANK_1`–`RANK_5` cards and **places them in the lane in the order they prefer**, left-to-right meaning highest-to-lowest priority. So if their order is *Story, Trust, Vulnerability, Conflict, Return*, they place: *RANK_3* leftmost, then *RANK_1*, then *RANK_4*, then *RANK_2*, then *RANK_5*.

The cards are face-up on the floor, in a line. The camera reads the spatial order.

**System reads.**

- Detected `RANK_*` cards are sorted by their floor X coordinate (or Y for vertical lanes).
- Each card's "rank" is its position in the sorted sequence: leftmost = rank 1.
- Per-option rank is averaged across all participants. The aggregate ranking is published.

**Visualisation on `/project`:**

A live histogram for each option's rank distribution. As participants drop their cards and the camera reads them, the histogram fills in real time — every drop is visible, the room watches its preference emerge. Final ranking is announced with a brief animation.

**Cleanup.**

After the result is announced, participants pick up their cards. The operator advances `/admin`; the system clears the ranking lane.

**Variants.**

- **Top-3 only.** Participants drop only the top 3 of 5 cards; remaining cards stay in their pocket.
- **Vertical lane.** Useful for venues where the floor is irregular but a clear vertical strip exists.
- **Group-rank.** Multiple participants share a stack and drop one stack collectively as a small group's consensus.

## Consequences

**Positive:**
- Ranking exercises that today take 15 minutes resolve in 3. The ranking is *embodied* — participants walk through their own preferences, see them on the floor.
- The data is *visible during voting*, which generates social signal naturally — late-droppers see what early-droppers chose. Optionally suppressible if the workshop wants blind ranking.
- Beautiful artefact: the cluster of cards on the floor at the end of the round is itself a photograph of the room's preference.

**Negative:**
- Floor space matters. A small venue can't run a long ranking lane. Mitigation: vertical-lane variant; ADR 0034 coverage planning includes a lane-positioning step.
- Participants who can't bend / drop / kneel are excluded from this gesture. Mitigation: a chair-friendly variant uses a tabletop strip instead of a floor lane.

**Risks:**
- Cards land in the wrong order due to floor jostling. Mitigation: the camera reads continuously; final ranking is the *settled* state after a 5-second stability window.
- Participants game the spatial reading by leaving large gaps. Mitigation: gaps don't matter — only the *order* is read, not the spacing.
- Very crowded lanes (100 participants × 5 cards = 500 cards in one lane) create overlap. Mitigation: cap at 60 participants per lane; large workshops use multiple parallel lanes (one per cohort table) and aggregate.

## Alternatives considered
- **Sticky-note ranking.** The current default. Slow, doesn't scale, no data captured.
- **Phone-app ranking.** Same data, breaks embodiment, breaks the *visible group decision* property.
- **Stand-in-a-zone ranking** (zone per option). Captures only the *top* preference per person; loses the priority *order*.
