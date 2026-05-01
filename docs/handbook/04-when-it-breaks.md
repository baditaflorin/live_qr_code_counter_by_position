# 4 · When it breaks

*Reading: 20 minutes. Re-read at quarterly review.*

A workshop runs 90 minutes. Every minute the system is broken is a minute
the facilitator is improvising. This chapter is the five most common
failure modes, with their recovery, ordered by *frequency*.

The full runbook is [`deploy/RUNBOOK.md`](../../deploy/RUNBOOK.md). This
chapter is the subset that hits in real workshops.

---

## 1 · Live page froze; counts not updating

**Symptom.** Live page shows the camera feed but the count tiles haven't
changed in ~20 seconds.

**Likely cause.** WebSocket dropped silently — Wi-Fi blip, browser tab
backgrounded.

**Recover:**

1. Click **Stop**, then **Start** on the Live page. The WS reconnects.
2. If counts still don't move, refresh the page (Cmd-R). Active question
   + zones reload from server, no data loss.

**Workshop-side workaround while you fix:** *"Hold this position for
30 seconds — the system is catching up."* Continue verbally.

---

## 2 · Camera not detected when you click "Start"

**Symptom.** Browser shows "camera error" or the dropdown is empty.

**Likely cause.** Browser permission denied earlier in the session.

**Recover:**

1. Click the lock icon in the URL bar → **Site settings** → **Camera** →
   set to **Allow**.
2. Reload the page.
3. If still failing, the camera is in use by another app (Zoom, FaceTime).
   Quit that app.

**Workshop-side workaround:** Start the test snapshot on a different laptop
while you fix. The active question + zones state survive.

---

## 3 · Wi-Fi cratered mid-exercise

**Symptom.** Live page shows red "disconnected" status pill. The audit
log freezes.

**Likely cause.** Conference Wi-Fi got hammered.

**Recover:**

1. Switch to phone hotspot temporarily. Tracking continues; audit lag
   catches up when network resumes.
2. Drop bandwidth profile to **lite** (`/admin → Cameras`): 960×540 @ 5 fps
   ≈ 1 Mbps. Workable on phone tether.

**Workshop-side workaround:** Use the verbal/embodied formation; system
captures what it can.

---

## 4 · A control card keeps firing repeatedly

**Symptom.** Banner shows "▶ Start tracking" 5 times in 30 seconds.

**Likely cause.** A control marker is sitting on a desk in the camera's
view. The 5-second debounce handles fast re-fires but misses long-term
sitting.

**Recover:**

1. Move the control card out of camera view. The router stops firing it.
2. If the card is on a participant's costume by accident, swap it with a
   plain person marker.

**Prevention:** Operator's pocket is the right place for control cards
between uses. Or use the `enabled: false` toggle in `/admin → Control
markers` to disable them mid-session.

---

## 5 · Tracking session shows zero samples after stop

**Symptom.** `/track → Session report` says `samples: 0`.

**Likely cause.** Camera was off during the session, OR the session was
started but no client was streaming frames.

**Recover:**

1. The samples are gone — they were never written. The session row
   itself remains for reference.
2. Re-run if possible. If not, the data is what you had verbally.

**Prevention:** Always start the camera *before* the session. Check the
*sample count* in the active-session banner climbs above 0 within 5
seconds of starting tracking.

---

## What to type in the "anything weird" log

Examples of good entries:

```
14:42 — Anna asked if we record audio. Reassured.
15:08 — Camera 2 dropped for 30s, came back fine.
15:21 — 'Yes' card on the right side of the room got missed.
15:35 — Switched to lite profile because Wi-Fi tanked.
```

The log is in `docs/pilots/<date>/anything-weird.txt`. It's for *memory*,
not consumption.

## When to stop the workshop

If any of these:

- Multiple participants raise the **`INTENT_REST`** card unprompted →
  pause, ask the room what's happening.
- The data is clearly wrong (e.g. counts are 100× the actual room) →
  press **Esc Esc Esc** and continue verbally.
- Someone in the room is visibly distressed → operator priority is the
  person, not the system. Stop. Reach the facilitator.

---

✅ **You've done this if:** you can articulate, without looking, what
to do if the live overlay freezes mid-snapshot.

→ Next: [What's coming](05-whats-coming.md) — vision + how to contribute.
