# Hardware kit reference

Implements [ADR 0056](../docs/adr/0056-reference-hardware-kit.md). Three orderable
tiers — pick one, follow the BOM, the system works on day one.

> **Pricing notes.** Prices below are USD and best-effort accurate at time of
> writing. They drift; treat them as ranges. Most line items have alternatives
> at lower price points listed under each tier.

---

## Tier 1 · Solo  (~$350–500)

For: pilot workshops up to ~30 people, single operator, single fixed camera at
gallery height.

| Line item                                | Why                                                             | Source / model                            | Price  |
| ---------------------------------------- | --------------------------------------------------------------- | ----------------------------------------- | -----: |
| **1× Logitech C922 Pro Stream** webcam   | 1080p / 30 fps; reliable detection at the centre of frame       | Amazon, B&H                               | ~$80   |
| **1× operator laptop**                   | Existing — Mac, Linux, or Windows, any 2019+ machine            | —                                         | —      |
| **4× A4 anchor markers** (printed)       | Floor calibration, ADR 0012                                     | `printable/anchors.pdf` — your printer    | ~$2    |
| **1× roll black gaffer tape**            | Affix anchors to floor; remove cleanly                          | Local / B&H                               | ~$10   |
| **Person markers** (printed)             | Hat-mounted, A5 size                                            | `/api/markers/pdf` from the Admin tab     | ~$3    |
| **Card stock** for mounting              | 200 gsm or higher so markers stay flat                          | Office supply                             | ~$15   |

Sized for: 1 operator + 1 camera + ≤30 attendees + 1 hall + no projector.

**Alternatives:**
- Replace the C922 with the laptop's built-in webcam if it's 1080p (most MacBooks since 2020). Detection at the back of the room becomes flaky — see [ADR 0031](../docs/adr/0031-resolution-marker-sizing.md).
- Anchor markers can be skipped if you don't need real-meter proximity ([ADR 0012](../docs/adr/0012-auto-calibration-corner-markers.md)).

---

## Tier 2 · Standard  (~$1,500–2,500)

For: workshops 30–80 people, two operators, redundant fusion ([ADR 0005](../docs/adr/0005-multi-camera-fusion.md)).

| Line item                                  | Why                                                       | Source / model                                | Price  |
| ------------------------------------------ | --------------------------------------------------------- | --------------------------------------------- | -----: |
| **2× Logitech C922 Pro Stream**            | Two angles → multi-camera fusion                          | Amazon, B&H                                   | ~$160  |
| **1× operator laptop + 1× Raspberry Pi 5** | Pi runs the second camera; laptop drives admin            | rpi.com + retailer                            | ~$120  |
| **1× Brother HL-L2350DW** mono laser       | On-the-day reflection cards ([ADR 0017](../docs/adr/0017-personal-reflection-card.md))  | Amazon                                        | ~$130  |
| **1× BenQ TH671ST short-throw projector**  | `/present` + `/project`; throws across a 4 m hall         | B&H                                           | ~$650  |
| **1× projector screen / blank wall**       | 9'×6' minimum                                             | local / no cost                               | —      |
| **A3 ChArUco calibration board**          | One-time intrinsic calibration ([ADR 0048](../docs/adr/0048-aruco-pose-estimation.md))   | `printable/charuco-board.pdf` — print on rigid laminated stock | ~$30   |
| **A4 anchor + person markers**             | Same as Tier 1 but more, in pre-bagged kits               | `/api/markers/pdf` + lamination               | ~$60   |
| **HDMI cable + power strips**              | Connect projector + cameras                               | Monoprice, Anker                              | ~$40   |

Sized for: 2 operators + 2 cameras + projection + bagged participant kits.

**Alternatives:**
- Skip the Pi — a single laptop with a USB hub can drive both cameras. CPU may struggle past 1080p × 2 cameras.
- Replace the BenQ with any 1080p projector ≥3000 lumens. Brighter is better; halls are not dim auditoriums.

---

## Tier 3 · Pro  (~$4,000–6,000)

For: 80–150 people, the slide-deck Czocha six-camera setup, pre-bagged kits, transport case for a touring kit.

| Line item                                  | Why                                                      | Source / model                  | Price  |
| ------------------------------------------ | -------------------------------------------------------- | ------------------------------- | -----: |
| **6× Logitech Brio 4K** webcams           | Six-camera setup from the slide deck                     | B&H, Amazon                     | ~$1,200 |
| **3× operator laptops**                    | One per pair of cameras; redundant if any drops          | Used MacBooks / refurbished     | ~$1,500–2,500 |
| **2× short-throw projectors**             | One for `/present` (audience), one for `/project` (floor) | BenQ TH671ST x2                  | ~$1,300 |
| **1× colour laser printer**                | Reflection cards in colour; the workshop's keepsake      | Brother HL-L3270CDW              | ~$300  |
| **Pre-printed participant kits**           | 200× hat markers + 200× chest+back lanyards (laminated)  | Local print shop, bulk          | ~$300  |
| **1× Pelican 1620 hardware case**         | Transport between venues                                 | B&H                              | ~$300  |
| **Cabling, USB hubs, mounts**              | Camera mounts, USB extensions, gaff tape, Velcro         | various                          | ~$200  |

Sized for: 80–150 people, six-camera fusion, two projectors, the wooden-box destination ([ADR 0039](../docs/adr/0039-yellow-hat-2028-destination.md)) in field form.

---

## What ships with the repo

- [`printable/anchors.pdf`](../printable/anchors.pdf) — four corner anchors at the right physical size, A4 ready-to-print.
- [`printable/charuco-board.pdf`](../printable/charuco-board.pdf) — single ChArUco board for ADR 0048 intrinsic calibration, A3.
- `/api/markers/pdf` — bulk-print all assigned person markers, named.
- `/api/control-markers/pdf` — the four hands-free cards (TRACK_START, TRACK_STOP, Q_NEXT, Q_PREV) at large card size.
- `/api/markers/{id}/badge` — designed badge ([ADRs 0068–0072](../docs/adr/0068-badge-as-composition.md)) — pick template, palette, ornament, frame.

## Lighting & venue notes

- **Avoid mixed lighting.** Tungsten + fluorescent + projector spill confuses the auto-threshold. One light source ≥ 200 lux is plenty.
- **Hall ceiling height.** 6 m+ is comfortable. Below 4 m the gallery angle gets steep enough that markers near the foot of the camera are clipped.
- **Mark out the floor before doors.** Anchor markers should be in place + calibrated before the first participant arrives.

## What you shouldn't skip

- The 4 anchor markers. Without them the proximity metric is in image pixels, not metres ([ADR 0003](../docs/adr/0003-floor-homography.md)).
- The ChArUco calibration. Without it pose estimation ([ADR 0048](../docs/adr/0048-aruco-pose-estimation.md)) doesn't run.
- Print test before the day. Detection-rate degrades with curling or under-saturated prints. Run [`/admin → Markers → 🎨`](../README.md) to verify.
