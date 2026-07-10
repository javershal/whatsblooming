"""Quick smoke test for the Phase 3 pipeline."""
import json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from trailside.pipeline import ask

TESTS = [
    # (label, question, month)
    ("J1 basic",          "What's blooming at Point Lobos in April?",        4),
    ("J2 basic",          "Where can I see California poppies near Monterey?", None),
    ("temporal hedge",    "Is the lupine out yet?",                           9),
    ("out-of-scope",      "Can you identify this plant from my photo?",       None),
    ("unsourced place",   "What's blooming at Jack's Peak in May?",           5),
]

for label, q, month in TESTS:
    print(f"\n{'='*60}")
    print(f"[{label}] {q}" + (f" (month={month})" if month else ""))
    r = ask(q, month=month)
    print(f"call_type : {r['call_type']}")
    print(f"sources   : {r['sources']}")
    print(f"answer    : {r['answer'][:300]}")
