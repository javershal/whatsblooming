"""§2 -- grounding / faithfulness. LLM-as-judge, binary, whole-answer.

Scope (§2): only score records where the model actually produced factual
content, i.e. the pipeline's *actual* call_type is answer/hedge. A clean
refuse/redirect has no claims to ground. Per the spec's either/or, this
implementation EXCLUDES those records from grounding entirely (grounded=None)
rather than trivially marking them grounded=true -- "excluding is cleaner."
"""
from __future__ import annotations

import time

from trailside.eval.judge import RATE_LIMIT_SLEEP_SECONDS, judge_grounding
from trailside.pipeline import LLMProvider

GROUNDABLE_CALL_TYPES = {"answer", "hedge"}


def is_scoreable(record: dict) -> bool:
    return record["call_type"] in GROUNDABLE_CALL_TYPES


def score_record(provider: LLMProvider, record: dict) -> dict | None:
    """Returns {"grounded": bool, "justification": str}, or None if the
    record's call_type has no factual content to ground."""
    if not is_scoreable(record):
        return None
    return judge_grounding(
        provider,
        question=record["question"],
        answer=record["answer"],
        retrieved_context=record["retrieved_context"],
    )


def score_all(provider: LLMProvider, records: list[dict],
               sleep_seconds: float = RATE_LIMIT_SLEEP_SECONDS) -> list[dict | None]:
    results = []
    for i, r in enumerate(records):
        results.append(score_record(provider, r))
        if i < len(records) - 1:
            time.sleep(sleep_seconds)
    return results


def aggregate(grounding_scores: list[dict | None]) -> dict:
    scoreable = [g for g in grounding_scores if g is not None]
    n = len(scoreable)
    if n == 0:
        return {"n_scoreable": 0, "grounded_rate": None}
    n_grounded = sum(1 for g in scoreable if g["grounded"])
    return {"n_scoreable": n, "n_grounded": n_grounded, "grounded_rate": n_grounded / n}
