# ADR 0068 — Badge as designed composition: the marker is *one element*, not the whole

## Status
Proposed.

## Context
Today [`backend/markers.py`](../../backend/markers.py) renders exactly what its name says — a marker, with the participant's ID number and name in a caption underneath, on white card stock. It looks like a tracking tag because it *is* a tracking tag.

The slide deck is set in a hall whose ceilings are coffered oak, whose floors are herringbone parquet, whose gallery rails carry hand-stitched banners. The room is composed. The room is beautiful. A participant wearing a clipped photocopy is the *wrong texture* for that room — and for any workshop that takes its physical environment seriously.

The marker doesn't *have to* look like a marker. It has to *contain* a detectable marker. Everything else on the badge is design surface that we are throwing away.

## Decision
Treat the badge as a designed object with the marker as one component.

**Layered composition.** A badge is rendered from a parameterised SVG template (`printable/templates/<workshop>/badge.svg`) with five layers:

| Layer        | What it carries                                                  |
| ------------ | ---------------------------------------------------------------- |
| Frame        | Ornamental border — hand-illustrated patterns, or vector ornaments per workshop palette |
| Sigil        | Workshop logo or symbol — small, in one corner                   |
| Name         | A single chosen typeface for the workshop, set with care         |
| Color band   | A 4 mm strip that identifies cohort / day / table assignment     |
| **Marker**   | The actual detection target, sized per ADR 0031, framed by quiet zone |
| Edge motifs  | Foliage, geometric pattern, watermark — outside the quiet zone   |

The marker's quiet zone is *non-negotiable* — no decoration crosses it. Everything else is the designer's playground.

**Per-workshop templates.** Three default templates ship with the repo:

- `default.svg` — clean modern. Black + grey + accent. Inoffensive.
- `czocha-day-1.svg` — gothic-medieval. Brass + parchment palette. Heraldic frame.
- `craft.svg` — handmade, off-register prints, gentle imperfection.

Workshop sponsors fork these via ADR 0030's per-deck mechanism. Each fork goes into `printable/templates/<workshop>/`.

**Bulk-print pipeline.** The existing PDF generator extends to consume `(roster.csv, template.svg)` and emit one badge per participant — name slotted, marker rendered, sigil in place, all visually coherent.

**Detection guarantee.** A `tests/templates/test_badge_detection.py` test in ADR 0059's test layer renders every shipped template at print resolution, re-detects the marker, and fails the build if detection fails or confidence drops below 0.9. **No template ships that breaks detection.**

## Consequences

**Positive:**
- The badge stops feeling like a tracking tag and starts feeling like *a thing the participant wants to keep*. Reflection-card souvenir value (ADR 0017) compounds.
- Workshops gain a visual identity. Photographs from a Czocha session look unmistakably *Czocha*, not *generic facilitation tool*.
- The template is also a contract with the workshop sponsor — they can see what their participants will wear before doors open.

**Negative:**
- Each new template is design work, not just engineering. Mitigation: ship 3–4 strong defaults; sponsors with brand budgets fork.
- More template files in the repo. Mitigation: each template is one SVG + one preview PNG; <50 KB per workshop.

**Risks:**
- A template that looks beautiful but breaks detection (busy pattern bleeds into the quiet zone). Mitigation: the detection test catches it; the build fails before the template can ship.
- Visual fashion over function — a designer prioritises beauty over the participant's ability to read their own name on the badge. Mitigation: each template has a "name reads at 1.5 m" check at design review.

## Alternatives considered
- **Plain card (current state).** Functional, ugly. Wrong texture for any workshop that cares.
- **Hand-designed badges per participant.** Beautiful, doesn't scale beyond 20 people.
- **Single visual identity for the system.** Wrong — the system is the *instrument*; the workshop is the *song*. Each workshop deserves its own look.
