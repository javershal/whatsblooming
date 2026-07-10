"""§5 -- reporting. Gate-pass rate and mean quality as separate headlines,
plus per-category breakdown (the 10 categories double as scoring buckets),
with hero_stacked / out_of_scope / the temporal_hedge GT-013-014 pair called
out explicitly per the spec.
"""
from __future__ import annotations

from trailside.eval.scoring import call_correctness, grounding, quality, retrieval

HIGHLIGHT_CATEGORIES = ("hero_stacked", "out_of_scope")
REPRODUCIBILITY_PAIR = ("GT-013", "GT-014")


def _category_breakdown(records: list[dict]) -> dict:
    per_category = {}
    for cat in sorted({r["category"] for r in records}):
        cat_records = [r for r in records if r["category"] == cat]
        per_category[cat] = {
            "n": len(cat_records),
            "exact_match_rate": call_correctness.exact_match_rate(cat_records),
            "gate_pass_rate": sum(1 for r in cat_records if r["gate_pass"]) / len(cat_records),
            "retrieval": retrieval.aggregate([r["retrieval"] for r in cat_records]),
            "grounding": grounding.aggregate(
                [{"grounded": r["grounded"]} if r["grounded"] is not None else None for r in cat_records]
            ),
            "quality": quality.aggregate(
                [{"score": r["quality_score"]} if r["quality_score"] is not None else None for r in cat_records]
            ),
        }
    return per_category


def build_report(scored: list[dict]) -> dict:
    n = len(scored)
    retrieval_scores = [r["retrieval"] for r in scored]
    grounding_scores = [{"grounded": r["grounded"]} if r["grounded"] is not None else None for r in scored]
    quality_scores = [{"score": r["quality_score"]} if r["quality_score"] is not None else None for r in scored]

    return {
        "n_records": n,
        "call_correctness": {
            "exact_match_rate": call_correctness.exact_match_rate(scored),
            "confusion_matrix": call_correctness.confusion_matrix(scored),
            **call_correctness.error_breakdown(scored),
        },
        "retrieval": retrieval.aggregate(retrieval_scores),
        "grounding": grounding.aggregate(grounding_scores),
        "gate_pass_rate": sum(1 for r in scored if r["gate_pass"]) / n,
        "quality": quality.aggregate(quality_scores),
        "per_category": _category_breakdown(scored),
        "reproducibility_pair": [
            {
                "id": r["id"], "question": r["question"], "category": r["category"],
                "expected_call": r["expected_call"], "call_type": r["call_type"],
                "grounded": r["grounded"], "gate_pass": r["gate_pass"],
                "quality_score": r["quality_score"],
            }
            for r in scored if r["id"] in REPRODUCIBILITY_PAIR
        ],
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def _fmt(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def format_report(report: dict) -> str:
    lines = []
    lines.append(f"=== Trailside Eval Report ({report['n_records']} records) ===\n")

    lines.append("--- Headlines (§5: reported separately, the gap is the finding) ---")
    lines.append(f"Gate-pass rate : {_pct(report['gate_pass_rate'])}")
    q = report["quality"]
    lines.append(
        f"Mean quality   : {_fmt(q['mean_quality'])} / 5"
        f"  (n={q['n_scoreable']}, gate-passing answer/hedge records only)\n"
    )

    cc = report["call_correctness"]
    lines.append("--- §3 Call correctness ---")
    lines.append(f"Exact-match rate: {_pct(cc['exact_match_rate'])}")
    lines.append(
        f"Over-confidence errors: {cc['over_confidence_count']} {cc['over_confidence_ids']}"
    )
    lines.append(
        f"Over-caution errors   : {cc['over_caution_count']} {cc['over_caution_ids']}"
    )
    lines.append("Confusion matrix (rows=expected, cols=predicted):")
    types = call_correctness.CALL_TYPES
    header = "expected\\predicted".ljust(20) + "".join(t.ljust(10) for t in types)
    lines.append(header)
    for e in types:
        row = e.ljust(20) + "".join(str(cc["confusion_matrix"][e][p]).ljust(10) for p in types)
        lines.append(row)
    lines.append("")

    r = report["retrieval"]
    lines.append("--- §1 Retrieval (only records with non-empty expected_source) ---")
    lines.append(f"n_scoreable: {r['n_scoreable']}")
    lines.append(f"recall@6   : {_pct(r['recall_at_6'])}")
    lines.append(f"MRR        : {_fmt(r['mrr'])}\n")

    g = report["grounding"]
    lines.append("--- §2 Grounding (only records with call_type in {answer, hedge}) ---")
    lines.append(f"n_scoreable   : {g['n_scoreable']}")
    lines.append(f"grounded_rate : {_pct(g['grounded_rate'])}\n")

    lines.append("--- Per-category breakdown ---")
    for cat, stats in report["per_category"].items():
        marker = " *" if cat in ("hero_stacked", "out_of_scope") else ""
        lines.append(
            f"{cat}{marker} (n={stats['n']}): exact_match={_pct(stats['exact_match_rate'])} "
            f"gate_pass={_pct(stats['gate_pass_rate'])} "
            f"recall@6={_pct(stats['retrieval']['recall_at_6'])} "
            f"grounded={_pct(stats['grounding']['grounded_rate'])} "
            f"mean_quality={_fmt(stats['quality']['mean_quality'])}"
        )
    lines.append("(* = highlighted per §5)\n")

    lines.append("--- Temporal-hedge reproducibility pair (GT-013 / GT-014) ---")
    for rec in report["reproducibility_pair"]:
        lines.append(
            f"{rec['id']}: \"{rec['question']}\" "
            f"expected={rec['expected_call']} got={rec['call_type']} "
            f"grounded={rec['grounded']} gate_pass={rec['gate_pass']} "
            f"quality={rec['quality_score']}"
        )

    return "\n".join(lines)
