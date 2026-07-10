"""Stage 1 — run the pipeline over the ground-truth set (§0, build order step 1).

Calls ask() for every ground-truth record, passing eval_month as month=, and
persists the raw per-record results to a timestamped file. Scoring is a
separate stage (see score.py) so a run's raw output can be re-scored without
re-hitting the API.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from trailside.eval.judge import call_with_retry  # noqa: E402
from trailside.pipeline import GeminiProvider, LLMProvider, ask  # noqa: E402

RUNS_DIR = pathlib.Path(__file__).parent / "runs"

# Free-tier Gemini is capped at 15 RPM; ask() makes 2 calls (embed + generate)
# per record, so space calls out to stay well under the limit.
DEFAULT_SLEEP_SECONDS = 4.5


def run_all(
    records: list[dict],
    provider: LLMProvider | None = None,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    on_record: callable | None = None,
) -> list[dict]:
    """Call ask() for every ground-truth record; return raw per-record results.

    Reuses a single provider instance across all calls so the pipeline's
    embedding cache (keyed on corpus chunk ids, not per-query) is built once.
    """
    provider = provider or GeminiProvider()
    results = []
    for i, r in enumerate(records):
        result = call_with_retry(ask, r["question"], month=r["eval_month"], provider=provider)
        raw = {
            "id": r["id"],
            "question": r["question"],
            "category": r["category"],
            "difficulty": r["difficulty"],
            "eval_month": r["eval_month"],
            "expected_call": r["expected_call"],
            "expected_answer": r["expected_answer"],
            "expected_source": r["expected_source"],
            "call_type": result["call_type"],
            "answer": result["answer"],
            "sources": result["sources"],
            "retrieved_context": result.get("retrieved_context", []),
        }
        results.append(raw)
        if on_record:
            on_record(i + 1, len(records), raw)
        if i < len(records) - 1:
            time.sleep(sleep_seconds)
    return results


def save_raw_run(results: list[dict], path: pathlib.Path | None = None) -> pathlib.Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = RUNS_DIR / f"raw_{stamp}.json"
    path.write_text(json.dumps(results, indent=2))
    return path


def load_raw_run(path: pathlib.Path) -> list[dict]:
    return json.loads(pathlib.Path(path).read_text())
