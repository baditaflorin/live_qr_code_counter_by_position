# Participant consent

This workshop will use a system that records **where you stand** during the
exercises. Please read before participating.

## What's recorded

- **Position only.** A small marker pinned to your hat or chest is detected
  by cameras. The system records *which floor zone you're standing in* every
  half-second.
- **Your name** if you've registered with one. The marker is linked to a
  person row in the database; the position data is per-person.

## What's *not* recorded

- **No audio.** Unless you raise a *promise card* and explicitly consent at
  that moment, no microphone is recording you.
- **No video frames.** The cameras process frames in memory and discard
  them, unless this workshop has explicitly enabled the highlight-reel
  feature *and* you have consented to image storage.
- **No face recognition.** The system identifies markers, not faces. If you
  remove your marker, you become invisible to the system.

## Your rights during the workshop

- **Opt out at any moment** by raising the `INTENT_REST` card (handed out
  with your kit). The system stops counting you for that round.
- **Walk away** at any time. No data point obliges you to stay.
- **Ask the facilitator** to delete your data after the workshop. The
  facilitator will run `DELETE /api/people/{id}` against your row and
  every position sample associated with it.

## What's done with the data

| Default | Opt-in only |
|---|---|
| Stays on the workshop's server | Cross-workshop research dataset (anonymised) |
| Auto-deleted after 90 days     | Six-week follow-up email                     |
| Visible to the facilitator     | Public per-person reflection card with names |

## Questions

Ask before you sign. Once you sign, you can still revoke at any time during
the workshop, but data captured before revocation may already be aggregated
into snapshots.

---

**☐ I have read this and consent to position tracking during the workshop.**

**☐ Optional: I consent to my name appearing on my reflection card.**
*(Without this, the card uses anonymised letters: "you stood longest with A, B, C".)*

**☐ Optional: I consent to a six-week follow-up email about any promise I make at the closing ritual.**

**☐ Optional: I consent to my anonymised data contributing to the cross-workshop research corpus.**

Name: _______________________________________

Signature: ___________________________________

Date: ________________________________________
