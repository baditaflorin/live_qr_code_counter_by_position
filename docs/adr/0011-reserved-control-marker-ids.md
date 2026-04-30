# ADR 0011 — Reserved control-marker IDs

## Status
Proposed. Foundation for ADR 0012, 0013, 0014, 0015.

## Context
Every ArUco id in the active dictionary is currently treated as a "person marker" — the only thing the detection loop can do with one is render a label and look up its assignee in the `markers` table. That's an under-use of a fiducial system that's *designed* to convey intent.

The slide deck already pushes the facilitator off the laptop and onto the gallery floor: "the room becomes the lens." Today they still need to come back to the keyboard to start tracking, advance a question, or re-draw a zone. A printed card with a marker on it is a faster, more theatrical control surface than alt-tabbing to the browser mid-exercise.

`DICT_4X4_250` has 250 ids; `_next_aruco_id()` allocates from 0 upward. Nothing structural prevents a person from being assigned id 247, but in practice the upper range never gets used until a workshop has hundreds of attendees.

## Decision
Reserve the **top 16 ids of whichever dictionary is active** (e.g. `DICT_4X4_250` → ids 234–249) as **control markers**, not person markers.

- A `ControlMarker` table (`marker_aruco_id`, `name`, `action`, `params_json`) lists the reserved ids, seeded at first migration.
- `_next_aruco_id()` and `POST /api/markers/batch` refuse to allocate inside the reserved range; the assignment endpoints reject `person_id` on a control id.
- Detection pipeline: every frame, marker ids are split into person-detections and control-detections. Person-detections flow into the existing path. Control-detections are passed to a new `CommandRouter` (in `backend/control.py`) which dispatches to handlers (one per ADR 0012/0013/0014/0015 use case).
- A new admin tab "Control markers" lists the reserved ids, lets the operator print them as a single PDF (analogous to `markers_pdf`), and lets them rebind which id triggers which action (`PATCH /api/control-markers/{id}`).

## Consequences

**Positive:**
- One pattern (a printed marker held to the camera) covers calibration, zone drawing, session control, drift checks. Each subsequent ADR is just another handler in the router.
- Operators can run an entire workshop without keyboard contact — meaningful when they're standing on a wooden gallery 3 m above the floor.
- The reserved range is part of the same dictionary, so detection is free; no second detector needed.

**Negative:**
- Reserves 16 ids that are then unavailable for people. With `DICT_4X4_250` that's negligible; with `DICT_4X4_100` (100 ids) it's a 16 % cap on roster size and we'd want to default-promote to `DICT_4X4_250` before turning this on.
- Control markers in the wrong hands (a participant with a printed copy) can fire actions. ADR 0014 mitigates with held-still timing + audible/visible confirmation.

**Risks:**
- Accidental triggers from a participant's stray printout. Mitigation: control markers must be held still for ≥1.5 s before firing, and confirmation is shown in the live overlay; destructive actions require a second confirmation marker held within 5 s.

## Alternatives considered
- **Reserve ids of a *different* dictionary** (e.g. control markers in `DICT_5X5_50`, person markers in `DICT_4X4_250`) — solves the namespace cleanly but doubles detector cost.
- **Use QR codes for control** — heavier visual, harder to detect at gallery distance.
- **No control markers; keep the operator at the keyboard** — current state; the cost is operator presence, which is exactly what we want to remove.
