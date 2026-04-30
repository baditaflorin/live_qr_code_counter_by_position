# ADR 0058 — Pilot workshop protocol

## Status
Proposed (executes during ADR 0057's Phases 2 and 3).

## Context
ADR 0039 envisions 1,000 consented workshops by 2028. The first 5–10 are different — they're the ones we *learn from*. They produce most of the bug reports, most of the UX rewrites, and most of the operator confusion. They also have outsized risk: a participant has a bad experience because the system glitched, and the workshop's core trust work is collateral damage.

Without a protocol, every pilot is improvised. Consent forms are written ad-hoc. Briefings vary by operator. Post-event learning lives in someone's head until the next pilot, where they re-learn the same lesson differently.

A short, written protocol makes pilots *comparable* (we can tell which lessons replicate), *safe* (consent and privacy are handled the same way every time), and *generative* (every pilot is a learning artifact, not a one-off run).

## Decision
Maintain `docs/PILOT-PROTOCOL.md` covering five sections.

### 1. Pre-event (T−7 days → T−1 hour)

- **T−7 days**: send the consent form template (PL/EN, in `docs/consent/`) to the workshop sponsor for distribution at registration. Confirm hardware tier (per ADR 0056) and active dictionary (per ADR 0049 capacity check).
- **T−24 hours**: print marker roster, anchor markers, ChArUco calibration board. Pack the kit. Test the deploy on the operator laptop (boot the stack, run the smoke test from ADR 0059).
- **T−1 hour**: arrive at venue, set up cameras, run intrinsic + extrinsic calibration (ADRs 0048, 0012). Check coverage diagram (ADR 0034) is green. Test snapshot, test tracking session start/stop. Pre-load the active question deck.

### 2. Briefing (first 5 minutes of the workshop)

A scripted briefing the operator reads aloud, kept in `docs/scripts/participant-briefing.md`:

> *"Tonight we're recording where you stand, not what you say. Each of you has a marker — on a hat, on a lanyard. Cameras on the gallery see the markers and count them. We don't record audio, we don't record video frames unless you raised a memory card and chose to. The data goes home with you on a card at the end. If you're uncomfortable being tracked, raise the* `INTENT_REST` *card any time and the system stops counting you for that round."*

The briefing emphasises the **opt-out is one card-raise away**. This is non-negotiable — without it, consent isn't really consent.

### 3. During-event (90-minute exercise)

- **Minimum-viable feature set**: only enable ADRs that have shipped to prod *and* completed at least one prior pilot. Phase-2 pilots use Phase-1 features; Phase-3 pilots use Phase-2 features plus the new Phase-3 slice.
- **Operator stop-button**: a single keystroke (`Esc Esc Esc`) immediately disables tracking *and* the live overlay, leaves the room visibly silent. Used if anything weird happens.
- **"Anything weird" log**: the operator types one-line notes during the session in a side terminal. *"15:42 — Anna asked if we record audio. Reassured."*. Zero formatting; the log is for memory, not consumption.

### 4. Post-event debrief (60 minutes after the workshop)

- **Operator's first 30 minutes** (alone, before talking to anyone): write what happened. What surprised them. What they noticed the room felt. The Red-Hat (ADR 0037) flags from the session are reviewed here. This output is preserved verbatim — it's the most honest moment of the pilot's record.
- **Participant feedback**: a 5-question paper survey handed at workshop end:
  1. Did you understand what the system was tracking?
  2. Did you feel comfortable being tracked?
  3. Was anything unexpected?
  4. Would you do this again?
  5. Open: anything you want to say.

  Surveys are scanned and transcribed into `docs/pilots/<date>/surveys.md`.
- **Data-quality review**: open the report (ADR 0008), the audit log, the metrics. Did detection work? Did the report make sense? Were there obvious bugs in the data? Captured in `docs/pilots/<date>/data-review.md`.

### 5. Learning capture

Each pilot ends with a single **document** at `docs/pilots/YYYY-MM-DD-<venue>.md` containing:

- **What worked** (3 bullets, evidence-based)
- **What didn't** (3 bullets, evidence-based)
- **What surprised us** (1–3 bullets, vibe-based, contradictions welcome)
- **What we'll change next time** (concrete actions, owners, ETAs)

These documents feed the quarterly ADR re-read (ADR 0041) — they're the *primary* source of evidence that drives status changes from Proposed → Accepted → Implemented or Deprecated.

### Pilot ladder

- **Pilots 1–5**: original team operates *and* observes. Internal participants (other team members, willing friends).
- **Pilots 6–10**: trained external facilitators operate; team observes. Real workshop sponsors. Real participants.
- **Pilots 11+**: external facilitator runs solo; team off-site. The protocol is now general.

## Consequences

**Positive:**
- Pilots become *comparable*. Lessons replicate or refute each other; we accumulate signal instead of anecdotes.
- Consent is consistently and visibly handled, removing the most likely participant-trust failure mode.
- The 30-minute alone-write captures the operator's gut (per ADR 0037) before social conversation contaminates it.
- Participant surveys are the single best calibration signal we have for "does this thing work?"

**Negative:**
- Adds ~4 hours of structured work per pilot (1 hr pre, 1 hr post-event, ~2 hr write-up + survey transcription). Mitigation: the write-up *is* the deliverable — without it the pilot didn't happen.
- Surveys are paper, manually transcribed — slow. Mitigation: 5 questions × 30 participants is ~30 minutes of typing; tolerable for the first 10 pilots, automate later if pilots scale.

**Risks:**
- A pilot has a participant trust failure (someone feels surveilled, surfaces it later). Mitigation: the protocol's consent + opt-out + post-survey gives multiple chances to surface and address discomfort.
- The "30-minute alone-write" gets skipped under time pressure; we lose the most honest signal. Mitigation: this ADR makes it non-optional; the pilot doc must contain the alone-write or the pilot is marked incomplete.

## Alternatives considered
- **No protocol.** Status quo; pilots improvise. Costs us most of the learning.
- **Heavy IRB-style protocol** with formal data-sharing agreements per pilot. Right scale for academic research; overkill for the first 10 workshops.
- **Skip pilots; ship to general availability.** Wrong by every criterion — the system isn't ready, and the first failure would damage trust more than postponing GA.
