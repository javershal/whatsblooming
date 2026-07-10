# Phase 1 — Schema Decision & Data Provenance

> Phase 1 deliverable. Defines the enriched corpus schema, where each field
> comes from, and the deliberate boundaries on the data. Companion to
> `rubric.md` (Phase 0). The corpus itself is `data/trailside_plants.json`
> (29 plants) + `data/places.json` (place→habitat lookup).
>
> **The one rule still governs:** the data is *not* the deliverable. This phase
> is bounded on purpose — fill the schema for a fixed set, then stop. A thin,
> imperfect corpus is a feature: it gives the Phase 4 harness real grounding and
> refusal failures to catch.

---

## 1. The fixed set (locked)

**29 Monterey-area natives**, curated to span all 7 habitats with showy,
trip-planner-recognizable species and at least one winter bloomer (coast silk
tassel, big-berry manzanita) so the seasonal eval has off-peak cases. The set is
deliberately capped — comprehensiveness is explicitly out of scope.

## 2. Schema (per plant)

| Field | Source | Notes |
|---|---|---|
| `common_name`, `scientific_name` | Calflora | carried from existing `data/plants.json` |
| `growth_habit` | Calflora | tree / shrub / perennial herb — useful "what will I see" context |
| `native` | Calflora | always `true` (corpus is natives-only by design — see rubric §4) |
| `bloom_months` | Calflora | integer months 1–12; the spine of the project |
| **`habitat`** | **Calflora → mapped** | **the load-bearing field**; array of Trailside-vocab habitats |
| `habitat_source` | — | `"calflora"` or `"calflora+curator"` — flags the 3 curator-corrected records (see §5) |
| `habitat_raw` | Calflora | verbatim CNPS community names, kept so the mapping is auditable |
| `curator_note` | — | present only on curator-corrected records; states what was added and why |
| `description` | authored | one faithful, hiker-facing line (form + flower + field note) |
| `calflora_url`, `calscape_url` | — | provenance pointers |
| `photo_url`, `photo_attribution` | Calflora | |

**Dropped from the original Phase-1 schema:** `sun` and `water`. Those are
landscaping/horticulture attributes (how to grow a plant in a garden), not
"where will I encounter it on a hike." Out of scope for the trip-planner persona.

### Why habitat is a list, not a single value
Real natives span communities (coast buckwheat is both bluff-scrub *and* dune;
California poppy spans four). A single "primary habitat" would mislabel them and
make place-matching miss real blooms. The array is truer to the ground and lets
"what's at [place]?" match plants across all of a place's communities.

## 3. Habitat vocabulary (7) and the mapping

Controlled vocab — finalized as **7**, adding *coastal dune/strand* to the
hand-off's 6, because a large share of Monterey's iconic wildflower spots are
dunes (Asilomar, Marina) and forcing dune plants into "bluff scrub" would erase
a real, distinct community:

> coastal-bluff scrub · coastal dune/strand · chaparral · oak woodland ·
> riparian · grassland · Monterey pine forest

Calflora reports each plant's communities using **CNPS/Munz statewide community
names**. The mapping (in `scripts/build_trailside_corpus.py`):

| Calflora community | Trailside habitat |
|---|---|
| Northern Coastal Scrub, Coastal Sage Scrub | coastal-bluff scrub |
| Coastal Strand | coastal dune/strand |
| Coastal Prairie, Valley Grassland | grassland |
| Chaparral | chaparral |
| Closed-cone Pine Forest | Monterey pine forest |
| Northern/Southern Oak Woodland, Foothill Woodland, Mixed Evergreen Forest | oak woodland |
| wetland-riparian | riparian |
| Yellow Pine / Red Fir / Lodgepole / Subalpine Forest, Redwood Forest, Joshua Tree Woodland, Creosote Bush Scrub, Sagebrush Scrub | **dropped** (outside the Monterey planning area) |

## 4. Place → habitat lookup (`places.json`)

A small, **sourced** lookup so place-named questions ("what's at Point Lobos?")
resolve to plant communities at the rubric's chosen granularity (habitat, not
trail-microsite). Each entry records `attested_communities` (what the cited
source actually says), the mapped `habitat`, a `source` URL, and a `confidence`
flag. Per rubric §8, an *unsourced* "Point Lobos is coastal scrub" is the same
confabulation the harness exists to catch — so mappings that are inferred rather
than attested are flagged as such, not laundered into facts.

Shipped: **Garland Ranch** (high confidence), **Asilomar State Beach** (medium),
**Point Lobos** (medium). **Fort Ord** was intentionally *excluded*: its
signature maritime chaparral is well known but I could not find a citable source
that names its communities, so asserting them would be confabulation. It is
logged here as a deliberate gap and is a good candidate for a Phase 2
*weak-source* eval case (does the assistant over-trust a place it can't ground?).

## 5. Mapping-review policy: keep over-assignments, fix under-assignments

A Phase-1 review of all 29 mappings surfaced two *different* kinds of
imperfection, handled by opposite rules — a deliberate data-governance call:

- **Over-assignments are kept, untouched.** Calflora's statewide `Communities`
  leaks locally-marginal habitats onto some plants (hummingbird sage, coffeeberry,
  coast twinberry pick up a dune tag; seep monkeyflower maps to all 6 land
  habitats). These are left exactly as sourced — they are the *grounded-but-not-
  locally-true* material (finding #1) the Phase 4 harness is meant to catch as
  S1 over-inclusion failures. Hand-cleaning them would hide the very problem.

- **Under-assignments are corrected, transparently.** Calflora's per-(sub)species
  records have silent *gaps* that make the corpus quietly incomplete — a miss that
  teaches nothing rather than a faithful imperfection. Three were corrected via a
  flagged curator override (`habitat_source: "calflora+curator"` + a `curator_note`),
  using local-expert knowledge as a transparent, **non-laundered** authority:

  | Plant | Added | Why |
  |---|---|---|
  | Blue-eyed grass | grassland | the quintessential spring grassland flower; Calflora omitted it |
  | Coast Indian paintbrush | coastal-bluff scrub | common in Monterey coastal scrub; record had only Valley Grassland |
  | Toyon | oak woodland | classic oak-understory shrub; record had only Chaparral |

The asymmetry is the point: **provenance integrity is not "never edit" — it's
"never edit silently."** Faithful machine mappings and curator corrections are
distinguishable in the data forever, which is the auditability an enterprise
grounded-assistant program would need.

## 6. Two findings worth surfacing

1. **Calflora's `Communities` field is statewide, not local.** Faithfully
   importing it tags some plants with locally-marginal habitats (e.g. hummingbird
   sage and coffeeberry inherit "Coastal Strand"/dune because they occur on dunes
   *somewhere* in California). This is left in on purpose: it is a textbook
   *grounded-but-not-locally-true* case, and the Phase 4 harness should catch the
   resulting over-inclusion (an S1 completeness failure) rather than the data
   being hand-cleaned to hide it. Same shape as an enterprise assistant
   faithfully reporting a spec that's right for the wrong building.

2. **Place sourcing is thinner than plant sourcing.** Plant-community data is
   structured and citable (Calflora); place-community data is scattered across
   marketing pages. That asymmetry is exactly why the rubric draws the granularity
   floor at *habitat* and gates trail-microsite precision behind a future data
   source — the boundary is data-gated, not arbitrary.

---

## 7. Seeds for Phase 2 (ground-truth set) — start here next session

> **Reading order for a fresh session picking up Phase 2:** (1) memory
> `project-trailside-eval`, (2) `Eval project handoff.md` §"Phase 2", (3)
> `trailside/rubric.md` (the standard each ground-truth answer encodes), (4) this
> file, (5) `data/trailside_plants.json` + `data/places.json` (the facts to author
> against). Phase 2 is **[CHAT / Opus + extended thinking]** for the tricky cases.

The corpus was built with specific imperfections *on purpose* so the ground-truth
set has real failure surface. Concrete test-case seeds this corpus now supports:

- **S1 over-inclusion (the money case).** "What's blooming on the **dunes** in
  summer?" — a faithful-but-naive answer wrongly includes hummingbird sage /
  coffeeberry / coast twinberry (the kept statewide-dune leaks, §5). The *good*
  answer excludes them. This is the near-miss pair that makes finding #1
  demonstrable in Phase 4.
- **Weak-source place refusal.** "What's blooming at **Fort Ord**?" — Fort Ord is
  deliberately absent from `places.json`. Correct behavior = hedge/refuse, not a
  confabulated habitat. Pair it with "what's at **Garland Ranch**?" (well-sourced,
  should answer) as a near-miss.
- **Seasonal-conditional (the hero category).** "Is the **lupine** out yet?" —
  arroyo lupine blooms **Feb–May**; the right answer depends on the asked/again
  date and must *hedge*, never flat yes/no. ⚠️ **Design decision still open:**
  time-conditional ground-truth can't be a fixed string — it must encode the bloom
  window + seasonal logic, evaluated against an **injected reference date** (the
  harness supplies "today"; do NOT hardcode 2026-06-29). Decide the representation
  when designing the `ground_truth.json` schema.
- **Off-peak / winter blooms.** "Anything worth seeing in **December**?" → coast
  silk tassel (Nov–Feb), big-berry manzanita (Jan–Feb). Guards against a harness
  that only works in spring.
- **Place→habitat resolution.** "What's at **Point Lobos** in April?" → resolve to
  coastal-bluff scrub + Monterey pine forest, then the April bloomers in those
  habitats; explicitly *exclude* inland oak-woodland-only species.
- **Completeness + cap.** "Blue/purple flowers on the coast in spring" → multiple
  lupines + Douglas iris + seaside daisy etc.; expected answer must store the
  **complete count** even though the assistant caps at 5 (rubric §5 / S1).
- **Out-of-scope refusals / redirects.** Garden care ("aphids on my roses"), photo
  ID ("what's this purple flower" + image), trail-microsite ("exactly what's at the
  mile-2 overlook at Garland Ranch"), non-corpus plant, non-region ("wildflowers in
  Joshua Tree"). Each maps to a row of the rubric §6 gradient.

⚠️ **Open design decisions for Phase 2** (don't pre-decide — these are the Opus
judgment work): the concrete `ground_truth.json` entry schema; how to represent
seasonal-conditional expected answers + the injected-date contract; category +
difficulty tag vocabulary; and which `should-retrieve` source(s) each question
pins (a plant record, a place record, or "none → refuse").
