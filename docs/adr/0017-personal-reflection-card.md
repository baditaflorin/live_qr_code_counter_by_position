# ADR 0017 — Personal reflection card per participant

## Status
Proposed (depends on ADR 0010 workshop scoping for cross-day data).

## Context
A participant leaves a 5-day workshop with memories and maybe a journal. The system has, by Day 5, ~30 hours of dense data per person — every stand they took, every cluster they were in, every snapshot they appeared in. None of it goes home with them.

The slide deck talks about "what we capture becomes the closing reel of Day 5" — that's a *group* artifact, projected once, then gone. The personal artifact is missing. The marker card itself (printed for ADR 0011's reasons) goes in a pocket and gets thrown away.

Workshops at this caliber have always produced one-page handouts at the end. The data already exists to make that one-page handout *about each individual* rather than generic.

## Decision
At session end (manual trigger or scheduled at workshop close), generate a one-page **A6 reflection card per participant** as a printable PDF.

Each card contains:

- **Identity strip** — name, day, and a small reprint of their personal marker. The card is also a souvenir of the marker they wore.
- **Stand timeline** — a tiny strip-chart showing where they stood across the night's questions (zone label vs. time). Reads at a glance: "I was on the 'Yes' side most of the time, but I broke for question 7."
- **Top 3 partners** — the three markers they spent the most time clustered with, anonymised by default. Shown as: *"You stood longest with: A · B · C"*. With explicit consent at registration, names appear instead of letters.
- **One quiet stat** — the *single* most-vulnerable question they stood for, surfaced as: "Tonight, your body answered closest to: 'I would call a friend at three in the morning.'"
- **Outlier moment** — if they were alone in a zone or the lone hinge in a question, the card calls it out: *"On question 4, you stood alone. That mattered."*
- **Blank panel** — half the back of the card is empty, with a single prompt: "Write one thing you'll remember." The card is a thing they fill in too.

Implemented in [`backend/markers.py`](../../backend/markers.py)'s Pillow + reportlab stack — `render_reflection_pdf(workshop_id, person_id)` returns the bytes; a batch endpoint emits one big PDF for the whole roster.

## Consequences

**Positive:**
- The workshop's data becomes a personal artifact, not just a facilitator's report. Participants leave with something concrete to take home.
- The card is the natural object to hand each participant alongside their marker — they get it as they hand the marker back.
- Self-completion (the blank panel) makes it *theirs*; it survives in a pocket better than an emailed PDF would.

**Negative:**
- Design effort. A bad card feels worse than no card at all. Layout and typography matter; a programmer's PDF is not enough.
- Print logistics: printing 100 cards on the spot needs a colour printer at the venue.

**Risks:**
- Privacy: showing "who you stood next to most" is sensitive even when anonymised by letters. Mitigation: anonymise by default; opt-in to reveal names (collected at registration); never include "who you avoided" or anything punitive.
- Misinterpretation: "you stood alone on question 4" could land as praise or judgment depending on context. Mitigation: use only neutral language ("that mattered") and pair with the slide-deck framing ("the person at the edge is the gift").

## Alternatives considered
- **Email digest only** — loses the physical artifact; nobody opens these.
- **Group reel only** (already covered by slide deck and ADR 0019) — collective; doesn't substitute for individual.
- **Live web link to a personal page** — fewer than 10 % of attendees would visit; loses the takeaway moment.
