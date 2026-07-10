"""Loads and validates data/ground_truth.json (§0)."""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).parent.parent.parent
GROUND_TRUTH_FILE = ROOT / "data" / "ground_truth.json"

REQUIRED_FIELDS = (
    "id", "question", "category", "difficulty", "eval_month",
    "expected_call", "expected_answer", "expected_source", "notes",
)
VALID_CALLS = {"answer", "hedge", "redirect", "refuse"}


def load_ground_truth(path: pathlib.Path = GROUND_TRUTH_FILE) -> list[dict]:
    records = json.loads(path.read_text())
    for r in records:
        missing = [f for f in REQUIRED_FIELDS if f not in r]
        if missing:
            raise ValueError(f"{r.get('id', '?')} missing fields: {missing}")
        if r["expected_call"] not in VALID_CALLS:
            raise ValueError(f"{r['id']} has invalid expected_call: {r['expected_call']!r}")
    return records
