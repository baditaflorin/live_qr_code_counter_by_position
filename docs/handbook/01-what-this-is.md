# 1 · What this is

*Reading time: 5 minutes.*

This system measures **where people stand** during a facilitated workshop —
nothing more. Each participant wears a small printed marker on their hat or
chest. Cameras on the gallery (or a single laptop webcam) detect the markers,
count which floor zone each marker is in, and produce a record of who stood
where, when, and with whom.

It is built around the slide-deck thesis: **the room is the lens**. The body
answers before the mouth does; the system records the body's answer.

## What it does today

- **Live counting** — facilitator activates a question (*"I have a friend I
  would call at 3 a.m."*); participants stand on a side; the screen shows
  *yes: 47, no: 12, middle: 8* in real time.
- **Tracking sessions** — a 90-minute window where the system records
  positions every half-second. Reports show who stood with whom, how long.
- **Personal reflection card** — at workshop end, each participant gets a
  one-page printable card summarising where they stood, what they answered,
  who they spent time with. They take it home.
- **Designed badges** — markers don't have to look like QR codes. Six
  templates (poster, heraldic, botanical, postage, minimal, craft) × six
  cell ornaments × five palettes × five generative frames stack to ~900
  unique badge looks, all with detection verified.
- **Hands-free control** — four printed cards (Start/Stop tracking, Next/Prev
  question) the operator holds up to the camera. No keyboard during the
  exercise.

## What it doesn't do

- **No audio recording** unless the participant explicitly raised a *promise
  card* and consented. ADR 0029.
- **No video archiving** unless `record_frames=true` is set on the tracking
  session AND the workshop has consent. Otherwise frames pass through and
  are immediately discarded. ADR 0019.
- **No face recognition.** The system can't identify a person without their
  marker. Take the marker off, you're invisible to the system.
- **No exporting to third parties.** Data lives in your container. Backups
  go where you point them. ADR 0010.

## What it's *for*

A facilitator running an opening exercise like Czocha Day 1 ([slide deck](../../README.md))
gets:

- Bigger numbers, faster — *47 say yes, 12 say no, 8 are tender* — instead of
  guessing from the spread.
- A record of the spread that survives the workshop.
- A printable artifact for each participant that says *what their evening
  looked like through the room's eyes*.

A facilitator who doesn't want any of that — for whom the *embodiment* is
the work and the *measurement* is interference — should not run this system.
That's a fair thing to decide.

## Honest limits

- **One camera covers ~9 m of floor reliably at 1080p.** Bigger halls need
  multiple cameras (ADR 0005, 0034) or larger printed markers (ADR 0031).
- **Calibration matters.** Without the four floor-corner anchors and the
  ChArUco intrinsic, proximity is in image pixels, not metres. The numbers
  still work but the cluster claims drift.
- **Two operators recommended for >50 people.** One drives `/admin`, one
  watches `/track` and the room. A single operator works for ≤30.

---

✅ **You've done this if:** you can describe in one sentence what the tool
measures, *and* list two things it doesn't do.

→ Next: [Setup](02-setup.md) — install, calibrate, run a 5-friend test workshop.
