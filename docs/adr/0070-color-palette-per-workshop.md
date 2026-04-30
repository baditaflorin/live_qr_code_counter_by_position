# ADR 0070 — Color palette per workshop: the marker doesn't have to be black

## Status
Proposed (depends on ADR 0068 badge composition).

## Context
ArUco's high-contrast convention is *black-on-white*. The detector actually requires *high contrast*, not specifically black-on-white. A deep-navy mark on warm cream paper, or forest green on linen, can detect identically — and **looks like part of the workshop's chosen palette** instead of a black-and-white anomaly stuck to someone's chest.

The accessibility-design world already has a metric for whether two colors have enough contrast to be read: **WCAG contrast ratio**. The standard for legibility is ≥ 4.5:1. ArUco needs roughly the same — slightly more forgiving in good light, slightly stricter under noise. Anything that passes WCAG-AA passes ArUco detection in well-calibrated conditions.

## Decision
Allow per-workshop two-color palettes for marker rendering.

**Palette declaration.** A workshop's badge template (ADR 0068) declares:

```yaml
ink_color:    "#1a2840"   # deep navy (replaces black)
paper_color:  "#f7ecd2"   # warm cream (replaces white)
```

The marker is rendered with these colors. The badge frame, sigil, and decoration may use any palette; only the marker itself + its quiet zone are constrained to the (ink, paper) pair.

**Detection pipeline change.** A small per-camera *color-to-grayscale* pre-process:

```python
# Map the workshop's ink_color to dark and paper_color to light before the
# stock ArUco threshold pass. One ~1 ms color projection per frame.
gray = project_to_axis(frame_bgr, paper_color, ink_color)
detector.detectMarkers(gray)
```

Per-workshop palette is loaded at session start; the projection axis is precomputed.

**Palette validation.** The badge generator refuses palettes whose WCAG contrast ratio is below 4.5:1, with an explicit error message:

> *"Palette `forest_too_low` has contrast 3.8:1 (WCAG-AA requires 4.5:1). Detection will be unreliable. Increase the lightness gap between `ink_color` and `paper_color`."*

**Default palettes.** Three ship with the repo:

| Palette name | Ink color    | Paper color  | Vibe                                |
| ------------ | ------------ | ------------ | ----------------------------------- |
| `default`    | `#000000`    | `#ffffff`    | Stock; universal                    |
| `czocha`     | `#1a2840`    | `#f7ecd2`    | Deep navy on parchment; medieval    |
| `forest`     | `#2d4a2d`    | `#ebe2cf`    | Moss on linen; outdoor / retreat    |
| `noir`       | `#161616`    | `#e8e4d8`    | Ink on bone; editorial minimalism   |
| `terracotta` | `#5c2818`    | `#f4ddc4`    | Earthy red on sandstone; warm       |

Each comes with a tested calibration sample committed to `printable/palette-samples/` and a nightly detection test (per ADR 0059).

**Workshop sponsor flow.** ADR 0030's per-workshop kit gains palette parameters. The sponsor picks a palette in the kit editor, sees a live preview, runs the contrast check, ships the badges. Detection-rate is verified against a recorded calibration video from the venue.

## Consequences

**Positive:**
- Badges integrate visually into the workshop's chosen aesthetic. A Czocha badge in deep-navy-on-parchment reads as *of the room*, not against it.
- Per-workshop palette is a small lever with an outsized aesthetic effect. The same system feels different to a different cohort.
- The 4.5:1 contrast check protects detection without forcing the designer to think about the math.

**Negative:**
- One extra ~1 ms of pre-process per frame. Within ADR 0035's CPU envelope; trivial.
- Some color-blind participants find specific palette pairs hard to visually parse (the colors *detect* fine; the *human* readability of the badge name suffers). Mitigation: palette pairs are designer-curated; the `verify_template.py` step in ADR 0068 includes a color-blind simulation pass.

**Risks:**
- Low-contrast palettes detect badly under poor venue lighting (sodium, fluorescent flicker). Mitigation: the contrast check is a *floor*, not a guarantee; the operator handbook (ADR 0060) covers lighting do's and don'ts; ADR 0036 telemetry catches per-camera detection-rate drops live.
- Print fidelity — a deep navy that prints as muddy black on cheap printers undermines the design. Mitigation: the calibration sample is the print *test*; if the printer can't hit the palette, the operator falls back to `default`.

## Alternatives considered
- **Stay black-on-white forever.** Universal. Ugly with most rooms.
- **Allow arbitrary multi-color markers** (e.g., red ink, blue ink, green ink in different cells). Tempting; breaks the binary-ArUco assumption fundamentally and would require a custom detector.
- **Per-participant palette** (each person picks their own colors). Operationally painful at scale; loses workshop visual cohesion.
