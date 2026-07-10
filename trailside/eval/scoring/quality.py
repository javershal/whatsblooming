"""§4 -- answer quality. LLM-as-judge, 1-5, gated on passing the trust gates.

Only scores records that (a) passed the gates -- correct call_type AND
grounded (§5's gate_pass, computed upstream in score.py) -- and (b) actually
produced factual content (call_type answer/hedge; a passing refuse/redirect
has no list/claim to grade for completeness or actionability).
"""
from __future__ import annotations

import time

from trailside.eval.judge import RATE_LIMIT_SLEEP_SECONDS, judge_quality
from trailside.pipeline import LLMProvider

GRADEABLE_CALL_TYPES = {"answer", "hedge"}


def is_scoreable(record: dict) -> bool:
    return record["gate_pass"] and record["call_type"] in GRADEABLE_CALL_TYPES


def score_record(provider: LLMProvider, record: dict) -> dict | None:
    """Returns {"score": 1-5, "justification": str}, or None if not gate-eligible."""
    if not is_scoreable(record):
        return None
    return judge_quality(
        provider,
        question=record["question"],
        answer=record["answer"],
        expected_answer=record["expected_answer"],
    )


def score_all(provider: LLMProvider, records: list[dict],
              sleep_seconds: float = RATE_LIMIT_SLEEP_SECONDS) -> list[dict | None]:
    """records must already have gate_pass set (see score.py)."""
    results = []
    for i, r in enumerate(records):
        results.append(score_record(provider, r))
        if i < len(records) - 1:
            time.sleep(sleep_seconds)
    return results


def aggregate(quality_scores: list[dict | None]) -> dict:
    scoreable = [q for q in quality_scores if q is not None]
    n = len(scoreable)
    if n == 0:
        return {"n_scoreable": 0, "mean_quality": None}
    return {
        "n_scoreable": n,
        "mean_quality": sum(q["score"] for q in scoreable) / n,
    }
