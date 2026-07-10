# Phase 4 — Eval Harness Metric Spec

> **Purpose of this file.** This is the design artifact handed to Claude Code to
> implement the eval harness. It defines *what* every metric means and *how* it is
> scored for the Trailside suite. Code should implement to this spec, not invent
> metrics. Where a decision was made deliberately, the rationale is noted so the
> implementation preserves the intent.
>
> **Inputs:** `data/ground_truth.json` (52 records) and the pipeline's
> `ask(question, month=None) -> {"call_type", "answer", "sources"}` from
> `trailside/pipeline.py`.
>
> **Output:** an eval report (per-metric numbers + per-category breakdown + the
> caught-regression writeup).

---

## 0. Ground-truth fields the harness reads

Each record: `id, question, category, difficulty, eval_month, expected_call,
expected_answer, expected_source, notes`.

- `expected_call` ∈ {answer, hedge, redirect, refuse} — the 4-way gradient.
- `expected_source` — list of plant common names that *should* be retrieved/cited.
  **May be empty** (most refusals) and **may be non-empty even for refuse/redirect**
  (e.g. GT-014: lupine exists but is out of season → refuse, yet the real plant is
  named). See §1 for why this matters.
- `eval_month` — nullable; set only for temporal/underspecified cases. Pass it as
  the `month=` argument to `ask()`. When null, call with `month=None`.
- `expected_answer` — FREE-TEXT grading reference for the judge, **not** a gold
  string to match. For list answers it names the full match set + count.
- `notes` — ungraded, human context only. Do not feed to scorers.

---

## 1. Retrieval metrics — recall@k and MRR  *(mechanical, no judge)*

**Question it answers:** did the pipeline pull the right plants into context?

- Compare the pipeline's returned `sources` against `expected_source`, matching on
  plant common name (normalize case/whitespace; the ground-truth strings are the
  canonical spelling).
- **recall@k** = (# expected plants present in returned sources) / (# expected plants).
- **MRR** = 1 / (rank of the first expected plant in the returned source list).
- **k** = the pipeline's current top-6 retrieval. Report recall@6.

**CRITICAL scoping rule — only score records with a non-empty `expected_source`.**
Records where `expected_source` is empty (most refusals) have nothing to retrieve;
they are **excluded from the retrieval denominator entirely**. Do NOT score them as
recall = 0 — that would punish correct refusals and corrupt the metric. Retrieval
quality and refusal correctness are **independent axes** (see §3). A record can be
a correct refusal AND have expected sources (GT-014/026/047) — for those, retrieval
IS scored, refusal IS scored, separately.

Report retrieval numbers over the scoreable subset, and state the subset size.

---

## 2. Grounding / faithfulness  *(LLM-as-judge — the money metric)*

**Question it answers:** is every factual claim in the answer supported by the
retrieved context?

- **Verdict is binary and whole-answer:** `grounded` / `not_grounded`. One judge
  call per record. No claim-level decomposition.
- **Zero fabrication tolerance.** The judge is instructed: if the answer names even
  ONE plant, place, or bloom-month that is not supported by the retrieved context,
  the entire answer is `not_grounded`. A mostly-correct answer with one invented
  specific FAILS. This strictness is deliberate — the project models a high-trust
  (enterprise-grade) assistant where a single fabricated spec is the core danger. The
  wildflower domain doesn't require this bar; we impose it on purpose.
- **Judge inputs:** the question, the pipeline's `answer`, and the retrieved
  context (the chunks/sources the pipeline actually used — ground it against what
  the model SAW, not against the whole corpus).
- **Judge output:** `{grounded: bool, justification: str}` (one line).
- **Scope:** only score records where the model actually produced factual content
  (call_type answer/hedge). A clean refuse/redirect has no claims to ground — skip,
  or trivially mark grounded=true with justification "no factual claims." Decide one
  and apply consistently; excluding is cleaner.

**Expect to learn the judge's limits here** (per the handoff). Jacob spot-checks a
sample of grounding verdicts against his own read and records the agreement rate.

---

## 3. Refusal / call correctness  *(mechanical comparison of call buckets)*

**Question it answers:** did the model make the right call on the answer/hedge/
redirect/refuse gradient?

- **Headline metric: exact-match rate** — `call_type == expected_call`, over all 52
  records. One number. Simple, honest, defensible.
- **Underneath: full 4×4 confusion matrix** (rows = expected, cols = predicted,
  over {answer, hedge, redirect, refuse}). Nearly free once calls are compared.
- **Flag the dangerous cells.** The matrix is not symmetric in cost. Predicting a
  MORE-confident call than expected is the trust-violating direction:
  - expected `refuse` → predicted `answer` = worst case (confident confabulation).
  - expected `redirect` → predicted `answer`, expected `hedge` → predicted `answer`,
    etc. — over-confidence errors.
  Report an **over-confidence error count** (predictions more assertive than
  expected) separately from **over-caution errors** (predictions more cautious than
  expected). The gradient order for "more assertive" is: answer > hedge > redirect
  > refuse. This asymmetry is the trust story in one number.

---

## 4. Answer quality  *(LLM-as-judge — graded, gates must pass first)*

**Question it answers:** among answers that passed the gates, how good are they?

- **Scored 1–5, single combined number** folding the rubric's two quality scores
  (calibrated completeness — no omission AND no padding — and actionability) into
  one. Combined at this corpus size because per-dimension slices are statistically
  thin over ~22 answer-type records; would split as volume grows.
- **Only score records that pass the gates** (grounded, and correct call). Quality
  is a graded layer ON TOP of the pass/fail gates — a fabricated answer does not get
  a quality score, it already failed §2. State the gate-pass filter explicitly in
  the report.
- **Judge inputs:** question, pipeline `answer`, and `expected_answer` as the
  grading reference (use its named match-set + count to judge completeness — e.g.
  "named 5 of 7 valid, offered more" scores well; "named 3, stopped" is incomplete;
  "named all 7 + 3 sentences of filler" is penalized for padding).
- **Judge output:** `{score: 1-5, justification: str}` (one line — this is the
  diagnostic thread that recovers the completeness-vs-actionability split we folded
  away, and the thing Jacob spot-checks).

---

## 5. Reporting — gate-pass rate vs mean quality, reported SEPARATELY

Per the Phase 0 rubric: the three trust gates (temporal/factual correctness,
grounding, calibrated refusal) are pass/fail; the two quality scores are graded.
**Report gate-pass rate and mean quality as separate headline numbers — the gap
between them is the finding.** A high quality score over a low gate-pass rate means
"fluent but untrustworthy," which is exactly the failure mode the project surfaces.

Also report **per-category** breakdowns (the 10 categories do double duty as
eval-time scoring buckets) — especially `hero_stacked`, `out_of_scope`, and the
`temporal_hedge` reproducibility pair (GT-013/014).

---

## 6. Regression run  *(mechanical — re-run and diff)*

- Persist each full run's per-record results (call_type, grounded, quality, retrieval)
  to a timestamped file.
- A regression run = re-run the whole suite, diff per-record against a saved baseline,
  and surface every record whose call_type, grounded verdict, or quality bucket changed.

### ⭐ The money demonstration (capture this explicitly)
Introduce a change that *looks fine by eye* — e.g. swap the system prompt for a
slightly more "helpful" phrasing, or alter chunking — and show the harness catches a
**grounding or refusal regression** it would otherwise miss. Log the before/after:
the changed prompt, the specific record(s) that flipped (ideally a `refuse`→`answer`
or `grounded`→`not_grounded` flip on the hero cases), and the metric delta. This
single logged before/after is the artifact that retires the "no eval rigor" gap.

---

## 7. Judge implementation notes

- Use the same Gemini free-tier model as the pipeline for the judge, OR note if using
  a different one (a stronger judge than the generator is defensible; record the choice).
- `temperature=0`, structured JSON output for every judge call.
- Grounding and quality are **separate judge calls** with separate prompts — do not
  ask one call to do both; it muddies both verdicts.
- Respect the 15 RPM free-tier limit; add a small sleep if 429s appear.
- **Save every judge justification** — they are the spot-check trail and the
  diagnostic record, not disposable.
