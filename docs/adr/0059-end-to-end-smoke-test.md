# ADR 0059 — End-to-end happy-path smoke test

## Status
Proposed.

## Context
The repo currently has **zero automated tests**. Every deploy, every prod push, every PR is verified by clicking around the admin UI — *if* anyone bothers, *if* they remember the right click sequence, *if* they spot the silent regression.

The ADRs above describe a stack with two backend modules, one detection pipeline, six frontend modules, a card grammar, multi-camera fusion, calibration, and counting. None of those are tested. The existing 50-bug fix history (the `_next_aruco_id` 0-vs-falsy bug, the dictionary-overflow 500, the prod-only `datetime` import error) is exactly the kind of thing a smoke test catches in <60 seconds.

A real production tool that runs live workshops where a regression *during* a session is unrecoverable cannot ship without at least one automated test that exercises the full happy path.

## Decision
Add three layers of automated tests, runnable from a single `make test` command, gated in CI.

### Layer 1 — `tests/smoke/test_end_to_end.py` (every push, < 60 s)

A single test that exercises the whole stack on a clean SQLite. **Hard fails the build** if anything diverges.

The flow:

1. **Boot** — start the FastAPI app in-process with an empty `app.db`. Run Alembic upgrade head (per ADR 0002).
2. **Seed** — call the Czocha seeder; verify 63 questions + 22 zones load.
3. **Marker generation** — POST `/api/markers/batch` for 5 markers; assert all 5 IDs unique, all in person range.
4. **PDF roundtrip** — GET `/api/markers/pdf?ids=0,1,2,3,4`; assert response is valid PDF; re-detect ArUco markers in the rendered pages; assert all 5 are present.
5. **WS detection** — open WS to `/ws/detect`; send 30 pre-recorded JPEG frames containing 3 known markers; assert WS payload contains the 3 detections, correct `aruco_id`s, and reasonable `center_norm` values.
6. **Active question + snapshot** — activate question id 1; record a snapshot via `/api/questions/{id}/snapshot/record` with the test detections; verify a `Vote` row exists per detection.
7. **Tracking session** — start a session via `/api/tracking/sessions`; send 60 frames over 30 seconds (simulated rate); stop the session; fetch the report; assert: `sample_count > 0`, `markers_seen` includes the test ids, `pair_contact_seconds` is non-empty if any cluster occurred, `never_met_pairs` is well-formed.
8. **Audit log assertion** — verify the audit table now contains rows for each `POST/PUT/DELETE` made during the test.

Total expected runtime: 35–55 seconds. Runs on every PR via GitHub Actions.

### Layer 2 — `tests/integration/` (nightly)

Slower tests for things that don't change every commit but matter when they do:

- **Cluster math** — fixture of 50 known marker positions; assert the union-find clustering gives the expected groups for a sweep of `proximity_norm` values.
- **PDF rendering accuracy** — a generated marker PDF, re-rendered at print resolution, re-detected; assert ArUco corner-position drift is < 1 pixel (catches font/layout regressions that break detection at print size).
- **Homography invariance** — synthetic ground-truth scene; project through known camera matrices; verify `findHomography` recovers them within tolerance.
- **Migration round-trip** — every Alembic migration upgrades AND downgrades cleanly on an empty DB and on a DB with rows.

Layer 2 runs nightly and on tagged releases.

### Layer 3 — `tests/golden/` (any release)

Reference fixtures that catch *behaviour* regressions, not just *crash* regressions:

- A 5-second video of a known-good workshop snippet (3 people, line formation, walking through 5 zones).
- The expected output: which clusters formed when, who was in which zone at each frame, contact-time matrix.
- The test feeds the video frame-by-frame, captures the system's output, and diffs against the golden record.

When the cluster algorithm changes — even harmlessly — the golden test produces a *visible* diff. If the diff is intentional (smoothing improved, threshold tightened), the operator regenerates the golden record explicitly with a one-line `regenerate-golden` command, which logs the change in the audit document. Implicit cluster-algorithm changes are caught.

### CI wiring

`.github/workflows/test.yml`:

```yaml
on: [push, pull_request]
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt -r requirements-test.txt
      - run: make test-smoke
      - run: make lint
```

A separate `nightly.yml` runs Layer 2 and Layer 3 against `main` at 03:00 UTC.

## Consequences

**Positive:**
- The class of bugs that hit prod last quarter (the falsy-zero, the missing import, the dictionary overflow) cannot recur silently.
- A new contributor sees a green/red signal on their PR; they don't have to learn the manual click-test choreography.
- The golden test (Layer 3) catches *cluster-algorithm regressions* that no human would notice without watching every diff.

**Negative:**
- Test maintenance is a real ongoing cost. Mitigation: Layer 1 is small (~200 lines); Layers 2/3 are amortised across release cycles, not per-commit.
- The pre-recorded JPEG fixtures and the golden video are committed binary blobs that bloat the repo. Mitigation: store them in `tests/fixtures/` with documented regeneration scripts; flag if they exceed 50 MB total.

**Risks:**
- Tests pass but production fails because the test environment differs (e.g., no real webcam, no real network). The smoke test is *necessary but not sufficient*. Mitigation: pilot workshops (ADR 0058) remain the final line of defence; tests catch the regressions humans wouldn't catch in time.
- Golden-test churn: every cluster-algorithm tweak forces a golden regeneration. Mitigation: the regeneration is *explicit* and logged in `docs/golden-regenerations.md`; a high regeneration rate is itself a signal.

## Alternatives considered
- **No tests; manual QA only.** Status quo. Will eventually cost a workshop.
- **Unit tests of every module.** More code, less integration value. Layer-1 catches the bugs that actually shipped; Layer-2 fills the unit-style gaps where integration isn't enough.
- **Property-based / fuzz testing.** Worth doing eventually for the cluster math; add as a future Layer 4 ADR if observed bugs justify it.

## Postscript
This is the smallest possible step from "untested" to "tested". Adding it doesn't *prove* the system is correct — it proves the *happy path* still works after any given change. That's the bar a system that runs live, time-bounded, irreversible workshops needs to clear before it claims production status.
