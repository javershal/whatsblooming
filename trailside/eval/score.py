"""Stage 2+3 -- run all four scorers over a raw run, producing scored records.

gate_pass (feeds §5's headline gate-pass rate) reconciles the spec's two
implemented judges with the rubric's three trust gates:
  - call correctness (§3) stands in for G3 (calibrated answer/hedge/redirect/
    refuse call).
  - grounding (§2) stands in for G1+G2 (facts correct and traceable) -- the
    zero-fabrication grounding check already fails on wrong bloom-months/
    plants, which is what G1 would catch separately.
  - grounded=None (redirect/refuse, no factual content -- §2's scope note)
    passes vacuously: a correct refusal has no claims to be ungrounded.

    gate_pass = (call_type == expected_call) AND (grounded is not False)
"""
from __future__ import annotations

import datetime
import json
import pathlib

from trailside.eval.scoring import call_correctness, grounding, quality, retrieval
from trailside.pipeline import GeminiProvider, LLMProvider

RUNS_DIR = pathlib.Path(__file__).parent / "runs"


def score_all(raw_records: list[dict], provider: LLMProvider | None = None) -> list[dict]:
    provider = provider or GeminiProvider()

    scored = [dict(r) for r in raw_records]

    # Mechanical: retrieval (§1) and call correctness (§3).
    for r in scored:
        r["retrieval"] = retrieval.score_record(r["expected_source"], r["sources"])
        r["call_correct"] = r["call_type"] == r["expected_call"]
        r["call_verdict"] = call_correctness.classify(r["expected_call"], r["call_type"])

    # LLM judge: grounding (§2) -- must run before gate_pass can be computed.
    grounding_results = grounding.score_all(provider, scored)
    for r, g in zip(scored, grounding_results):
        r["grounded"] = g["grounded"] if g is not None else None
        r["grounding_justification"] = g["justification"] if g is not None else None

    # Gate pass (§5) -- needed before quality (§4) is scoreable.
    for r in scored:
        r["gate_pass"] = r["call_correct"] and r["grounded"] is not False

    # LLM judge: quality (§4), gated on gate_pass.
    quality_results = quality.score_all(provider, scored)
    for r, q in zip(scored, quality_results):
        r["quality_score"] = q["score"] if q is not None else None
        r["quality_justification"] = q["justification"] if q is not None else None

    return scored


def save_scored_run(scored: list[dict], path: pathlib.Path | None = None) -> pathlib.Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = RUNS_DIR / f"scored_{stamp}.json"
    path.write_text(json.dumps(scored, indent=2))
    return path


def load_scored_run(path: pathlib.Path) -> list[dict]:
    return json.loads(pathlib.Path(path).read_text())
