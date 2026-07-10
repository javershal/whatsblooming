"""CLI entrypoint for the Phase 4 eval harness.

    uv run python -m trailside.eval.cli run                       # ask() over all 52 GT records -> raw run
    uv run python -m trailside.eval.cli score <raw_run.json>       # mechanical + judge scorers -> scored run
    uv run python -m trailside.eval.cli report <scored_run.json>   # print the eval report
    uv run python -m trailside.eval.cli full-run                   # run + score + report in one go
    uv run python -m trailside.eval.cli regress <baseline.json> <new.json>
    uv run python -m trailside.eval.cli html <scored_run.json>      # render a scored run to a browsable HTML file
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from trailside.eval import regression, report, score  # noqa: E402
from trailside.eval.ground_truth import load_ground_truth  # noqa: E402
from trailside.eval.html_report import write_html_report  # noqa: E402
from trailside.eval.runner import load_raw_run, run_all, save_raw_run  # noqa: E402
from trailside.pipeline import GeminiProvider  # noqa: E402


def _progress(i, total, raw):
    print(f"[{i}/{total}] {raw['id']}: expected={raw['expected_call']} got={raw['call_type']}", file=sys.stderr)


def cmd_run(args):
    records = load_ground_truth()
    if args.limit:
        records = records[: args.limit]
    results = run_all(records, on_record=_progress)
    path = save_raw_run(results)
    print(f"Raw run saved to {path}")


def cmd_score(args):
    raw = load_raw_run(pathlib.Path(args.raw_run))
    provider = GeminiProvider()
    scored = score.score_all(raw, provider=provider)
    path = score.save_scored_run(scored)
    print(f"Scored run saved to {path}")


def cmd_report(args):
    scored = score.load_scored_run(pathlib.Path(args.scored_run))
    rep = report.build_report(scored)
    print(report.format_report(rep))


def cmd_full_run(args):
    records = load_ground_truth()
    if args.limit:
        records = records[: args.limit]
    provider = GeminiProvider()
    raw = run_all(records, provider=provider, on_record=_progress)
    save_raw_run(raw)
    scored = score.score_all(raw, provider=provider)
    scored_path = score.save_scored_run(scored)
    print(f"Scored run saved to {scored_path}")
    html_path = write_html_report(scored, scored_path.with_suffix(".html"), run_label=scored_path.name)
    print(f"HTML report saved to {html_path}")
    rep = report.build_report(scored)
    print(report.format_report(rep))


def cmd_html(args):
    scored_path = pathlib.Path(args.scored_run)
    scored = score.load_scored_run(scored_path)
    out_path = pathlib.Path(args.output) if args.output else scored_path.with_suffix(".html")
    write_html_report(scored, out_path, run_label=scored_path.name)
    print(f"HTML report saved to {out_path}")


def cmd_regress(args):
    baseline = score.load_scored_run(pathlib.Path(args.baseline))
    new = score.load_scored_run(pathlib.Path(args.new))
    changes = regression.diff_runs(baseline, new)
    print(regression.format_diff(changes))


def main():
    parser = argparse.ArgumentParser(description="Trailside Phase 4 eval harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run ask() over all ground-truth records; save raw run.")
    p_run.add_argument("--limit", type=int, default=None, help="Only run the first N records (for smoke-testing).")
    p_run.set_defaults(func=cmd_run)

    p_score = sub.add_parser("score", help="Score a raw run (mechanical + LLM judges).")
    p_score.add_argument("raw_run", help="Path to a raw_*.json run file.")
    p_score.set_defaults(func=cmd_score)

    p_report = sub.add_parser("report", help="Print the eval report for a scored run.")
    p_report.add_argument("scored_run", help="Path to a scored_*.json run file.")
    p_report.set_defaults(func=cmd_report)

    p_full = sub.add_parser("full-run", help="Run + score + report in one pass.")
    p_full.add_argument("--limit", type=int, default=None, help="Only run the first N records (for smoke-testing).")
    p_full.set_defaults(func=cmd_full_run)

    p_regress = sub.add_parser("regress", help="Diff a new scored run against a baseline.")
    p_regress.add_argument("baseline", help="Path to the baseline scored_*.json.")
    p_regress.add_argument("new", help="Path to the new scored_*.json.")
    p_regress.set_defaults(func=cmd_regress)

    p_html = sub.add_parser("html", help="Render a scored run to a single browsable HTML file.")
    p_html.add_argument("scored_run", help="Path to a scored_*.json run file.")
    p_html.add_argument("-o", "--output", default=None, help="Output path (default: same name, .html extension).")
    p_html.set_defaults(func=cmd_html)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
