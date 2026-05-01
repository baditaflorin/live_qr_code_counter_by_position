# Pilot workshop protocol

Implements [ADR 0058](../docs/adr/0058-pilot-workshop-protocol.md). For pilots
1–10. After 10 successful pilots the protocol becomes the operator handbook
chapter [docs/handbook/03-run-a-workshop.md](../docs/handbook/03-run-a-workshop.md).

---

## 1 · Pre-event

### T−7 days

- [ ] Send the consent form template (`docs/consent/`) to the workshop
      sponsor for distribution at registration. Confirm hardware tier (per
      [`HARDWARE.md`](HARDWARE.md)) and active dictionary
      ([`ARUCO_DICTIONARY` env](../docker-compose.yml)).
- [ ] Confirm operator + facilitator identities.
- [ ] Confirm venue: floor dimensions, gallery height, projector capability,
      Wi-Fi upstream.

### T−24 hours

- [ ] Print: marker roster, anchor markers, ChArUco calibration board,
      control-marker cards (`/api/control-markers/pdf`).
- [ ] Pack the hardware kit. Run smoke test:
      `make test-smoke` (see [ADR 0059](../docs/adr/0059-end-to-end-smoke-test.md)).

### T−1 hour

- [ ] Arrive at venue.
- [ ] Set up cameras + laptop(s). Power, network, projector.
- [ ] Run intrinsic + extrinsic calibration via `/admin → Cameras`.
- [ ] Verify zone polygons match floor layout: `/admin → Zones`.
- [ ] Test snapshot, test tracking session start/stop.
- [ ] Pre-load the active question deck (Czocha Day 1 by default).

---

## 2 · Briefing (first 5 minutes)

The operator reads aloud:

> *Tonight we're recording **where you stand**, not what you say. Each of you
> has a marker — on a hat, on a lanyard. Cameras on the gallery see the
> markers and count them. We don't record audio, we don't record video frames
> unless you raised a memory card and chose to. The data goes home with you
> on a card at the end. **If you're uncomfortable being tracked, raise the
> `INTENT_REST` card any time and the system stops counting you for that
> round.***

The opt-out via card-raise is **non-negotiable**. Without it, consent isn't
really consent.

---

## 3 · During-event (90-minute exercise)

### Minimum-viable feature set

Only enable ADRs that have **shipped to prod** *and* completed at least one
prior pilot. Phase-2 pilots use Phase-1 features; Phase-3 pilots use Phase-2
features plus the new Phase-3 slice (per [ADR 0057](../docs/adr/0057-mvp-slice-90-day-rollout.md)).

### Operator stop-button

A single keystroke: **Esc Esc Esc**. Disables tracking, freezes the live
overlay, and leaves the room visibly silent. Used if anything weird happens
or if the room asks for a pause.

### "Anything weird" log

Operator types one-line notes during the session. Zero formatting. Examples:

```
14:42 — Anna asked if we record audio. Reassured.
15:08 — Camera 2 dropped for 30s, came back fine.
15:21 — 'Yes' card on the right side of the room got missed.
```

The log is for **memory**, not consumption. Saved to
`docs/pilots/<date>/anything-weird.txt`.

---

## 4 · Post-event debrief (60 minutes after)

### Operator's first 30 minutes (alone)

The most honest moment of the pilot's record. Before talking to anyone:

- What happened.
- What surprised them.
- What they noticed the room felt.
- Review Red-Hat ([ADR 0037](../docs/adr/0037-red-hat-operator-vibe-channel.md)) flags from the session.

Output: `docs/pilots/<date>/operator-notes.md`.

### Participant feedback

5-question paper survey handed at workshop end:

1. Did you understand what the system was tracking?
2. Did you feel comfortable being tracked?
3. Was anything unexpected?
4. Would you do this again?
5. Open: anything you want to say.

Surveys → `docs/pilots/<date>/surveys.md` (transcribed).

### Data-quality review

Open `/track → session report`, the audit log, the metrics. Did detection
work? Did the report make sense? Were there obvious bugs in the data?

Output: `docs/pilots/<date>/data-review.md`.

---

## 5 · Learning capture

Each pilot ends with a single document at `docs/pilots/YYYY-MM-DD-<venue>.md`:

```markdown
# Pilot: 2026-05-12 · Czocha

## What worked
- (3 bullets, evidence-based)

## What didn't
- (3 bullets, evidence-based)

## What surprised us
- (1–3 bullets, vibe-based, contradictions welcome)

## What we'll change next time
- (concrete actions, owners, ETAs)
```

These documents feed the quarterly ADR re-read ([ADR 0041](../docs/adr/0041-blue-hat-adr-lifecycle.md)).
They are the **primary** evidence source driving status changes
Proposed → Accepted → Implemented or Deprecated.

---

## Pilot ladder

- **Pilots 1–5**: original team operates *and* observes. Internal participants.
- **Pilots 6–10**: trained external facilitators operate; team observes. Real workshop sponsors. Real participants.
- **Pilots 11+**: external facilitator runs solo; team off-site. Protocol becomes general.

---

## Consent specifics (non-negotiable)

Explicit opt-in at registration for each of:

- [ ] **Tracking position data** — which is the default; without it the system can't run.
- [ ] **Audio recording** ([ADR 0029](../docs/adr/0029-promise-cards.md) promise cards only) — opt-in.
- [ ] **Frame storage** ([ADR 0019](../docs/adr/0019-auto-highlight-reel.md) highlight reel) — opt-in.
- [ ] **Follow-up email** (six-week promise check-in) — opt-in.
- [ ] **Anonymised public dataset contribution** — opt-in.

Consent template lives in `docs/consent/EN.md` and `docs/consent/PL.md`.
