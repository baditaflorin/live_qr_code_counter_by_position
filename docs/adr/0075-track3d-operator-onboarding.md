# ADR 0075 — Track3D operator onboarding and calm empty states

## Status
Proposed. Complements ADR 0060 (operator handbook) and ADR 0074
(floor-aware framing).

## Context
Track3D is an expert surface: calibration quality, publishing cameras,
people, markers, encounters, trails, heatmaps, and recordings all live on the
same screen. When nothing is publishing, or when calibration is incomplete,
the old page mostly showed a black canvas plus sidebar text. That is technically
accurate, but it leaves new operators wondering whether the system is broken.

The page needs just enough onboarding to reveal state and next action without
turning into a tutorial.

## Decision
Track3D becomes state-led:

- The top panel shows scene health at a glance: camera count, people count,
  marker count, and average camera coverage.
- The setup checklist is compact and data-backed: intrinsic calibration,
  extrinsic calibration, and publishing status each show their current state.
- The canvas has centred empty states for the three common pauses:
  no publishing cameras, incomplete calibration, and connected cameras with
  no markers in view.
- The sidebar stays sticky on desktop so publishing, people, encounters, and
  recordings remain visible while inspecting a tall canvas.
- The canvas height scales with the viewport, giving the 3D scene more room
  on operator laptops without hiding the next panel on smaller screens.

## Consequences

**Positive:**
- New operators can tell whether they need Admin, Live, or physical markers.
- The page feels more like an operations console and less like a blank render
  target.
- The setup path no longer tells users to press a camera button on the
  observer page; publishing stays anchored to Live.

**Negative:**
- There is more visible state in the top chrome.
- Empty-state copy must stay terse so it does not compete with the scene when
  cameras are live.

## Alternatives considered

- **Keep onboarding only in the handbook.** Good for training, weak in a live
  room where the operator needs immediate state.
- **Use a multi-step modal.** Too heavy for repeat operators and awkward when
  the page is used as a passive monitor.
- **Add more sidebar paragraphs.** Easy to implement but keeps the black
  canvas feeling broken.

## Postscript
The best onboarding for this page is not explanation; it is making the current
state obvious enough that the next move is boring.
