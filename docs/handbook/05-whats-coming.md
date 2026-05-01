# 5 · What's coming

*Reading: 10 minutes.*

The system you've just learned is still moving. This chapter sets honest
expectations for what's coming and how to contribute.

## The 2028 destination

By 2028 ([ADR 0039](../adr/0039-yellow-hat-2028-destination.md)):

- **50 facilitators** outside the original team running workshops.
- **1,000 recorded workshops**, with consent, in a privacy-respecting corpus.
- **Three peer-reviewed papers** citing the proximity-graph methodology.
- **The kit ships in a wooden box** — Pi 5, cameras, anchor markers,
  projector, pre-loaded SD card.
- **A public deck library** — 30+ reusable per-workshop kits.
- **One person** can install, configure, run, and debrief without touching
  Python.

This handbook is the bridge from *"developers can use it"* to *"facilitators
can use it."*

## The next 90 days

The current plan is laid out in [ADR 0057](../adr/0057-mvp-slice-90-day-rollout.md).
Three phases, each ending with a real workshop:

| Phase | Days | Lands |
|---|---|---|
| 1 | 0–21 | Auth + Alembic + audit log + 5 starter metrics + 1 internal workshop |
| 2 | 22–49 | Presenter mode + CSV import + audio cues + control-marker foundation + 4 hands-free cards + 3 external workshops |
| 3 | 50–90 | 6-DOF pose + multi-placement markers + phone-as-camera join + tier-1 calibration + 1 phone-camera pilot |

Items in **bold** in [`docs/adr/README.md`](../adr/README.md) are shipped
to prod. Everything else is design intent.

## How to contribute

If you ran a workshop with this system:

1. **File a pilot report** at `docs/pilots/YYYY-MM-DD-<venue>.md` using the
   template in [`PILOT-PROTOCOL.md`](../../deploy/PILOT-PROTOCOL.md).
   These reports are the *primary* signal driving ADR re-reads.
2. **Open an issue** for any bug or paper-cut you hit.
3. **Propose an ADR** if you found a design decision worth making —
   format in [`docs/adr/README.md`](../adr/README.md), anything you'd
   tell the next operator counts.

If you want to develop the system:

- Read `docs/adr/` (~75 ADRs, grouped by family).
- Run `make test-smoke` — that's the green-or-red signal for any change.
- Pick a single ADR, implement it, file a PR. Keep ADRs as the unit of
  work, not features.

## What we won't add

The system has a deliberate scope. Things we will not build:

- **Face recognition.** The system identifies *markers*, not people.
  Take the marker off, you're invisible. This is a feature, not a gap.
- **Cloud SaaS.** The destination is a wooden box, not a website. The
  data lives in your container.
- **Ad-targeting / analytics-as-a-service.** Workshops are a privacy-
  sensitive context. We don't ship a path to monetising the data.

## Where to send your first pilot report

`baditaflorin@gmail.com` — until a more durable channel exists.

The team reads every report. Pilots 1–10 will probably surface things
that surprise everyone, including the team.

---

✅ **You've done this if:** you know where to send your first pilot
report.

🎓 **Handbook complete.** You can now run a workshop end-to-end. If you
find something this handbook didn't prepare you for, that's the most
useful thing you can report.

→ Back to [Chapter 1](01-what-this-is.md), or [the ADR set](../adr/README.md), or `make test-smoke` and start.
