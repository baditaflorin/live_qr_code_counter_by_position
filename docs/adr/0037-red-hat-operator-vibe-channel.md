# ADR 0037 — ❤️ Red Hat · Honour the operator's gut as data

> *Red Hat: feelings, intuitions, hunches. No need to justify them.*

## Status
Proposed (complements ADR 0036's data-only view).

## Context
Most ADRs avoid feelings. They reason from facts and decide from logic — and they're right to, in most domains. This domain isn't most domains.

A facilitator running an opening exercise at Czocha is an instrument. They feel the room before the room knows it has a feeling. *"Something just shifted"* is real information. *"This snapshot is the one"* is a reading by someone who has run a thousand of these. The system today gives that reading **nowhere to go**. Every input the operator can give is logical: click this, drop this zone, advance this question. The gut has no channel.

Ignoring the operator's gut produces a tool that *fights* the room — statistically rich snapshots that miss the moment, an algorithm-picked outlier when the operator already knew who to invite. That's not a sensor problem. It's a design choice we're making by default.

## Decision
Add an explicit **vibe channel** for the operator. No data analysis, no filtering by it, no metric attached. The system *listens* to the operator's gut and *preserves* it verbatim.

A `MoodFlag` table: `(t, actor_token_hash, tag, free_text, attached_to_kind, attached_to_id)`.

Default tag set, single-keystroke from `/admin` (no menus, no friction):

| Key | Tag                | Meaning                                                |
| --- | ------------------ | ------------------------------------------------------ |
| `B` | `beautiful`        | "I want to remember this exactly."                     |
| `T` | `tender`           | "Hold the silence; nothing data-driven happens here."  |
| `Y` | `tense`            | "The room is holding something. Let it settle."        |
| `S` | `something-shifted`| "The arc just changed."                                |
| `K` | `worth-keeping`    | "The reel needs this clip even if metrics say no."     |
| `X` | `worth-cutting`    | "The reel doesn't need this clip even if metrics say yes." |
| `?` | `i-don't-know`     | "I felt something. Naming it later."                   |

How they propagate:

- Flags attach to whatever was active at the keystroke moment: the current question, the current tracking session, the most recent snapshot.
- The highlight reel (ADR 0019) treats `worth-keeping` as a hard include and `worth-cutting` as a hard exclude — overrides the geometry-based picker.
- The personal reflection card (ADR 0017) doesn't show flags directly, but a participant near a `beautiful` moment gets a tiny phrase on their card: *"the room marked this moment as one to keep."*
- The closing reel narration (when ADR 0040 wild-idea #6 lands) opens flagged moments with a different cadence than statistical ones.

The flags are **operator-private** by default. The reflection card never names the flagger. The reel never says "the operator flagged this."

## Consequences

**Positive:**
- Subjective reading is finally captured before the workshop ends. A facilitator's hunch survives into the artefact.
- The operator works *with* the system instead of *despite* it. Trust improves because the system listens.
- A junior facilitator gets a mentor's gut in writing — flags from a senior operator's session become training material.

**Negative:**
- Flags are subjective. Two operators on the same room would tag differently. That's the *point*, not a bug.
- The Red Hat's data is incommensurable with the White Hat's (ADR 0036). They live side-by-side, not in a unified report.

**Risks:**
- A `tender` flag could be used to mask a moment that ought to be reviewed for safety reasons. Mitigation: flags don't suppress audit logging (ADR 0009); the moment exists in both layers.
- Flag fatigue — operators get into a flagging rhythm and lose discrimination. Mitigation: zero pressure to flag; the system works fine if no flags are ever set; the channel is *available*, not *required*.

## Alternatives considered
- **Free-text journal only** — too high-friction during a live session. The keystroke-tag set is one-handed and silent.
- **Voice memo** — breaks the slide-deck silence; transcription introduces lag and error.
- **No vibe channel** — current state. Forces the operator to remember the moment until the debrief, which doesn't survive the rest of the workshop.
