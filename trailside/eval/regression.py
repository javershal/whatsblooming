"""§6 -- regression run. Diff a scored run against a saved baseline scored run,
surfacing every record whose call_type, grounded verdict, or quality score
changed.
"""
from __future__ import annotations

TRACKED_FIELDS = ("call_type", "grounded", "quality_score")


def diff_runs(baseline: list[dict], new: list[dict]) -> list[dict]:
    baseline_by_id = {r["id"]: r for r in baseline}
    changes = []
    for r in new:
        b = baseline_by_id.get(r["id"])
        if b is None:
            continue
        changed_fields = {
            field: {"baseline": b[field], "new": r[field]}
            for field in TRACKED_FIELDS
            if b[field] != r[field]
        }
        if changed_fields:
            changes.append({
                "id": r["id"],
                "question": r["question"],
                "category": r["category"],
                "changed": changed_fields,
            })
    return changes


def format_diff(changes: list[dict]) -> str:
    if not changes:
        return "No regressions: call_type, grounded, and quality_score are unchanged for all matched records."
    lines = [f"=== Regression diff: {len(changes)} record(s) changed ===\n"]
    for c in changes:
        lines.append(f"{c['id']} [{c['category']}] \"{c['question']}\"")
        for field, delta in c["changed"].items():
            lines.append(f"    {field}: {delta['baseline']!r} -> {delta['new']!r}")
    return "\n".join(lines)
