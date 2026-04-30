# Architecture Decision Records

One decision per file, status `Proposed` until acted on. Each ADR is self-contained — read in any order, but several reference earlier ones (noted in the Status section).

## Platform & ops

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0001](0001-bearer-token-auth.md)              | Bearer-token auth on state-mutating routes              | —          |
| [0002](0002-alembic-migrations.md)             | Adopt Alembic for schema migrations                     | —          |
| [0009](0009-audit-log-and-structured-logs.md)  | Audit log + structured request logs                     | 0001       |
| [0010](0010-workshops-backups-retention.md)    | Workshop scoping, backups, retention                    | 0001, 0002 |

## Detection & geometry

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0003](0003-floor-homography.md)               | Per-camera floor homography for real-meter proximity    | —          |
| [0004](0004-marker-tracker.md)                 | Stateful marker tracker with temporal smoothing         | —          |
| [0005](0005-multi-camera-fusion.md)            | Multi-camera fusion via floor-plane merge               | 0003, 0004 |
| [0048](0048-aruco-pose-estimation.md)          | Real-time 6-DOF pose estimation per marker              | 0003, 0012 |
| [0049](0049-multi-placement-marker-strategy.md)| Multi-placement marker kit (hat + chest + back)         | 0048       |
| [0050](0050-3d-scene-reconstruction.md)        | 3D scene reconstruction by fusing pose across cameras   | 0005, 0048, 0049 |

## Crowdsourced sensing — every phone is a camera

ADR 0034 plans cameras as fixed infrastructure; ADRs 0051–0055 invert the
model. Participants log in, their phones become cameras, the mesh handles
the constant churn, the room itself converges its own coverage from the
ground floor up.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0051](0051-phone-as-camera-join.md)                       | Phone-as-camera join flow + lifecycle states          | 0034, 0050 |
| [0052](0052-dynamic-camera-mesh.md)                        | Dynamic camera mesh; cameras come and go invisibly   | 0051       |
| [0053](0053-ground-floor-coverage-convergence.md)          | Live coverage convergence + per-phone "fill the gap" pings | 0034, 0051, 0052 |
| [0054](0054-self-calibration-via-shared-markers.md)        | Self-calibration from anchors / cross-camera observations / IMU | 0012, 0048, 0049, 0050 |
| [0055](0055-quality-weighted-heterogeneous-fusion.md)      | Quality-weighted fusion for heterogeneous cameras    | 0050, 0051 |

## Make it real — production scaffolding

The first 55 ADRs say *what we'll build*. These five say *how we get there*:
hardware, schedule, pilot protocol, automated tests, and the document a
stranger reads on a Saturday morning and runs their first workshop on Tuesday.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0056](0056-reference-hardware-kit.md)         | Reference hardware kit — three tiers, today's BOM        | 0031, 0039 |
| [0057](0057-mvp-slice-90-day-rollout.md)       | MVP slice & 90-day rollout plan, three real workshops    | 0001–0055  |
| [0058](0058-pilot-workshop-protocol.md)        | Pilot workshop protocol — consent, briefing, debrief     | 0010, 0037, 0057 |
| [0059](0059-end-to-end-smoke-test.md)          | End-to-end smoke test + nightly + golden-fixture layers  | 0002       |
| [0060](0060-operator-handbook.md)              | Operator handbook & onboarding path (5 chapters)         | 0038, 0056, 0058 |

## Operator UX & workflow

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0006](0006-presenter-mode.md)                 | Presenter mode at `/present`                            | —          |
| [0007](0007-csv-roster-import.md)              | CSV roster import + bulk marker assignment              | —          |
| [0008](0008-tracking-timeline-replay.md)       | Tracking-session timeline replay UI                     | —          |

## Control markers — the room as the interface

These five all rest on the same idea: reserve a slice of the ArUco dictionary
as **system commands**, printed on cards. The operator runs the show by holding
cards up to the camera instead of clicking a laptop.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0011](0011-reserved-control-marker-ids.md)    | Reserve top 16 dictionary ids for system commands       | —          |
| [0012](0012-auto-calibration-corner-markers.md)| Auto-calibration via four floor-corner markers          | 0003, 0011 |
| [0013](0013-wand-zone-authoring.md)            | Author zones by walking the floor with a "wand" marker  | 0011, 0012 |
| [0014](0014-marker-driven-session-control.md)  | Hands-free session control: start/stop/next/snapshot    | 0011       |
| [0015](0015-anchor-drift-detection.md)         | Anchors detect camera drift and self-recalibrate        | 0011, 0012 |

## Magic & polish — the experience layer

What turns the system from a tool into an artifact people remember.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0016](0016-audio-cues.md)                     | Audio cues so the system stops being silent              | —          |
| [0017](0017-personal-reflection-card.md)       | One-page reflection card per participant                 | 0010       |
| [0018](0018-projection-mode.md)                | `/project` mode — the room as canvas                     | 0003       |
| [0019](0019-auto-highlight-reel.md)            | Auto-generated session highlight reel                    | 0008, 0010 |
| [0020](0020-cross-day-memory.md)               | Cross-day participant memory ("welcome back")            | 0010, 0017 |

## Participant cards — the room speaks back

ADR 0011 reserved 16 IDs as **operator** commands. ADRs 0021–0030 reserve 32
more as **participant** cards: a communal kit, picked up off a table, raised
by anyone in the room. The slide deck calls participants "witnesses" and
the kit is what gives them a voice the system can hear.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0021](0021-participant-control-markers.md)    | Reserve 32 IDs for participant cards (foundation)        | 0011       |
| [0022](0022-card-handling-semantics.md)        | Multi-hand input: pulse / level / gesture fire-models    | 0021       |
| [0023](0023-reaction-cards.md)                 | Reaction cards (yes / no / unsure / tender / lived / …) | 0021, 0022 |
| [0024](0024-theme-cards.md)                    | Theme cards — the room labels its own data              | 0021, 0022 |
| [0025](0025-intent-cards.md)                   | Intent cards — speak / listen / pair / pause / rest     | 0021, 0022 |
| [0026](0026-composition-cards.md)              | Composition cards — the room changes the rules          | 0021, 0022 |
| [0027](0027-witness-cards.md)                  | Witness cards — directional "I see you"                 | 0021, 0022 |
| [0028](0028-memory-cards.md)                   | Memory cards — participant-bookmarked moments           | 0021, 0019 |
| [0029](0029-promise-cards.md)                  | Promise cards — the closing commitment ritual           | 0017, 0020 |
| [0030](0030-custom-card-decks.md)              | Custom decks per workshop — the kit as instrument       | 0010, 0021–0029 |

### Grammar layer — the kit becomes a language

ADRs 0023–0029 give the kit *atoms* (one card → one meaning).
ADRs 0042–0047 give it *primitives* that compose: modifier + subject +
quantity + connector. Together they let participants build sentences
from a small vocabulary, instead of needing a dedicated card for every
shade of meaning.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0042](0042-card-budget-extension.md)          | Extend reserved range 32 → 96 IDs (138–233)              | 0011, 0021 (supersedes id-count portion) |
| [0043](0043-modifier-cards.md)                 | Modifier cards: STRONGLY / NOT / MAYBE / AS-IF / …      | 0042, 0047 |
| [0044](0044-pronoun-cards.md)                  | Pronoun cards: I / YOU / US / THEM / ANYONE / …         | 0042, 0047 |
| [0045](0045-quantity-cards.md)                 | Quantity cards: 0 / 1 / 2 / 3 / 5 / 10 / ALL / NONE     | 0042, 0047 |
| [0046](0046-connector-cards.md)                | Connector cards: AND / OR / BUT / BECAUSE / IF / …      | 0042, 0047 |
| [0047](0047-card-grammar.md)                   | Six-slot grammar — how primitives compose into events    | 0042–0046  |

## Limits & degradation — what the system actually does at the edges

The math behind "how many people, how many cameras, how fast" — and what the
system does when reality exceeds the configured envelope.

| #    | Decision                                                              | Depends on |
| ---- | --------------------------------------------------------------------- | ---------- |
| [0031](0031-resolution-marker-sizing.md)       | Resolution, marker size, detectable count per camera     | 0003, 0012 |
| [0032](0032-frame-rate-budget.md)              | Frame-rate budget by use case (FrameRouter)              | —          |
| [0033](0033-bandwidth-and-jpeg-quality.md)     | Bandwidth budget + adaptive JPEG quality                 | —          |
| [0034](0034-multi-camera-coverage-planning.md) | Multi-camera coverage planner with blind-spot diagram    | 0003, 0005, 0031 |
| [0035](0035-system-limits-and-degradation.md)  | Document the envelope + named degradation strategies     | every other ADR |

## Six Thinking Hats — different lenses on the whole

Six ADRs that step back from features and look at the system through the
six De Bono lenses. Together they cover *what we know*, *what we feel*,
*what could kill us*, *what we're for*, *what else could be*, and *how
we decide what we decide*.

| #    | Hat                                          | Decision |
| ---- | -------------------------------------------- | -------- |
| [0036](0036-white-hat-self-telemetry.md)       | 🤍 White (facts)       | Telemetry of the system itself        |
| [0037](0037-red-hat-operator-vibe-channel.md)  | ❤️ Red (feelings)       | Honour the operator's gut as data     |
| [0038](0038-black-hat-premortem-runbook.md)    | 🖤 Black (caution)      | Premortem & runbook with chaos drills |
| [0039](0039-yellow-hat-2028-destination.md)    | 💛 Yellow (optimism)    | The 2028 destination — wooden box, 50 facilitators, 1,000 workshops |
| [0040](0040-green-hat-twelve-wild-ideas.md)    | 💚 Green (creativity)   | Twelve wild ideas committed to paper  |
| [0041](0041-blue-hat-adr-lifecycle.md)         | 💙 Blue (process)       | ADR lifecycle, quorum, re-read cadence |

## Suggested implementation order

Smallest blast radius first, biggest leverage last:

1. **0002** — get migrations in place before any more schema churn (10 min).
2. **0001** — close the auth hole now while traffic is local-only (an afternoon).
3. **0009** — audit-log goes in cheap once auth lands; gives forensics for everything that follows.
4. **0016** — audio cues. Tiny diff, big confidence boost for the operator. Land before any production workshop.
5. **0006** — presenter mode is pure frontend; ships value to the next workshop with no backend risk.
6. **0007** — CSV import; biggest UX win for actual workshop setup.
7. **0011** — control-marker infrastructure. Cheap on its own; unlocks four more ADRs.
8. **0004** — marker tracker; visible jitter goes away.
9. **0014** — hands-free session control. First payoff of 0011 — the operator stops touching the laptop.
10. **0003** — homography model + manual calibration UI.
11. **0012** — auto-calibration via corner markers. Replaces 0003's manual UX with a 30-second floor-walk.
12. **0015** — drift detection on top of 0012's anchors. Catches silent-failure mode.
13. **0013** — wand-based zone authoring. Best done after the operator's tooling and detection are mature.
14. **0008** — timeline replay, reusing 0003's floor coords.
15. **0010** — workshop scoping + retention; right-sizes the data layer.
16. **0017** — personal reflection card. Right after scoping lands so the data is per-workshop.
17. **0020** — cross-day memory. Builds on 0010 and 0017 — the through-line that makes Czocha feel like one event.
18. **0018** — projection mode. The room becomes the canvas. Theatrical, but fully optional and zero-data-risk.
19. **0019** — highlight reel. Last because it's privacy-sensitive (frame storage) and best done once retention + auth are solid.
20. **0021** — participant-card foundation. Cheap on its own; unlocks the next nine.
21. **0022** — card-handling semantics. The protocol layer; without it the cards stay theory.
22. **0023** — reaction cards. The simplest, highest-impact participant card class. Ship first to validate the kit idea.
23. **0025** — intent cards. The operator's outlier-pick gets a queue.
24. **0024** — theme cards. The dataset gains language.
25. **0027** — witness cards. The mutual-acknowledgement layer the slide deck describes the workshop *as*.
26. **0026** — composition cards. The room can change the rules.
27. **0028** — memory cards. The reel becomes co-authored.
28. **0029** — promise cards. The closing ritual gains a recorded artifact.
29. **0030** — custom decks. Turns the system from a Czocha tool into a workshop instrument other facilitators can adopt.
30. **0005** — multi-camera fusion; the most ambitious infrastructure piece, easiest after everything else is in place.
