# 2 · Setup

*Reading: 15 minutes. Hands-on: ~60 minutes including the test workshop.*

## Hardware

Pick a tier from [`deploy/HARDWARE.md`](../../deploy/HARDWARE.md). The
**Solo tier** is enough for the 5-friend test in this chapter.

## Software install (5 commands)

On a clean Mac with Docker Desktop running:

```bash
git clone https://github.com/baditaflorin/live_qr_code_counter_by_position.git
cd live_qr_code_counter_by_position
docker compose up --build -d
open http://localhost:8000
open http://localhost:8000/admin
```

That's it. Nothing else needs to be installed.

> **No Docker?** `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn backend.main:app --reload` works too.

## First calibration

Done once per camera setup. Open `/admin → Cameras → New camera`.

### Step 1 — Intrinsic (camera lens)

This is "what does this lens see vs. reality?" — done once per camera, never
needs redoing unless you change the lens or zoom.

1. Print [`printable/charuco-board.pdf`](../../printable/charuco-board.pdf) on
   A3 stiff card.
2. In `/admin → Cameras`, hit **Calibrate intrinsic**.
3. Show the ChArUco board to the camera at varied angles (10° tilt left,
   right, forward, back, multiple distances) for ~10 seconds. The page
   counts views as it captures them.
4. When ≥20 views collected, the system computes `K` and `dist`. Done.

A reprojection error of <1 pixel is good. >2 pixels means the camera moved
during capture; redo.

### Step 2 — Extrinsic (where the camera is in the room)

This is "where in the room is the camera?" — done once per *physical setup*.
Re-do if the camera moves.

1. Print [`printable/anchors.pdf`](../../printable/anchors.pdf).
2. Tape the four anchors to the floor in a known rectangle. The default is
   5 m × 4 m. Configure the rectangle in `/admin → Cameras → Floor rect`.
3. Aim the camera so all four anchors are visible.
4. Hit **Calibrate extrinsic**. The system reads the anchor pixel positions
   and computes where the camera is in the room.

After both calibrations, the **Cameras** tab shows green ticks for *intrinsic
calibrated* + *extrinsic calibrated*. The proximity metric is now in metres.

## The 5-friend test workshop (60 minutes)

Best way to know your install works.

### Setup (15 min)

1. Invite five friends. Bring printer, marker pens, tape, your laptop.
2. In `/admin → People`, add five rows. Use the **Add person** form, or
   prepare a CSV like:

   ```csv
   name,marker_count
   Alice,1
   Bob,1
   Cleo,1
   Dani,1
   Eli,1
   ```

   …and use the **Import roster** panel.
3. Hit `/api/markers/pdf` (linked from the Markers tab). Print, cut, hand out.
4. In `/admin → Zones`, click **Load default templates**. Activate the
   `two_camps` formation by drawing rough left/right zones on your camera
   feed.

### Run the test (30 min)

1. Open `/admin → Questions`. Hit **Load Czocha Day 1 deck**.
2. Activate any *Block 4 — How You Trust* question (e.g. *"I have a friend
   I would call at 3 a.m."*).
3. Open `/` (Live). Start the camera. Friends stand on yes/no sides.
4. Watch the counts settle. Hit **Record snapshot**.
5. Repeat with a different question.
6. Open `/track`, start a tracking session, run for 10 minutes, stop.
7. Click **Report** on the session. Verify the *pair contact seconds* shows
   non-zero pairs.

### Verify (15 min)

- The Live page shows zone counts that match what you see in the room.
- The audio cue plays when you hit Record snapshot.
- The tracking report has reasonable numbers.
- `/present` shows the active question fullscreen with cross-fade on advance.

If any of these don't work: see chapter [4 — When it breaks](04-when-it-breaks.md).

---

✅ **You've done this if:** you've run the 5-friend test and seen a tracking
report with non-zero `pair_contact_seconds` *and* a working `/present`
projection.

→ Next: [Run a workshop](03-run-a-workshop.md) — the real thing.
