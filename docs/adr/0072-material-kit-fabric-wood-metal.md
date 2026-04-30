# ADR 0072 — Material kit: fabric patches, wooden discs, lapel pins

## Status
Proposed (depends on ADR 0049 multi-placement, ADR 0056 hardware kit).

## Context
Print-on-paper is the cheapest medium for a badge. It is also the cheapest *looking*. For a one-night workshop, paper is fine — disposable, replaceable, low-stakes. For the **slide deck's five-day arc**, paper is wrong. By Day 5 the participant has worn this badge for a hundred and twenty hours, looked at it before bed, packed it in a wash bag, lost it, found it. Paper makes the workshop feel *scheduled*. Material that survives a week makes it feel *worn-in*.

The marker doesn't care what it's printed *on* — only that the geometry is preserved and contrast is sufficient. An embroidered fabric patch detects identically to card-stock when the thread density is right. So does a laser-engraved wooden disc, an enameled lapel pin, a screen-printed cotton patch, or a printed acrylic acetate.

This ADR is the upgrade path from *paper* to *thing the participant wants to keep*.

## Decision
Document a **material ladder** with detection-tested options and per-material calibration samples.

| Material                         | Best for                                                | Detection notes                                          | Lead time |
| -------------------------------- | ------------------------------------------------------- | -------------------------------------------------------- | --------- |
| **Card stock (default)**         | Most workshops, all tiers                               | Baseline; everything works                               | none      |
| **Embroidered fabric patch**     | Sewn onto hats, lanyards, chest patches; week-long wear | Detection works; thread thickness limits cell size — minimum patch ~10 cm at `DICT_4X4_250` | ~14 days  |
| **Screen-printed cotton patch**  | Cheaper than embroidered; same wearability             | Detection works; ink saturation matters; calibrate per print run | ~7 days   |
| **Laser-engraved wood disc**     | Lapel badges; ADR 0049 chest+back markers              | ~85 % detection; needs ~1.5× larger cell size; *beautiful*; survives anything | ~10 days  |
| **Enameled metal pin**           | Final-day take-home souvenir                           | Works; quality varies by manufacturer; calibration sample required before bulk order | ~28 days  |
| **Printed acrylic acetate**      | Translucent badges; backlit by venue lighting          | Works double-sided; enables 360° viewing without flipping the badge | ~14 days  |
| **Iron-on transfer**             | Participants apply to their own clothing               | Works; transfer quality varies; lower-end of detection rate | ~7 days   |

**Calibration samples.** A `printable/material-samples/` directory commits one printed-on-each-medium reference marker. Each sample carries:

- A photograph of the printed sample under typical workshop lighting.
- A re-detection test result (mean confidence, mean reproj error per ADR 0048).
- The supplier, order date, and per-unit cost (so the next operator orders the same thing cheaply).
- Any quirks of the medium (e.g., *"Material X loses 3 % detection at 60 °C from a hot iron — laundering fine, ironing not"*).

**Nightly re-detection** (per ADR 0059 test infrastructure). The committed material samples are re-detected nightly against the current detector; any drift surfaces as a CI signal. A new OpenCV release that breaks fabric-patch detection is caught in 24 hours.

**Tier 3 hardware kit (ADR 0056) default mix:**

- Hat marker: **card stock** in a pre-fabricated baseball cap pocket. Cheap, replaceable mid-workshop if it gets damaged.
- Chest + back markers: **embroidered fabric patches** on a sewn lanyard. Durable for the week; survives showers, sweat, hugs.
- Final-day souvenir: **enameled metal pin** handed out at the closing ritual. The pin is *the* keepable artefact — *"I was at this workshop"* in a form that survives travel.
- Workshop sponsor option: **laser-engraved wood disc** for the chest patch, for sponsors with a specific aesthetic ask. ~3× cost of embroidery, dramatic visual upgrade.

**Bulk-order pipeline.** A `printable/orders/` workflow:

- Operator picks workshop config (palette per ADR 0070, generative frame per ADR 0071, ornament style per ADR 0069).
- Pipeline emits per-medium production-ready files: SVG for embroidery, vector for laser, raster for pins.
- Generates a one-page *order brief* with quantities, supplier info from `material-samples/`, and target dates.

## Consequences

**Positive:**
- The participant on Day 5 is wearing a small object — fabric patch over their heart, a metal pin lapel — that they'll pack for the journey home. The workshop's emotional close gains a physical artefact that wasn't there before.
- Tier-3 workshops differentiate themselves from Tier-1 not just by camera count but by *the participant's wearable kit*. The system gains a budget-tier visible to the room.
- The detection-rate test for each material catches ordering mistakes (a supplier ships a thinner-thread embroidery that detects badly) before the workshop, not at the workshop.

**Negative:**
- Lead times. Embroidery (14 days), pins (28 days). Workshops with tight schedules drop back to card stock. Mitigation: ADR 0056's three tiers reflect what's orderable on what timeline.
- Cost. A 100-person Tier-3 workshop with embroidered patches + pins runs ~$15–25 per participant. Real money. Mitigation: the budget per workshop is sponsor-decided; the system supports the cheap path equally well.

**Risks:**
- Material variation introduces detection noise mid-workshop (a participant's patch is a slightly different batch). Mitigation: per-batch calibration sample is committed before bulk order; ADR 0036 telemetry surfaces per-marker detection-rate dips so a misbehaving batch is caught.
- A participant's patch falls off (sewing failure, adhesive failure). Mitigation: the workshop kit ships +5 % spares; the operator hands a replacement in <30 seconds.

## Alternatives considered
- **Card stock only.** Cheap, unmoving. The default for most workshops; this ADR is the *upgrade*, not the requirement.
- **Skip material kit, focus on graphic design only** (ADRs 0068–0071). Fine. Material is a *texture* upgrade on top of the design upgrade — they compose.
- **Bespoke hand-made badges per participant.** Beautiful, doesn't scale.

## Postscript
This is the most *physical* ADR in the set. Everything else is bytes; this is fabric, wood, metal, ink. The system's destination (ADR 0039's wooden box) makes its first appearance here — the wooden box is what *holds* the material kit. The kit is what the participant takes home.
