# ADR 0069 — Stylised cell ornaments: the marker doesn't have to look like a marker

## Status
Proposed (depends on ADR 0030 custom decks, ADR 0068 badge composition).

## Context
ArUco markers are convention-bound to look like 6×6 grids of black-and-white squares. The convention exists because that's what `cv2.aruco.generateImageMarker` outputs by default. The convention is fine when you accept *square = the look of the marker*; it is wrong when you want the marker to feel native to a workshop's visual language.

What the OpenCV detector *actually requires* — separate from the convention — is:

- A binary inner pattern of N×N cells with adequate Hamming distance.
- A clear quiet border around the inner pattern.
- Per-cell **brightness centroid** that the detector can read as filled vs empty.

It does *not* require that each cell be a square. A filled hexagon works. A filled six-pointed star works. A filled letter-glyph works. The detector reads centroids and brightness ratios, not iconography. The cell *appearance* is design surface.

## Decision
Generate workshop-specific *stylised* marker dictionaries.

**Cell-fill ornament library** (`printable/cells/`):

| Ornament         | Visual                          | Detection notes                                |
| ---------------- | ------------------------------- | ---------------------------------------------- |
| `square`         | Default — same as stock ArUco  | Best detection; the baseline                   |
| `circle`         | Filled disc                     | ~98 % of square; gentler look                  |
| `hexagon`        | Filled regular hexagon         | ~95 %; reads as a hex-grid                     |
| `six_star`       | Six-pointed star                | ~92 %; medieval / heraldic                     |
| `leaf`           | Stylised petal / leaf          | ~90 %; organic / botanical                     |
| `letter`         | A glyph from the participant's name | ~88 %; works at >60 px/side (per ADR 0031)  |
| `floral`         | Tiny rosette                    | ~85 %; ornamental                              |

**Generation.** A `printable/markers/styled.py` script:

1. Take a base ArUco dictionary (`DICT_4X4_250` or `DICT_4X4_1000`).
2. For each ID, render the marker as a parameterised SVG, replacing each cell's filled / empty decision with the chosen ornament.
3. Write to the bulk-print pipeline (per ADR 0049 multi-placement, ADR 0068 badge templates).

The detector still works because:

- Cell *centres* are preserved.
- Quiet zone is preserved.
- Brightness ratio (filled / empty) is preserved.
- Hamming distance of the dictionary is unchanged — only cell appearance changes.

Per-template selection: `cell_style: "hex"` in the badge template (ADR 0068) selects the ornament. The badge looks like a heraldic device, not a barcode.

**Detection-rate floor.** Each ornament style declares its **minimum recommended px-per-side**, surfaced to ADR 0031's calibration warning:

- `square`: 30 px.
- `circle`: 35 px.
- `hexagon`, `six_star`: 50 px.
- `leaf`, `letter`, `floral`: 60+ px.

A workshop choosing `floral` markers in a hall where pixel-per-marker is only 35 gets a warning at calibration time: *"this style needs 60 px/side; you're at 35; detection will be unreliable."*

## Consequences

**Positive:**
- The marker stops looking like a tracking grid and starts looking like *part of the workshop's visual language*. A "hexagon" Czocha badge reads as a heraldic seal, not a QR fragment.
- Combined with ADR 0068's badge composition, a participant's chest patch can show an embroidered six-pointed star pattern — the marker *is* the pattern.

**Negative:**
- Stylised cells detect ~5–15 % less reliably than stock squares. Acceptable when pixel-per-marker has headroom; risky at the resolution floor. Mitigation: per-style px floor surfaced as a calibration check.
- More test surface. Mitigation: each style has a `tests/cells/test_<style>_detection.py` round-trip test that prints + re-detects 50 markers; a regression in detection rate fails CI.

**Risks:**
- Beautifully-stylised markers detect great in dev (clean light) and poorly at the venue (mixed fluorescent + projector spill). Mitigation: the badge-detection test runs on the venue's actual lighting via a captured frame batch from the calibration step.
- Designers iterate on the cell ornament until it's pretty *and* breaks detection. Mitigation: detection-rate is a non-negotiable gate; a style that drops below 80 % is rejected by the test.

## Alternatives considered
- **Stick with stock ArUco.** Functional, dominant, looks like a barcode.
- **Switch to AprilTag.** Different convention, same root problem — fixed visual.
- **Steganographic markers** (hide the pattern inside larger artwork). Possible; reserved for ADR 0070-style explorations and beyond.
