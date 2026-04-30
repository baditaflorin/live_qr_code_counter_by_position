# ADR 0051 — Phone-as-camera: participant join flow & camera lifecycle

## Status
Proposed (depends on ADR 0034 multi-camera planning, ADR 0050 3D scene; complemented by ADR 0052 / 0054 / 0055).

## Context
ADR 0034 plans cameras as **fixed infrastructure**: six gallery-mounted webcams, each calibrated, each connected to an operator's laptop. That setup is expensive (six laptops, six camera mounts, six humans), unavailable in most venues, and brittle — one operator's machine going to sleep takes a sixth of the coverage with it.

Meanwhile every participant in the room is carrying a high-quality camera with a battery, a CPU, a network connection, and a willingness to participate. A workshop with 100 attendees has a hundred-camera fleet sitting in pockets. The current system uses none of it.

The slide deck's *"the room becomes the lens"* metaphor lands much harder if the *room itself* — its participants, their phones — is literally the sensor array.

## Decision
Add a `/camera` route. Any phone (participant's or otherwise) navigates to it, grants camera permission, and immediately becomes part of the fusion fleet.

**Join flow.**

1. Phone hits `/camera` (printed on the back of the participant card, also reachable from a QR poster on the venue wall).
2. Page asks for camera permission and the participant's marker id (or an anonymous slot, if they don't have one).
3. Phone-as-camera registers as a `Camera` row with `kind: "phone_participant"`, an auto-generated session id, and a `joined_at` timestamp.
4. Phone enters **warming up** state — ~5 seconds while it self-calibrates by observing room markers (per ADR 0054). The UI shows: *"Calibrating… point at the room and hold steady."*
5. On successful calibration, the phone enters **active** state. It now contributes per-marker observations to the fusion module (ADR 0050) at the configured frame rate (per ADR 0032).

**Phone UI.**

The viewfinder is the page; minimal chrome. Visible elements:

- A short label — *"Camera #14"* — assigned at join time.
- A small steadiness ring (green when stable, yellow when shaky, red when erratic).
- A contribution meter — *"You're covering 8 % of the back-right corner."* Updated every few seconds; soft motivation to point well.
- A *Stop* button. Honoured immediately; the slot is released.
- A *Coverage gap* arrow when the system asks this phone to re-aim (per ADR 0053 convergence pings).

**Camera lifecycle states.**

| State          | Trigger                                          | Behaviour                                          |
| -------------- | ------------------------------------------------ | -------------------------------------------------- |
| `warming_up`   | Just joined                                      | Calibrating; observations not yet trusted          |
| `active`       | Calibration succeeded                            | Full participant in fusion                         |
| `suspended`    | Page backgrounded / screen sleep                 | Stream pauses; slot held for **60 s**              |
| `low_quality`  | Quality score (ADR 0055) drops below threshold   | Observations excluded from fusion; advisory hint shown to participant |
| `departed`     | Explicit `Stop`, or 60 s suspended without resume| Slot released; observations purged from current cycle |

**Re-join.** The page can be reopened from the same browser within 5 minutes and resumes the same slot — useful when a phone briefly locks. Beyond 5 min the slot is gone, but a new join is one tap away.

**Privacy.** Phones uploading video is materially more sensitive than markers being seen. The join page is explicit:

- *"Your camera is contributing detection of marker positions. Frames are processed on the server, not stored, unless this workshop has frame-archiving enabled (you'll see a recording icon if so)."*
- A workshop-level toggle controls whether phone-camera frames count toward ADR 0019 highlight-reel storage. Default off — most workshops only need the marker positions, not the pixels.

## Consequences

**Positive:**
- The fleet scales with attendance, not with logistics. A 200-person workshop has 200 potential cameras.
- The metaphor and the implementation finally match: the room *is* the lens.
- Cost-of-entry collapses: any venue with Wi-Fi and willing participants can run multi-camera now.

**Negative:**
- Heterogeneous quality (ADR 0055 mitigates this with per-camera weighting).
- Participants holding phones during an embodiment exercise is *itself* a problem — the slide deck wants their hands free. Mitigation: phone-as-camera is opt-in per workshop and per moment; an exercise that requires hands free can pause uploads with one operator gesture.

**Risks:**
- A phone aimed at the floor or in a pocket sends mostly-black frames. Caught by ADR 0055's quality threshold; phone goes to `low_quality` state.
- Participants forgetting to plug in / dim screen → battery drain mid-workshop. Mitigation: the page shows estimated battery cost and recommends low-brightness; the phone's slot is forgiving of suspends.
- Network bandwidth from many phones (per ADR 0033). Multi-phone setups should use the `lite` profile by default (~1 Mbps per phone), giving ~30 phones on typical conference Wi-Fi.

## Alternatives considered
- **Native iOS / Android app.** Better camera control, app-store overhead, two codebases, version-skew problems. The browser is just-enough.
- **WebRTC peer-to-peer between phones** instead of WS to backend. Avoids upstream-bandwidth bottleneck on the operator's side. Adds NAT-traversal complexity. Worth re-visiting once the basic flow proves out.
- **Operator-curated camera fleet only.** The current ADR 0034 world. Works at small scale; doesn't unlock the *every-phone-is-a-sensor* idea.
