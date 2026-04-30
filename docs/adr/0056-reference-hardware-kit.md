# ADR 0056 — Reference hardware kit ("the wooden box v0.1")

## Status
Proposed.

## Context
ADR 0039 promises a wooden-box kit by 2028. Today every operator pieces together their own hardware: webcam-from-laptop, no projector, anchor markers printed on regular A4. We've never sat down and decided *"if you want to run a workshop tomorrow, here's the BOM."* Without a reference kit:

- Every new operator reinvents purchasing decisions and sometimes makes wrong ones (e.g., 720p webcam in a hall sized per ADR 0031).
- Pilot workshops (ADR 0058) compare across heterogeneous setups, contaminating the learning.
- The cost-of-entry to running a workshop is opaque, gating adoption.
- The path to ADR 0039's wooden box has no waypoints — we can't bulk-buy anything because we don't know what's in the box.

## Decision
Maintain `deploy/HARDWARE.md` documenting **three reference kits**, each orderable today, each with prices, sources, and sized to a workshop scale.

### Tier 1 — Solo ($350–$500 USD)
- 1× **Logitech C922 Pro Stream** webcam (1080p / 60 fps · ~$80)
- 1× **MacBook / mid-range Linux laptop** with the system installed (existing or ~$300 used)
- 4× **A4 sheet anchor markers** (printed at home, ~$2)
- 1× **roll black gaffer tape** for floor anchoring (~$10)
- *No projector, no participant phone-cameras, no participant kit beyond the markers themselves.*

Sized for: pilot workshops up to ~30 people, single operator, single fixed camera at gallery height.

### Tier 2 — Standard ($1,500–$2,500 USD)
- 2× **Logitech C922** webcams (one main, one rear) ($160)
- 2× **operator laptops** (existing) or 1 laptop + Raspberry Pi 5 with USB capture ($120)
- 1× **Brother HL-L2350DW** monochrome laser printer ($130) — for on-the-day reflection cards (ADR 0017)
- 1× **BenQ TH671ST short-throw projector** (~$650) — for `/present` and `/project` (ADRs 0006, 0018)
- 1× **9'×6' projector screen / blank wall** (no cost)
- Anchor + ChArUco board kit, A3 laminated (~$30)
- **Sourcing**: B&H Photo, Newegg, Amazon Business

Sized for: workshops 30–80 people, two operators, redundant fusion (per ADR 0005).

### Tier 3 — Pro ($4,000–$6,000 USD)
- 6× **Logitech Brio 4K** webcams ($1,200) — slide-deck six-camera setup
- 3× **operator laptops** ($1,500–2,500 used)
- 2× **short-throw projectors** ($1,300) — one for `/present` audience-facing, one for `/project` floor projection
- 1× **colour laser printer** for personal reflection cards in colour (~$300)
- **Pre-printed participant kit**: 200× hat markers, 200× chest+back marker lanyards (laminated), bagged per-person. Bulk-printed (~$300).
- 1× **Pelican 1620 hardware case** for transport ($300)

Sized for: 80–150 people, the slide-deck Czocha configuration, pre-bagged kits for fast registration (~15 sec per participant).

### What ships with the repo

- `printable/anchors.pdf` — four corner anchors at the right physical size, A4 ready-to-print.
- `printable/charuco-board.pdf` — single ChArUco board for ADR 0048 intrinsic calibration, A3.
- `printable/marker-roster-template.pdf` — for bulk printing person markers with assigned names underneath, A4 grid layout.
- `deploy/HARDWARE.md` — the BOM tables above, plus a "alternatives at different price points" appendix for each line item.

## Consequences

**Positive:**
- A new operator orders the right thing on the first try.
- Pilot workshops (ADR 0058) standardise on Tier 2 by default — fair comparisons.
- Aggregate purchasing across teams becomes possible. Buying 50 of the standard webcam from a single source unlocks discounts.
- The BOM is the *first concrete waypoint* toward ADR 0039's wooden box.

**Negative:**
- Maintaining a hardware document with prices means it goes stale (prices shift, products discontinue). Mitigation: revisit at quarterly ADR re-reads (ADR 0041); flag deprecated items rather than rewrite.
- Vendor-specific recommendations bias adoption toward US-centric sourcing. Mitigation: include EU + Asia equivalents per major item.

**Risks:**
- Operators interpret the kit as a *requirement* rather than a *baseline*. Some workshops will work with cheaper hardware; some will need more. Mitigation: each tier opens with *"this is the no-think default; deviations are fine if you understand ADR 0031's resolution math."*
- Bulk-printed marker kits lock in the dictionary choice (`DICT_4X4_250` vs `DICT_4X4_1000`) for the next ~6 months until the next print run. Mitigation: print-runs match the workshop pipeline, with explicit ADR 0049 budget warnings before reordering.

## Alternatives considered
- **No reference kit; let operators figure it out.** Status quo. Costs every new adopter the same hours of decision overhead.
- **Single recommended kit** instead of three tiers. Forces budget compromises that don't fit every venue.
- **Skip directly to the wooden box** (ADR 0039). Three years premature; we don't yet know what should be in it.
