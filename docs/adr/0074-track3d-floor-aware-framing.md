# ADR 0074 — Track3D floor-aware camera framing

## Status
Proposed. Implements a Track3D operator polish layer on top of ADR 0050.

## Context
`/track3d` renders the calibrated floor in metres, but its viewer camera
started from a fixed position. That worked for the default 5 m × 4 m room and
failed once a real calibration described a larger or differently-shaped floor:
the camera target moved to the floor centre, while the camera distance did
not. The result looked off-centre or clipped even though the math was using
the correct world frame.

The operator should never have to orbit blindly just to discover where the
floor went. The page already knows the world bounds; the viewport should use
that data.

## Decision
Track3D derives camera framing from the actual scene bounds:

- The first `scene_world.world_frame` auto-fits the calibrated floor.
- The fit calculation uses the active viewport aspect ratio and camera field
  of view, not a fixed distance.
- `Frame all` fits the floor, visible people, visible markers, and camera
  positions together.
- `Reset` returns to a floor-aware default orbit instead of the legacy fixed
  `(6, -6, 6)` view.
- `Top-down` uses the same bounds with a top-down direction, so large rooms
  still fit.
- Browser resizes re-fit the scene until the operator manually orbits, pans,
  follows, or flies to a target.

Manual camera control wins after the operator touches the viewport. The page
does not keep snapping the view back while someone is inspecting a marker.

## Consequences

**Positive:**
- Calibrated rooms are visible on first load regardless of floor size.
- The controls become predictable: all three view buttons use one bounds
  model.
- Wide and narrow screens get equivalent framing because aspect ratio is part
  of the fit.

**Negative:**
- The viewer now has a little more camera-state bookkeeping.
- If a user manually frames a strange debug angle, auto-fit intentionally
  stops until they press `Reset` or `Frame all`.

## Alternatives considered

- **Only increase the default camera distance.** Helps one venue size, fails
  the next one, and wastes screen space for small rooms.
- **Make the floor CSS container taller.** Useful polish, but it cannot fix a
  perspective camera aimed from the wrong distance.
- **Always auto-fit every frame.** Looks tidy in screenshots but fights the
  operator during real inspection.

## Postscript
This is a small UX decision with a large trust effect. When the floor appears
where the operator expects it, the rest of the calibration workflow feels less
mysterious.
