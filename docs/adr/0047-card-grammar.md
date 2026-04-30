# ADR 0047 — Card grammar: how primitives compose

## Status
**Superseded by ADR 0061.** Six-slot sentence parsing is the wrong cognitive frame for a live workshop. Abandoned.

## Context
ADRs 0023–0029 give the kit **specific cards** (atom-level meaning). ADRs 0043–0046 give the kit **primitive cards** (modifier, subject, quantity, connector). Together that's a *vocabulary*. What's missing is the *grammar*: a rule for how multiple cards co-raised by one or more participants compose into a single, parseable, archivable event.

Without a grammar:
- Two cards raised by the same person within the same window are recorded as two unrelated events. *"I + WANT-SPEAK"* loses the structural link between subject and verb.
- Two cards raised by different people in the same window are at best a coincidence and at worst conflated. *"Anna's I + Bob's WANT-SPEAK"* must not become *"Anna wants Bob to speak"*.
- The audit log fills with raw card IDs, illegible six months later.

ADR 0022 specified a co-occurrence window. This ADR specifies how a window's cards are *parsed* into a structured event with a readable text rendering.

## Decision
Define a small **card grammar** in `backend/card_grammar.py` that the `ParticipantRouter` invokes per co-occurrence window.

**Per-holder grouping.** A window's cards are first partitioned by attributed holder (per ADR 0022). Each holder produces *one* compound event; cards held by different people in the same window are independent compound events.

**Slot model.** Each compound event has six slots, in this order:

```
[modifier_chain]  [subject]  [verb_atom]  [object_atom]  [connector + clause2]  [scope]
   STRONGLY         I          WANT         SPEAK            BUT + TENDER          NOW
```

Slots are filled greedily by card class:

- **modifier_chain** — any ADR 0043 modifier cards (preserve order; they layer).
- **subject** — first ADR 0044 pronoun card; defaults to the holder.
- **verb_atom / object_atom** — first one or two atom cards (reactions, intents, themes — ADRs 0023–0025); roles are inferred from card class.
- **connector + clause2** — first ADR 0046 connector splits the slot list; remaining cards are parsed recursively as a sub-clause.
- **scope** — ADR 0045 quantities, ADR 0026 compositions, or future time-scope cards.

**Sentence cap.** A single compound event accepts at most **5 cards**. A holder raising six or more cards within the window emits an `OVER_LIMIT` event with the raw list preserved; the operator sees a yellow flag in `/admin`. This caps grief and parser cost.

**Text rendering.** Every parsed event carries a human-readable `text` field. *Anna raises STRONGLY + I + INTENT_SPEAK + BUT + TENDER* → `"Anna: strongly want to speak, but tender."` This is what shows in the audit log, the operator's queue, and the report.

**Parse warnings.** Ambiguity (`BARELY + STRONGLY` together, `Q_3 + Q_5` without a connector, solo modifiers without an atom) is recorded as a `parse_warning: [...]` field. The event still fires; the warning is for review.

**Schema.** `ParticipantEvent` gains:

```python
modifier_chain: list[str]
subject: str               # "holder" | "I" | "YOU" | … with subject_target_aruco_id when relevant
verb_atom: str
object_atom: str | None
connector: str | None      # if a sub-clause follows
sub_clause: dict | None    # recursive structure for AND/OR/BUT/etc.
scope: str | None          # quantity or composition
text: str                  # human-readable rendering
parse_warnings: list[str]
```

Printed cards on the master PDF (per ADR 0030 deck editor) carry their *kit* tag visibly so participants can see whether they're picking up a modifier vs an atom — visual aid for grammar usage.

## Consequences

**Positive:**
- Compound events are *first-class*. The system understands "Anna wants to speak about trust because she's lived this" as one structured thing, not five disconnected card raises.
- The audit log becomes legible. Reading back a workshop is reading prose, not telemetry.
- Reports gain a narrative axis: *"five participants tagged their `TENDER` reaction with `BECAUSE GRIEF`"*. Coloured by causation.

**Negative:**
- Parser code is non-trivial. Mitigation: 200-line module; comprehensive tests for each slot-fill path. The grammar is small enough to fit in a single page.
- Ambiguous parses surface as warnings, not errors — operator must check them. Mitigation: `/admin` shows a parse-warning count badge that's normally near zero.

**Risks:**
- Greedy slot-fill picks the wrong card for a slot (e.g., assigns an atom as subject). Mitigation: card-class is hard-typed in `ParticipantCard.kit`, which the parser uses for unambiguous routing; the only ambiguity is *between cards of the same class*, which is rare and explicitly warned.
- Sentence-cap of 5 cards excludes legitimate complex thoughts. Mitigation: the cap is configurable per-deck; `BUT` chains emit an `over_clause` warning rather than truncation, preserving everything raw.

## Alternatives considered
- **No grammar; raw card list per window.** Audit log unreadable; no narrative reports.
- **Full programming language** (BNF, AST). Overkill, brittle, hard to brief participants.
- **LLM-based parsing** of the raw card list into prose. Tempting and probably worse — the parse becomes opaque, non-deterministic, and locale-fragile. The hand-rolled six-slot grammar is *enough*.

## Postscript
With the grammar in place, the participant kit stops being "a list of buttons" and starts being "a small constructed language the workshop speaks". The cards are the lexicon; the grammar is the syntax; the workshop is the corpus. The slide deck calls participants *witnesses*; the grammar is what gives their witnessing a *grammar*.
