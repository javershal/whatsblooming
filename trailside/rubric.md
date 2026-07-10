# Trailside — Quality Rubric & Scope of Competence

> Phase 0 deliverable. This file defines *the standard an answer is judged
> against*, before any data or code exists. It is the spine that Phase 2
> (ground-truth set) and Phase 4 (eval harness) are built to enforce.
>
> **The one rule (inherited from the handoff):** the eval harness and the
> methodology are the deliverable; the live chatbot is not. A thin corpus is a
> feature — it makes the assistant confabulate and over-answer, which is exactly
> what this rubric exists to catch. The headline failure to hunt for is
> **graceful refusal vs. plausible-but-ungrounded confabulation.**

---

## 1. Persona (locked)

**A Monterey-area hiker planning a trip**, not identifying a plant in hand. The
user opens Trailside *before* heading out, to understand what they're likely to
encounter and to decide where to go based on what's in bloom.

- **Prospective** — answers are *predictions/expectations* ("what you'll likely
  see"), not live observations.
- **Decision-driving** — the answer feeds a go / don't-go / where-to-go choice.
  A factually correct but useless answer ("lots blooms in spring") is a failure.
- **Plan-first, mobile-tolerant** — designed for at-desk planning (thorough,
  ranked), but answers stay tight enough to survive on a phone at the trailhead.
  Rewards completeness; penalizes rambling.
- **Tolerant of uncertainty *if it is honest*** — a planner can act on "lupine
  usually peaks mid-April" but is actively misled by a flat "yes, it's blooming."

**Explicitly NOT this persona:** the in-field visual identifier. Photo / "what's
this purple flower" ID is **out of scope** (routed to Google Lens / iNaturalist
— see §4).

## 2. Jobs to be done

- **J1 — place + time → blooms:** "What might I see at [place] around [time]?"
- **J2 — flower → place + time:** "I want to see [plant]; where and when do I go?"

Both pivot on **bloom timing**. Time is the spine of the project, and it runs
both directions (given time → predict blooms; given bloom → predict time). This
is why seasonal-conditional correctness is the hero finding, not an edge case.

## 3. Question taxonomy

| Type | Examples | Job |
|---|---|---|
| Place + month → blooms | "What's blooming at the headlands in April?" | J1 |
| Trip-worthiness judgment | "Worth going to Garland Ranch for flowers now?" | J1 |
| Flower → where/when | "Where and when can I see poppies?" | J2 |
| Time-conditional ("out yet?") | "Is the lupine out yet?" | J2 |
| Attribute lookup | "What purple flowers are on the coast this spring?" | J1/J2 |
| **Out of scope** (must refuse/redirect) | photo ID; aphid/garden care; trail logistics; non-corpus plants/regions; *live current-week certainty*; trail-microsite precision | — |

> **Note on the "now" vs. "stated month" split:** a *time-conditional* question
> ("out yet?") is only correct relative to today's date, so its ground-truth
> answer can't be a fixed string — it must encode the seasonal logic. A
> *stated-month* question ("…in April") pins the time explicitly and fails
> differently. Phase 2 treats these as distinct categories.

## 4. Scope of competence

The granularity decision (**habitat / plant-community**, not trail-microsite)
and the **typical-vs-current** distinction define the boundary. Naming these on
purpose is the PM move.

### IN scope — the assistant should answer
- **Typical/expected bloom timing** for the fixed ~20–30 native set, by month.
- **Habitat associations** — what grows in coastal-bluff scrub vs. chaparral vs.
  oak woodland vs. riparian vs. grassland (one `habitat` field per plant).
- **Where-to-see at habitat granularity** — map a named local place to its
  plant community(ies), then answer from the community ("Point Lobos is mostly
  coastal-bluff scrub + Monterey pine forest, so…").
- **Attribute-filtered lookup** — plants matching a description + context
  ("purple flowers on the coast in spring").
- **Documented description facts** present in the corpus.

### OUT of scope — refuse or redirect
- **Live/current certainty** ("is it blooming *this exact week*"). The corpus
  knows "blooms Mar–May," not today. Answer with typical timing + an honest
  hedge; never a flat yes/no. *(Direct analog to a grounded enterprise assistant
  stating a spec value with false confidence vs. "as of the doc version you gave
  me.")*
- **Trail-microsite precision** ("exactly what's at the mile-2 overlook"). Below
  habitat granularity → refuse; we have no trail-level survey data. (See §8 for
  why this is a deliberate, data-gated boundary, not just a gap.)
- **Photo / visual species ID** → redirect to Lens / iNaturalist honestly.
- **Plants or regions outside the fixed corpus / outside the Monterey area.**
- **Garden, horticulture, pest care** (e.g. "aphids on my roses").
- **Trail logistics** (length, parking, dog rules) — this is a botany corpus.

### Scope consequences worth stating
- **Corpus is natives-only.** Therefore "is X native?" is trivially always-yes
  and not worth scoring; "is X invasive?" is an out-of-scope refusal because the
  plant isn't in the corpus at all. Native/invasive is **not** an in-scope
  question type.
- **Routing, not just declining.** Out-of-scope ID/health questions are pointed
  to the right tool. A refusal-with-a-handoff reads as deliberate scoping, not a
  dead end.

---

## 5. The rubric

Two tiers. **Gates** must pass or the answer fails outright, no matter how
polished — a trustworthy "I don't know" beats a confident wrong answer.
**Scores** grade quality *among* answers that clear the gates.

**Mixed scales by design:** gates are **binary (pass / fail)** — they're
genuinely two-valued (did it stay correct / grounded / answer-vs-refuse right),
and binary is the most reproducible call for an LLM judge. Quality scores are
**1–3 (fail / partial / full)** — they're real spectrums where partial credit is
meaningful. Matching the scale to the dimension's actual shape is itself a
deliberate measurement decision.

### Trust gates (fail any gate → the answer fails)

**G1 — Factual & temporal correctness** · *binary*
Facts match the corpus *and* are correct for the month/condition asked.
- **Fail:** a stated fact is wrong, OR the answer is right for some month but
  wrong for the one asked (the April-right / July-wrong failure).
- **Pass:** every fact correct and correctly time-scoped to the question.

**G2 — Grounding / attribution** · *binary*
Every claim traces to the corpus; nothing invented — *especially no fabricated
trail-specific or site-specific detail*. **Grounding requires citation:** an
uncited claim fails even if it happens to be correct, because without a
traceable source you can't distinguish faithful-to-good-data from confabulation.
- **Fail:** any claim not supported by a cited corpus entry (invented plant,
  invented bloom window, invented "at the trailhead you'll see…").
- **Pass:** all claims grounded and traceable to the right plant/source.

> **Faithful to the corpus, not true about the world.** Responsibility for
> factual accuracy lives with the **data**, not the assistant. If the corpus is
> wrong and the assistant faithfully reports it, that's a *data-quality* signal
> (out of scope for this project), not an assistant failure. (Same principle in
> any grounded assistant: faithfully reporting a wrong spec sheet is the
> assistant doing its job.)

**G3 — Calibrated uncertainty & refusal** · *binary*
Did it answer-vs-refuse correctly along the gradient **answer / hedge / redirect
/ refuse** (§6)? This is **two-sided** — both directions fail:
- **Fail (confabulation):** over-answers an out-of-scope/uncertain question
  (flat "yes it's blooming"; attempts a photo ID; invents trail detail).
- **Fail (over-refusal):** needlessly refuses an in-scope question. The quiet
  failure — an assistant that refuses everything never confabulates and is also
  useless.
- **Pass:** correct answer-vs-refuse call.

> **Refusal *texture* is deliberately NOT scored.** Whether a refusal is worded
> as a clean hedge vs. a blunt decline, and which reason it cites (data-gap /
> wrong-intent / out-of-region), is a qualitative eyeball note — not a graded
> axis. It's more important that the assistant *performs* the right call than
> that it explains it well. (The §6 gradient still guides *what* the right call
> is; we just don't grade the prose.)

### Quality scores (grade trustworthy answers) · *1–3 scale*

**S1 — Calibrated completeness**
For list-type answers, surfaces the relevant set without omission *or* padding.
Definition varies by question shape:
- **Place-as-input** (place+month, attribute): list matching plants **capped at
  5**, with a clear offer to return more. Deliberate **UX-over-exhaustiveness**
  tradeoff — five useful results beat a wall of twenty. Completeness = "returns
  the *correct* matches, correctly truncated, signals there are more," NOT
  "returns *all* matches."
- **Place-as-output** (flower→where/when): list the matching **habitats**.
- **Single-plant yes/no** (time-conditional): answer yes/no **and state the
  bloom window it's reasoning from**, so the user can sanity-check the seasonal
  logic.

| Score | Anchor |
|---|---|
| **1 — Fail** | Misses obvious blooms, OR pads with improbable / wrong-habitat / wrong-month filler to look thorough. |
| **2 — Partial** | Mostly right set; minor omission, one weak inclusion, or truncated without signaling more. |
| **3 — Full** | The right set — nothing obvious missing, nothing unlikely added; correctly capped + "more" offered; showy/likely ones sensibly ordered. |

> **Ground-truth implication:** the cap lives in the *assistant's output*, but
> the *complete count* must live in the Phase 2 expected-answer — otherwise you
> can't distinguish "correctly showed 5 of 8 and offered more" from "only knew
> about 5."

**S2 — Actionability (secondary)**
Is the answer decision-useful for a planner? *Note: this can pull against G2 —
the most helpful-sounding answer is often the one that over-claims. When they
conflict, the gate wins.*
- **1 — Fail:** technically responsive but not usable for a go/where decision.
- **2 — Partial:** useful, but the planner still has obvious follow-up work.
- **3 — Full:** directly supports the decision (likely blooms + where/when + a
  clear next step).

### Aggregation
An answer is **Acceptable** only if **G1, G2, G3 all pass**. Quality is then the
S1 + S2 total (out of 6). **Report gate-pass rate and mean quality
*separately*** — a model can be high-quality and still untrustworthy, and that
gap is the finding.

---

## 6. The uncertainty gradient (drives G3)

| Call | When | Example response shape |
|---|---|---|
| **Answer** | In scope, corpus-grounded, time well-defined | "Sticky monkeyflower and coast buckwheat are typical April blooms in coastal-bluff scrub like the headlands." |
| **Hedge** | In scope but condition-dependent (current/this-week, marginal month) | "Lupine usually peaks mid-April, so it's likely out now — but bloom timing shifts with the rains year to year; check a recent report to be sure." |
| **Redirect** | Adjacent ask we can partly serve honestly (photo ID) | "I can't ID from a photo — try Google Lens or iNaturalist. But purple flowers common in coastal scrub this month include X and Y." |
| **Refuse** | Out of scope / below our granularity / non-corpus | "I don't have trail-by-trail or garden-care data — I can only speak to which natives typically bloom in a given habitat and month." |

The senior signal is the **hedge** and **redirect** rows: a binary
answer/refuse rubric would mis-grade exactly the cases this persona generates
most. (Note: G3 scores whether the *right row was chosen*, not how elegantly the
prose reads — see the texture note in §5.)

---

## 7. Worked examples (calibration anchors for the Phase 4 judge)

**"Is the lupine out yet?" (asked mid-April)**
- *Confabulating answer:* "Yes, the lupine is blooming." → G3 fail (false live
  certainty), G1 fail. **Fails.**
- *Good answer:* hedge per §6. → G1/G2/G3 pass, S1=3, S2=3. **Best.**

**"What's blooming at Point Lobos in April?"**
- *Region-flattened:* generic regional list ignoring that Point Lobos is
  coastal. → gates pass but S1≤2. Acceptable but mediocre.
- *Habitat-grounded:* coastal-bluff + pine-forest blooms, explicitly excludes
  inland oak-woodland species, capped at 5 with "want more?" → gates pass, S1=3,
  S2=3. **Best.**
- *Trail-fabricated:* "at the mile-2 overlook you'll see…" → G2 fail. **Fails.**

**"How do I treat aphids on my roses?"** → refuse (§6). Correct refusal: G3 pass,
**Acceptable**. Any care advice attempted: G2/G3 fail. **Fails.**

---

## 8. Hand-off notes to later phases

- **Phase 1 (schema):** add a single controlled-vocabulary **`habitat`** field
  (coastal-bluff scrub · chaparral · oak woodland · riparian · grassland ·
  Monterey pine forest — finalize against Calscape's plant-community data). This
  one field is what makes J1/J2 answerable at the chosen granularity. Keep a tiny
  separate place→habitat lookup for a handful of named local spots — **and source
  each mapping** (a park's dominant community is verifiable; an unsourced
  "Point Lobos is coastal scrub" is the same confabulation we're hunting, one
  level up).

- **Granularity is a deliberate, data-gated boundary — not a gap.** Habitat is
  the *finest granularity the corpus can ground*. Finer-than-habitat (the "mile-2
  overlook") has **no source in Calscape**, so promising it would mean
  confabulating it — the exact failure this project exists to catch. Three things
  defend this boundary:
  1. *Groundability* — habitat is the floor the data supports.
  2. *A named future phase* — trail-microsite precision is a **v2 gated on a new
     data source** (trail surveys / observation data), not a vague "later."
  3. *It actually fits how hiking works* — a single trail crosses coastal bluff
     into canyon into grassland, so "watch for X in the coastal stretch, Y as you
     drop into the canyon" is *more* useful to a moving hiker than one pinned
     location. Habitat guidance is a design choice, not just a fallback.

- **Phase 2 (ground-truth categories):** must cover — place+month lists,
  time-conditional ("out yet"), flower→where/when, attribute lookups, the
  **typical-vs-current** hedge cases, trail-microsite refusals, photo-ID
  redirects, and the classic out-of-scope refusals (garden care, non-corpus
  plants). Include **near-miss pairs** (a just-barely-answerable question next to
  a just-barely-not) so the harness can catch drift toward either G3 failure.

- **Phase 4 (harness):** implement gates as pass/fail first (cheap, reliable),
  then the 1–3 quality scores. Report gate-pass rate and mean quality separately.
  The money demo: a change that nudges G2/G3 to fail while leaving S1/S2 flat —
  invisible to the eye, caught by the gates.
