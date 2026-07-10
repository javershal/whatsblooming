"""Phase 4 eval harness for the Trailside pipeline.

Implements the metric families defined in eval_metric_spec.md:
  1. retrieval (recall@6, MRR)              -- mechanical
  2. grounding / faithfulness                -- LLM judge, binary
  3. call correctness (answer/hedge/redirect/refuse) -- mechanical
  4. answer quality (1-5)                    -- LLM judge, gated
  5. reporting (gate-pass rate vs mean quality, per-category)
  6. regression (diff vs a saved baseline)
"""
