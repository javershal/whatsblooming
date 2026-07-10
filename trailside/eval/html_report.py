"""Renders a scored run as a single self-contained HTML file for human review.

    uv run python -m trailside.eval.cli html <scored_run.json> [-o out.html]

No external dependencies (inline CSS, no JS framework) -- one file, open it
directly in a browser. Complements report.py's plain-text report: this is for
eyeballing individual records (answers, judge justifications, retrieved
context), not just the aggregate numbers.
"""
from __future__ import annotations

import html as html_lib
import pathlib

from trailside.eval.report import build_report
from trailside.eval.scoring.call_correctness import CALL_TYPES

HIGHLIGHT_CATEGORIES = {"hero_stacked", "out_of_scope"}
REPRODUCIBILITY_PAIR = {"GT-013", "GT-014"}

CSS = """
:root {
  --pass: #1a7f37; --fail: #cf222e; --warn: #9a6700; --muted: #6e7781;
  --bg: #ffffff; --bg-alt: #f6f8fa; --border: #d0d7de;
}
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; margin: 2rem; color: #1f2328; background: var(--bg); }
h1 { margin-bottom: 0.2rem; }
h2 { margin-top: 2.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }
.subtitle { color: var(--muted); margin-top: 0; }
.headline-row { display: flex; gap: 1.5rem; margin: 1.5rem 0; flex-wrap: wrap; }
.headline-card { border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.5rem; background: var(--bg-alt); min-width: 200px; }
.headline-card .big { font-size: 2rem; font-weight: 700; }
.headline-card .label { color: var(--muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.03em; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.9rem; }
th, td { border: 1px solid var(--border); padding: 0.4rem 0.6rem; text-align: left; vertical-align: top; }
th { background: var(--bg-alt); position: sticky; top: 0; }
tr:nth-child(even) { background: var(--bg-alt); }
.pill { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; color: white; }
.pill-pass { background: var(--pass); }
.pill-fail { background: var(--fail); }
.pill-na { background: var(--muted); }
.verdict-correct { color: var(--pass); font-weight: 600; }
.verdict-over_confidence { color: var(--fail); font-weight: 600; }
.verdict-over_caution { color: var(--warn); font-weight: 600; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; }
details > summary { cursor: pointer; color: #0969da; }
.q-cell { max-width: 320px; }
.small { color: var(--muted); font-size: 0.8rem; }
.highlight-row { outline: 2px solid #8250df; outline-offset: -2px; }
.section-note { color: var(--muted); font-size: 0.9rem; margin-top: -0.5rem; }
"""


def _esc(x) -> str:
    return html_lib.escape("" if x is None else str(x))


def _pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _pill(ok) -> str:
    if ok is None:
        return '<span class="pill pill-na">N/A</span>'
    return '<span class="pill pill-pass">PASS</span>' if ok else '<span class="pill pill-fail">FAIL</span>'


def _grounded_cell(grounded, justification) -> str:
    if grounded is None:
        return '<span class="small">n/a (no factual content)</span>'
    label = '<span class="pill pill-pass">grounded</span>' if grounded else '<span class="pill pill-fail">not grounded</span>'
    just = f'<div class="small">{_esc(justification)}</div>' if justification else ""
    return label + just


def _quality_cell(score, justification) -> str:
    if score is None:
        return '<span class="small">not scored (gate failed or no factual content)</span>'
    just = f'<div class="small">{_esc(justification)}</div>' if justification else ""
    return f"<b>{score}</b> / 5{just}"


def _record_row(r: dict) -> str:
    verdict = r["call_verdict"]
    call_cell = (
        f'{_esc(r["expected_call"])} &rarr; {_esc(r["call_type"])}<br>'
        f'<span class="verdict-{verdict}">{verdict.replace("_", " ")}</span>'
    )

    retrieval = r.get("retrieval")
    if retrieval is None:
        retrieval_cell = '<span class="small">n/a (empty expected_source)</span>'
    else:
        retrieval_cell = (
            f'recall={_pct(retrieval["recall"])} '
            f'({retrieval["n_hit"]}/{retrieval["n_expected"]}), RR={_fmt(retrieval["reciprocal_rank"])}'
        )

    sources = ", ".join(_esc(s) for s in r["sources"]) or '<span class="small">none</span>'
    expected_source = ", ".join(_esc(s) for s in r["expected_source"]) or '<span class="small">none</span>'

    details = (
        "<details><summary>answer + context</summary>"
        f'<p><b>Answer:</b> {_esc(r["answer"]) or "<i>(empty)</i>"}</p>'
        f'<p><b>Expected answer (grading reference):</b> {_esc(r["expected_answer"])}</p>'
        f'<p><b>Sources returned:</b> {sources}</p>'
        f'<p><b>Expected sources:</b> {expected_source}</p>'
        f'<p class="small"><b>Retrieved context ids:</b> '
        f'{_esc(", ".join(c["id"] for c in r.get("retrieved_context", [])))}</p>'
        "</details>"
    )

    row_class = "highlight-row" if r["id"] in REPRODUCIBILITY_PAIR else ""

    return f"""
<tr class="{row_class}">
  <td class="mono">{_esc(r['id'])}</td>
  <td class="q-cell">{_esc(r['question'])}</td>
  <td>{_esc(r['category'])}</td>
  <td>{call_cell}</td>
  <td>{retrieval_cell}</td>
  <td>{_grounded_cell(r['grounded'], r['grounding_justification'])}</td>
  <td>{_pill(r['gate_pass'])}</td>
  <td>{_quality_cell(r['quality_score'], r['quality_justification'])}</td>
  <td>{details}</td>
</tr>"""


def _confusion_table(matrix: dict) -> str:
    header = "<tr><th>expected \\ predicted</th>" + "".join(f"<th>{t}</th>" for t in CALL_TYPES) + "</tr>"
    rows = ""
    for e in CALL_TYPES:
        cells = "".join(f"<td>{matrix[e][p]}</td>" for p in CALL_TYPES)
        rows += f"<tr><th>{e}</th>{cells}</tr>"
    return f"<table>{header}{rows}</table>"


def _category_table(per_category: dict) -> str:
    header = (
        "<tr><th>category</th><th>n</th><th>exact match</th><th>gate pass</th>"
        "<th>recall@6</th><th>grounded</th><th>mean quality</th></tr>"
    )
    rows = ""
    for cat, stats in per_category.items():
        marker = " &#9733;" if cat in HIGHLIGHT_CATEGORIES else ""
        rows += (
            f"<tr><td>{_esc(cat)}{marker}</td><td>{stats['n']}</td>"
            f"<td>{_pct(stats['exact_match_rate'])}</td>"
            f"<td>{_pct(stats['gate_pass_rate'])}</td>"
            f"<td>{_pct(stats['retrieval']['recall_at_6'])}</td>"
            f"<td>{_pct(stats['grounding']['grounded_rate'])}</td>"
            f"<td>{_fmt(stats['quality']['mean_quality'])}</td></tr>"
        )
    return f"<table>{header}{rows}</table><p class='section-note'>&#9733; = highlighted per spec §5</p>"


def build_html(scored: list[dict], run_label: str = "") -> str:
    rep = build_report(scored)
    cc = rep["call_correctness"]

    rows_html = "\n".join(_record_row(r) for r in scored)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Trailside Eval Report{" - " + _esc(run_label) if run_label else ""}</title>
<style>{CSS}</style>
</head>
<body>
<h1>Trailside Eval Report</h1>
<p class="subtitle">{_esc(run_label)} &middot; {rep['n_records']} ground-truth records</p>

<div class="headline-row">
  <div class="headline-card">
    <div class="big">{_pct(rep['gate_pass_rate'])}</div>
    <div class="label">Gate-pass rate</div>
  </div>
  <div class="headline-card">
    <div class="big">{_fmt(rep['quality']['mean_quality'])} / 5</div>
    <div class="label">Mean quality (n={rep['quality']['n_scoreable']})</div>
  </div>
  <div class="headline-card">
    <div class="big">{_pct(cc['exact_match_rate'])}</div>
    <div class="label">Call exact-match rate</div>
  </div>
  <div class="headline-card">
    <div class="big">{_pct(rep['retrieval']['recall_at_6'])}</div>
    <div class="label">Recall@6 (n={rep['retrieval']['n_scoreable']})</div>
  </div>
  <div class="headline-card">
    <div class="big">{_pct(rep['grounding']['grounded_rate'])}</div>
    <div class="label">Grounded rate (n={rep['grounding']['n_scoreable']})</div>
  </div>
</div>
<p class="section-note">Per spec §5: gate-pass rate and mean quality are reported separately &mdash; the gap between them is the finding.</p>

<h2>Call correctness</h2>
<p>Over-confidence errors ({cc['over_confidence_count']}): <span class="mono">{', '.join(cc['over_confidence_ids']) or 'none'}</span></p>
<p>Over-caution errors ({cc['over_caution_count']}): <span class="mono">{', '.join(cc['over_caution_ids']) or 'none'}</span></p>
{_confusion_table(cc['confusion_matrix'])}

<h2>Per-category breakdown</h2>
{_category_table(rep['per_category'])}

<h2>All records</h2>
<p class="section-note">Purple-outlined rows = the GT-013/014 temporal-hedge reproducibility pair. Click "answer + context" to expand.</p>
<table>
<tr>
  <th>ID</th><th>Question</th><th>Category</th><th>Call (expected &rarr; got)</th>
  <th>Retrieval</th><th>Grounding</th><th>Gate</th><th>Quality</th><th>Details</th>
</tr>
{rows_html}
</table>

</body>
</html>"""


def write_html_report(scored: list[dict], out_path: pathlib.Path, run_label: str = "") -> pathlib.Path:
    out_path = pathlib.Path(out_path)
    out_path.write_text(build_html(scored, run_label=run_label))
    return out_path
