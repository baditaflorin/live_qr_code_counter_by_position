# 3 · Run a workshop

*Reading: 45 minutes. The pre-event checklist alone is worth printing.*

This chapter is the operating manual. Bookmark it. Re-read T−24 hours.

## Pre-event checklist

### T−7 days

- [ ] Confirm participant count + venue + facilitator + sponsor consent.
- [ ] Send participants the consent text from
      [`docs/consent/EN.md`](../consent/EN.md). The room must arrive having
      seen it.
- [ ] Pick a hardware tier ([`deploy/HARDWARE.md`](../../deploy/HARDWARE.md)).
- [ ] If the dictionary needs to grow (>40 attendees on the multi-placement
      kit), set `ARUCO_DICTIONARY=DICT_4X4_1000` in `docker-compose.yml`.

### T−24 hours

- [ ] Print: anchor markers, ChArUco board, person markers (one per attendee
      named, via `/api/markers/pdf`), control-marker cards
      (`/api/control-markers/pdf`).
- [ ] Pack in this order: case bottom → laptops → cameras → printer (Tier 2+)
      → markers (paper goes last on top so it doesn't get crushed).
- [ ] Run `make test-smoke` on your laptop. Green = all good.

### T−1 hour (on-site)

- [ ] Camera mounted, laptop powered, projector aimed.
- [ ] In `/admin → Cameras`: confirm intrinsic + extrinsic green.
- [ ] In `/admin → Zones`: load default templates for the formations the
      facilitator will use today.
- [ ] In `/admin → Questions`: load the Czocha Day 1 deck (or whatever
      deck the facilitator chose).
- [ ] Run a sanity snapshot with you standing in a zone — verify `Vote`
      row appears in `/admin → Questions → Results`.

## The participant briefing (verbatim)

> *"Tonight we're recording where you stand, not what you say. Each of
> you has a marker — on a hat, on a lanyard. Cameras on the gallery see
> the markers and count them. We don't record audio, we don't record
> video frames unless you raised a memory card and chose to. The data
> goes home with you on a card at the end. If you're uncomfortable
> being tracked, raise the* `INTENT_REST` *card any time and the
> system stops counting you for that round."*

The opt-out card is non-negotiable. Brief it visibly.

## During the exercise

### Operator's keyboard rhythm

| Action                         | How                                              |
| ------------------------------ | ------------------------------------------------ |
| Advance to the next question   | Click **Next ›** on `/` or hold up the *Q_NEXT* card |
| Go back                        | **‹ Prev** or *Q_PREV* card                       |
| Record a snapshot              | **Record snapshot** button on `/`                |
| Start tracking                 | `/track → Start tracking` or *TRACK_START* card  |
| Stop tracking                  | `/track → Stop` or *TRACK_STOP* card             |
| **Stop everything (panic)**    | **Esc Esc Esc** (three times)                    |

The control cards are slow but theatrical — hold them up to the camera for
~1.5 seconds. Use them when you don't want to look at the laptop.

### What to watch

- **The room first.** The screen second.
- **`/admin → Audit log`** if anything weird happens. It's the truth.
- **Camera coverage** — if the live page shows the formation but counts
  drift toward zero, the camera angle has shifted. Recalibrate extrinsic.

### What `/present` shows

A separate display (projector, second laptop) on `/present` shows:

- The active question, big.
- Per-zone counts with bump animation.
- Optional "control card recognised" banner when a card fires.

Operators run `/admin` + `/`. The room sees `/present`. They never overlap.

## Post-event debrief

Within 60 minutes of the room emptying:

1. **Operator's first 30 minutes** — alone, before social conversation.
   Type what happened, what surprised, what you noticed. Use the Red-Hat
   flags from the session. This is the most honest record.
2. **Participant survey** — 5 paper questions, see
   [`PILOT-PROTOCOL.md §4`](../../deploy/PILOT-PROTOCOL.md).
3. **Data review** — open `/track → Session report`. Did proximity
   numbers make sense? Did `never_met_pairs` look right?
4. **Reflection cards** — print the per-person cards for the room. Hand
   them out the next morning, or leave them at registration.

Save everything to `docs/pilots/<date>-<venue>.md`.

---

✅ **You've done this if:** you have the briefing script bookmarked, know
the Esc Esc Esc keystroke without looking, and have a printed pre-event
checklist on your clipboard.

→ Next: [When it breaks](04-when-it-breaks.md) — the runbook.
