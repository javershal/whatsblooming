# CLAUDE.md

This repo holds **two independent projects** that happen to share a directory and
some plant data. Know which one you're touching before you start.

1. **What's Blooming** — a static website + data pipeline showing which California
   native plants are blooming near Monterey, CA. Public-facing, deployed.
2. **Trailside** — an eval harness (and a small RAG chatbot it grades) built to
   demonstrate formal evaluation methodology for an LLM assistant. The **eval
   harness and methodology are the deliverable; the chatbot exists only to be
   evaluated.** Lives entirely under `trailside/`.

They are not integrated. Changes to one should not touch the other.

---

## Project 1 — What's Blooming (the website)

**What it is:** Static site (no server, no database, no build step) hosted on
**GitHub Pages, live at https://javershal.github.io/whatsblooming/**, served from
`main` branch root. A month slider lets the user see which plants bloom in each month.

### Layout
```
index.html              # Entry point + month slider UI
css/style.css           # Responsive card grid; green accent #3d7a4f; no media queries
js/app.js               # Fetches data/plants.json, filters by selected month, renders cards
data/plants.json        # Committed plant data — source of truth for the frontend
scripts/collect_data.py # Data pipeline that regenerates plants.json
.github/workflows/refresh-data.yml  # Quarterly cron + manual dispatch
```

### `data/plants.json`
Committed to the repo so the site runs with zero infrastructure. One record per
plant, sorted alphabetically by `common_name` (for stable diffs). Fields:
`common_name`, `scientific_name`, `family`, `growth_habit`, `native`,
`bloom_months` (1-indexed ints), `calflora_url`, `calscape_url`, `photo_url`
(may be `null`), `photo_attribution`. Photos come from Calflora (attribution
preserved). `app.js` ignores any extra fields.

### Data pipeline — `scripts/collect_data.py`
Pulls the native plant list for a Calflora saved polygon (default shape id
**`rs3899`**, covering Monterey) via Calflora's "What Grows Here" **GWT-RPC**
endpoint (`POST /app/userdata`) — *not* the documented api.calflora.org API,
which is a dead end. One HTTP request, **no API key required**. Records are
deduped by common name (subspecies/varieties share names) with bloom months
unioned.

```bash
python scripts/collect_data.py --existing data/plants.json --output data/plants.json
# fallback if the live endpoint breaks: --tsv path/to/calflora_export.tsv
```

If the endpoint starts returning errors instead of `//OK[...]`, Calflora
redeployed their GWT build — re-capture the request from DevTools and update the
`WGH_*` constants / `WGH_PAYLOAD_TEMPLATE` in the script. The GWT-RPC decoding
details are documented in the script and in project memory (`project-calflora-api`).

### Running locally
Must be served over HTTP for the `fetch` to work:
```bash
python -m http.server 8000   # then open http://localhost:8000
```

### Deployment
`.github/workflows/refresh-data.yml` runs the pipeline quarterly (Jan/Apr/Jul/Oct)
and on manual dispatch, committing any `plants.json` changes. No secrets required.
The site itself deploys automatically from `main` via GitHub Pages.

---

## Project 2 — Trailside (the eval project)

An eval-methodology project: a small retrieval-augmented plant assistant plus a
full harness that grades its answers against a hand-authored ground-truth set.
The assistant answers two jobs — "place + time → what will I see?" and "flower →
where/when do I go?" — scoped to **habitat/plant-community granularity** (it
refuses below that). Everything lives under `trailside/` and `data/`.

### Key concept: gates vs. scores
The rubric (`trailside/rubric.md`) grades each answer on **3 trust gates**
(factual/temporal correctness, grounding, calibrated refusal) and **2 quality
scores** (completeness, actionability). A failed gate fails the answer outright;
gate-pass rate and mean quality are reported **separately**. The headline finding
the harness is designed to surface is the "fluent but untrustworthy" gap.

### Layout
```
trailside/
├── rubric.md              # Phase 0 — the grading rubric (gates + scores)
├── schema_decision.md     # Phase 1 — corpus schema rationale
├── pipeline.py            # Phase 3 — the RAG pipeline; public API is ask(question, month=None)
├── embeddings_cache.json  # Cached Gemini embeddings for the corpus
├── smoke_test.py
└── eval/                  # Phase 4 — the eval harness
    ├── cli.py             # run / score / report / full-run / regress / html subcommands
    ├── runner.py          # calls ask() over the ground-truth set, saves timestamped raw runs
    ├── judge.py           # shared Gemini LLM-judge plumbing (with 429/503 backoff retry)
    ├── score.py           # orchestrates scoring; gate_pass = call_correct AND grounded is not False
    ├── scoring/           # retrieval / call_correctness / grounding / quality scorers
    ├── report.py          # gate-pass rate + mean quality + per-category breakdown
    ├── regression.py      # diff two scored runs
    ├── html_report.py     # render a scored run to a self-contained HTML file
    └── runs/              # raw_*.json / scored_*.json / .html outputs (gitignored)

data/
├── trailside_plants.json  # 29 Monterey natives spanning 7 habitats (corpus)
├── places.json            # 3 sourced places (Garland Ranch, Asilomar, Point Lobos)
├── ground_truth.json      # 52 hand-authored eval records (canonical)
└── Ground truth final data.csv  # human editing view of the same set
```

Root-level docs: `eval_metric_spec.md` (metric definitions), `feedback_design.md`
(Phase 5 feedback-loop design), and `Eval project handoff.md` (the full plan and
phase-by-phase decision log — the authoritative history).

### Running the pipeline and eval
This is a `uv` project (Python ≥3.12; deps `google-genai`, `numpy`). Both the
live `ask()` calls and the judge calls go through **Gemini** (free tier).

```bash
uv run python -m trailside.eval.cli full-run          # run + score + report + HTML
uv run python -m trailside.eval.cli run --limit 5     # smoke test a few records
uv run python -m trailside.eval.cli regress <baseline.json> <new.json>
```

- The Gemini API key lives in **`geminikey.txt`** (gitignored — never commit it).
- Generation/judge model is **`gemini-3.1-flash-lite`**. Watch daily quota caps:
  a full 52-record run makes ~150+ calls (generation + 2 judges).
- `ask()` returns `retrieved_context` (the top-K chunks actually fed to the model)
  so the grounding judge checks against what the model *saw*, not the whole corpus.

### Status
Phases 0–5 complete. A baseline run and a captured regression demo live in
`trailside/eval/runs/`. The remaining optional stretch is **Phase 6** — a small
demo widget. See `Eval project handoff.md` for the current pickup point.

---

## Conventions

- **No secrets in git.** `geminikey.txt` and `trailside/eval/runs/` are gitignored;
  keep it that way.
- **Commit/push only when asked.** `main` is the deployed branch for the website.
- Keep the two projects separate — don't let eval code depend on the website or
  vice versa.
- Website frontend stays framework-free and build-step-free (plain HTML/CSS/JS).
