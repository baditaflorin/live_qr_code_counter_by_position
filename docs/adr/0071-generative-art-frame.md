# ADR 0071 — Generative art frame: every participant gets a unique surround

## Status
Proposed (depends on ADR 0068 badge composition).

## Context
ADR 0068 turns the badge into a designed object. It makes every badge in a workshop *visually coherent* — same template, same palette. What it does *not* do is make every badge *unique*.

A workshop produces 100 badges that look like 100 *the same*. That's the convention for branded swag — uniformity is the brand. It is the *wrong* convention for a workshop whose entire premise (per the slide deck) is *one hundred individuals becoming a hundred witnesses*. Uniformity erases the very thing we're trying to celebrate.

Generative algorithms are the cheapest available way to make every badge unique while keeping all badges visually coherent. Same generator + same palette + different seed (the participant's marker ID) = a workshop's worth of one-of-a-kind objects, all clearly *of the same family*.

## Decision
A `generative_frame` field in the badge template (ADR 0068) selects an art generator from a small library; the participant's marker ID seeds it deterministically.

**Frame library** (`printable/generative.py`):

| Generator      | What it draws                                                 | Vibe                  |
| -------------- | ------------------------------------------------------------- | --------------------- |
| `voronoi`      | Voronoi cell tessellation; cell density scales with badge size | Crystalline, modern   |
| `mandala`      | Radial repeated motif; rotation + secondary palette derive from ID | Meditative, ornate    |
| `flow_field`   | Organic curving lines; turbulence seeded from ID              | Wind, water, breath   |
| `fractal_tree` | Branching pattern from a single root; angle + depth from ID   | Botanical, generative |
| `stippled`     | Fine dots forming an abstract gradient; pattern seeded from ID | Letterpress feel      |
| `constellation`| Star-cluster pattern with connecting lines; positions from ID  | Astronomical          |

**Determinism.** Same `marker_id` + same generator + same palette → byte-identical SVG every time. A participant who loses their badge and gets it reprinted gets *the same* unique frame. The frame is part of their identity in this workshop.

**Quiet-zone respect.** The generator draws *only outside* the marker's quiet zone. The bounding box and quiet zone are passed in as constraints; the generator clips. No matter how chaotic the visual, the marker stays detectable.

**Multi-marker coherence (ADR 0049).** A participant with 3 markers (hat, chest, back) sees the *same generative surround* on each badge — same generator, same seed, the marker ID changes but the surround derives from the *participant's* primary id, not the per-marker id. Their kit feels like one designed family, not three separate badges.

**Reflection card integration (ADR 0017).** The participant's reflection card gets a small reproduction of their generative frame as a header decoration. The frame becomes the participant's visual signature for the workshop.

**Curation pass.** A few specific marker IDs produce visually unfortunate generative output (a fractal tree that's almost empty, a mandala that's nearly featureless). The bulk-print pipeline runs a quality scorer (lacunarity, edge density) and re-rolls the generator with a perturbed seed for IDs that score below threshold. Result: every printed frame meets a minimum aesthetic bar.

## Consequences

**Positive:**
- 100 unique objects, one workshop. Every participant has *theirs* — not just *a*.
- Generative art is a cheap, well-understood domain — the library is a few hundred lines of Python; aesthetic upside is large.
- Combined with ADR 0072's material kit, the participant's chest patch isn't just a tracking tag — it's *their* one-of-a-kind workshop tattoo, in fabric.

**Negative:**
- Print-time generation is slower than static templates. Mitigation: cache generated frames per ID; bulk-print pre-renders.
- A generator produces visually polarising output — some participants love the mandala, others find it busy. Mitigation: the workshop sponsor picks *one* generator per kit; participants don't choose individually.

**Risks:**
- A generator produces output that bleeds into the quiet zone despite the constraints (a bug, an edge case). Mitigation: every generated frame goes through a quiet-zone-clip verifier before bulk-print; the badge-detection test (ADR 0068) re-detects the rendered marker post-generation.
- Generative aesthetic doesn't fit some workshops (a corporate gathering may want uniform branding). Mitigation: the generative frame is *opt-in*; templates without `generative_frame` produce uniform badges.

## Alternatives considered
- **Hand-illustrated badges per participant.** Beautiful, doesn't scale at all.
- **Pick from a small library of pre-made frames** (5–10 designs, randomly assigned). Cheaper; each frame appears 10–20 times in a 100-person workshop; loses the *one-of-a-kind* property.
- **Skip the layer.** Functional badge stays functional; souvenir value stays low; uniformity wins.

## Postscript
The phrase that drove this ADR: *"a hundred strangers cannot become a hundred witnesses by accident"* (slide 4). Uniform badges are an *accident* — a default. Generative art per badge is the small intentional gesture that says: *we know you are not interchangeable. The system knows it. Even your tracking tag knows it.*
