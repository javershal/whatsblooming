"""§1 — retrieval metrics: recall@6 and MRR. Mechanical, no judge.

CRITICAL scoping rule (§1): only records with a non-empty expected_source are
scoreable. Records where expected_source is empty (most refusals) have nothing
to retrieve and are excluded from the denominator entirely -- NOT scored as
recall=0. Retrieval quality and refusal correctness are independent axes; a
record can be a correct refusal AND have expected sources (GT-014/026/047),
in which case retrieval IS scored here, separately from the refusal call in
call_correctness.py.
"""
from __future__ import annotations


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def score_record(expected_source: list[str], sources: list[str]) -> dict | None:
    """Score one record's retrieval. Returns None if the record is out of scope
    for retrieval (empty expected_source)."""
    if not expected_source:
        return None

    expected_norm = [_normalize(s) for s in expected_source]
    sources_norm = [_normalize(s) for s in sources]
    expected_set = set(expected_norm)

    n_hit = sum(1 for e in expected_set if e in sources_norm)
    recall = n_hit / len(expected_set)

    reciprocal_rank = 0.0
    for rank, s in enumerate(sources_norm, start=1):
        if s in expected_set:
            reciprocal_rank = 1.0 / rank
            break

    return {
        "n_expected": len(expected_set),
        "n_hit": n_hit,
        "recall": recall,
        "reciprocal_rank": reciprocal_rank,
    }


def aggregate(retrieval_scores: list[dict | None]) -> dict:
    """retrieval_scores: one entry per record (None where not scoreable)."""
    scoreable = [s for s in retrieval_scores if s is not None]
    n = len(scoreable)
    if n == 0:
        return {"n_scoreable": 0, "recall_at_6": None, "mrr": None}
    return {
        "n_scoreable": n,
        "recall_at_6": sum(s["recall"] for s in scoreable) / n,
        "mrr": sum(s["reciprocal_rank"] for s in scoreable) / n,
    }
