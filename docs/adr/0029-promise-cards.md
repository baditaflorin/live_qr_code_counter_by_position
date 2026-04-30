# ADR 0029 — Promise cards: the closing commitment

## Status
Proposed (depends on ADR 0021, 0022, 0017 reflection cards, 0020 cross-day memory).

## Context
The slide deck's Day 5 (*The Return*) ends with one question: *"what do you carry home?"* — and a closing ritual whose details the deck leaves to the facilitator. In practice this is the moment the workshop is designed for: each participant says, out loud or to themselves, what they intend to do differently.

Today this moment is recorded only in the participants' memories. By Friday afternoon they are gone. Six weeks later they're back at work, the promise unrecalled, the workshop a fading photograph.

A small physical artifact — a card raised in the closing circle, optionally attached to a written or spoken promise — turns the commitment into a thing that survives the room.

## Decision
Add **2 promise cards** to the participant deck — `PROMISE` and `PROMISE_SHARED` — both `gesture`-mode (per ADR 0022).

- **`PROMISE`** is private. Raised by a participant during the closing ritual. The system records `PromiseEvent(t, holder_aruco_id, scope: "private", body: null)`. The reflection card (ADR 0017, end-of-week edition) includes a single dedicated panel: *"The promise you made to yourself, on Friday at 16:23: ____________"* — left blank for the participant to fill in by hand on the printed card.

- **`PROMISE_SHARED`** is public. Same gesture, but the participant has consented in advance (a checkbox at registration) to having their voice recorded. The card raise *also* triggers a 30-second microphone capture from the operator's laptop. The transcript is processed offline (whisper.cpp, locally — no cloud), attached to the reflection card, *and* added to the workshop's collected promises corpus.

A weeks-later follow-up email (ADR 0010 retention policy makes this safe to do): *"Six weeks ago, you promised to ___. How is that going?"* — with the promise text restored from the recording.

The promise count is rendered on `/present` during the closing ritual as a quietly growing number — *"X / N people have made a promise"*. No names. The room sees its own commitment level.

## Consequences

**Positive:**
- The moment the workshop is designed for is captured. The artifact endures.
- Shared promises form a corpus over time — anonymised excerpts can become future workshop material ("things people promised themselves at Czocha").
- The follow-up email is uniquely powerful: the *participant's own voice*, weeks later, asking themselves how they're doing.

**Negative:**
- The microphone capture introduces an audio pipeline (whisper.cpp local). Yet another dep, modest but real.
- The follow-up email requires a contact channel — registration must collect email and consent.

**Risks:**
- A participant raises `PROMISE_SHARED` thinking it's private. Mitigation: card design and pre-workshop briefing make the distinction unambiguous; consent is collected at registration *and* re-confirmed on the printed card via the participant's signature before the audio is processed.
- Recording in a room of 100 people picks up everyone's audio. Mitigation: a directional mic on the operator's laptop limits range; transcripts are speaker-segmented; only segments coincident with a `PROMISE_SHARED` raise are kept.
- The follow-up email feels like surveillance instead of care. Mitigation: opt-in at registration *and* opt-out after the workshop; default is "no follow-up" unless the participant ticks "yes please".

## Alternatives considered
- **No promise capture.** The most common state in the wild. The closing ritual happens, the data layer is silent. Acceptable, but the system can do more with little additional friction.
- **Written-only promises (no card, no audio).** Simpler, loses the closing-ritual physical gesture and the spoken-voice artifact.
- **Phone-app commitment tracking.** Industry standard, completely the wrong vibe for the closing ritual the slide deck describes.
