# ADR 0030 — Custom card decks: the kit as a per-workshop instrument

## Status
Proposed (depends on ADR 0021–0029, 0010 workshop scoping).

## Context
ADRs 0023–0029 fix specific cards into specific roles: `REACT_YES`, `THEME_TRUST`, `INTENT_SPEAK`, etc. That's right for *Day 1, The Opening, at Czocha* — those words match the slide deck. It's wrong for every workshop that isn't this one.

A workshop on grief and loss needs different theme cards than one on entrepreneurship. A workshop in Polish wants Polish words on the cards, even if the system protocol is English. A new facilitator might want their own intent vocabulary — `INTENT_OBSERVE` instead of `INTENT_LISTEN`.

The 32 participant IDs are abstract slots. The slot's *meaning* — the word printed on the card, the action it triggers, the rate-limit it carries — is **per-deck**, and each workshop binds a deck to itself.

## Decision
Make the participant deck a **first-class, editable, per-workshop object**.

- New `CardDeck` table: `id`, `workshop_id` (nullable — global decks are workshop_id=null), `name`, `parent_deck_id` (decks can inherit), `created_at`.
- New `CardBinding` table: `deck_id`, `marker_aruco_id`, `kit` (one of `reaction|theme|intent|composition|witness|memory|promise|custom`), `name`, `label`, `action`, `params_json`, `enabled`. One row per active card in the deck.
- `Workshop` (ADR 0010) gains an `active_deck_id`. `ParticipantRouter` resolves the meaning of every participant card by looking it up in the active deck.
- A "Card kit editor" tab in `/admin`:
  - List the deck, drag to reorder, edit each card's name/label/action/enabled state.
  - **Print the deck** as a PDF — every card in one document, with its marker on one face and its label + brief description on the back.
  - **Fork the deck** — clone the workshop's current deck as a starting point for a sister workshop.
  - **Promote a card to global** — once a card has been used and refined across multiple workshops, the operator can mark it as a global default for new decks.

A small set of **safety invariants** are enforced:
- A card whose `kit` is `composition` or `promise` is rate-limited more aggressively than reactions.
- A card whose `name` matches a built-in operator command (`TRACK_START`, etc.) is rejected on save.
- A deck must contain at minimum one of each: reaction, intent, theme. (Or it's not a workshop kit; it's a research project.) Operator can override the minimum on save with a confirmation.
- Disabling all reaction cards triggers a soft warning ("the room will have no reaction channel") rather than a hard block — research workshops sometimes want this.

## Consequences

**Positive:**
- The system stops being *a Czocha tool* and becomes *a workshop instrument* that ships with a Czocha kit. Other facilitators can adopt it without touching Python.
- Per-workshop decks make data segmentation trivial: the *trust* card in the spring workshop is a different row in the table from the *trust* card in the autumn workshop, even though they share the marker ID. Reports can compare across decks or filter to one.
- The deck is a *cultural object* — a thing a facilitator iterates on between workshops, like a deck of slides or a question script.

**Negative:**
- More schema, more UI. Mitigation: ships with two built-in decks (Czocha Day 1, Czocha 5-day), so 90 % of the value is delivered without users ever opening the kit editor.
- Per-deck card meaning means a participant's gesture *cannot* be interpreted across workshops with different decks. That's correct semantically, but means cross-workshop reports (ADR 0010) need careful schema choices.

**Risks:**
- A facilitator builds a deck that maps `THEME_GRIEF` to a destructive action. The kit editor prevents binding to operator-reserved kits, but it doesn't prevent a strange semantic mapping. Mitigation: the kit editor shows a "this card will fire `<action>`" preview before save; destructive actions require confirmation.
- A card from one workshop accidentally fires in another (the participant brought a card home, brings it back). Mitigation: `ParticipantRouter` ignores any participant card not present in the active workshop's deck; the event is logged, not fired.

## Alternatives considered
- **Hardcoded cards forever.** Sufficient for a single workshop format; doesn't compose.
- **YAML-as-deck files.** Cleaner version control, harder UX for non-developer facilitators. The kit editor's "export to YAML" is the bridge.
- **One global deck shared across workshops.** Simpler, loses the per-workshop semantic clarity that makes the data interesting six months later.

## Postscript
This ADR is the last of the 0021–0030 sequence and intentionally so: it's the meta-decision that turns the previous nine into a *system you can extend*. The 32 IDs are not "32 hardcoded features"; they're 32 sockets, and the deck is what plugs into them. A workshop becomes a *configuration of the kit*, and the kit becomes part of the workshop's identity.

The slide deck describes a hundred strangers becoming a hundred witnesses by stepping into a circle. The corresponding system idea is: the kit is the language they speak while doing it, and the language is theirs to author.
