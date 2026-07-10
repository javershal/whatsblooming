"""§7 -- shared LLM-judge plumbing.

Reuses the pipeline's GeminiProvider/LLMProvider (no new model client).
temperature=0 and structured JSON output come for free from
GeminiProvider.generate(), which already sets those for every call.

Grounding and quality are separate judge calls with separate prompts (§7) --
this module exposes one function per judge, each returning a dict with a
one-line justification that the caller is responsible for persisting.

Judge model choice (§7): same GeminiProvider/model as the generator
(gemini-3.1-flash-lite -- moved off gemini-2.5-flash-lite, whose 20/day free-tier
cap can't cover a 52-record run's ~150+ calls; 3.1-flash-lite's daily cap is
500, RPM is still 15). A stronger judge model would be defensible, but the
generator and judge share the same free-tier RPM budget, so keeping one
provider/model keeps the rate-limit bookkeeping in one place.
"""
from __future__ import annotations

import json
import time

import httpx
from google.genai import errors as genai_errors

from trailside.pipeline import LLMProvider

# Free-tier Gemini is capped at 15 RPM.
RATE_LIMIT_SLEEP_SECONDS = 4.5

MAX_RETRIES = 5
RETRY_BASE_DELAY_SECONDS = 8.0

# 429 = rate limit (§7's 15 RPM free-tier cap); 503 = transient server
# overload. httpx transport errors (dropped connections, timeouts) are also
# transient -- all worth a backoff-and-retry, not a hard failure.
RETRIABLE_API_CODES = (429, 503)
RETRIABLE_TRANSPORT_ERRORS = (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException)


class JudgeError(Exception):
    pass


def call_with_retry(fn, *args, max_retries: int = MAX_RETRIES, **kwargs):
    """Call fn(*args, **kwargs), retrying with backoff on transient API/network
    errors. Shared by judge calls and the runner's ask() calls -- both hit the
    same Gemini API and are subject to the same transient failures."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except genai_errors.APIError as e:
            if e.code in RETRIABLE_API_CODES and attempt < max_retries - 1:
                time.sleep(RETRY_BASE_DELAY_SECONDS * (attempt + 1))
                continue
            raise
        except RETRIABLE_TRANSPORT_ERRORS:
            if attempt < max_retries - 1:
                time.sleep(RETRY_BASE_DELAY_SECONDS * (attempt + 1))
                continue
            raise
    raise JudgeError("Exceeded retries due to rate limiting or transient network errors")


def _parse_first_json_object(raw: str) -> dict:
    """The judge model occasionally appends stray trailing text after a
    well-formed JSON object even with response_mime_type=application/json;
    decode just the leading object and ignore the rest."""
    return json.JSONDecoder().raw_decode(raw.strip())[0]


def _call_judge(provider: LLMProvider, system: str, user: str) -> dict:
    raw = call_with_retry(provider.generate, system=system, user=user)
    try:
        return _parse_first_json_object(raw)
    except json.JSONDecodeError:
        raise JudgeError(f"Judge returned non-JSON output: {raw!r}")


GROUNDING_SYSTEM = """\
You are a strict grounding auditor for a wildflower trip-planning assistant \
(Trailside). You will be given the user's QUESTION, the CONTEXT the assistant \
retrieved (exactly what the assistant could see when it answered), and the \
assistant's ANSWER.

Decide whether EVERY factual claim in the ANSWER is supported by CONTEXT. A \
claim is any specific plant name, bloom-month, place name, or habitat detail.

Zero-fabrication rule: if the ANSWER names even ONE plant, place, or \
bloom-month that is not present in or supported by CONTEXT, the entire answer \
is not_grounded -- even if the rest of the answer is correct. This bar is \
deliberately strict.

Judge only against the given CONTEXT, never against your own botanical \
knowledge -- if CONTEXT doesn't support a claim, it is unsupported even if it \
happens to be true in the real world.

Return strict JSON: {"grounded": true|false, "justification": "<one line>"}\
"""

QUALITY_SYSTEM = """\
You are a quality grader for a wildflower trip-planning assistant (Trailside) \
used by hikers planning trips in Monterey County, CA. You will be given the \
user's QUESTION, the assistant's ANSWER, and an EXPECTED_ANSWER reference.

EXPECTED_ANSWER is a grading reference, not a literal string to match -- for \
list answers it names the full correct match set and count.

Score the ANSWER 1-5 on a single combined scale folding together:
- Completeness: for list-type answers, does it surface the right matches \
without omission or padding? Capping at ~5 strong matches and offering more is \
CORRECT behavior when the true set is larger, not a penalty. Padding with \
improbable, wrong-habitat, or wrong-month filler to look thorough is a \
penalty.
- Actionability: is the answer useful for a hiker deciding whether/where to \
go (bloom expectations + place/time context + a clear next step)?

Anchors:
5 = right set (or correctly capped + offered more), no padding, no omission, \
clearly actionable.
4 = minor omission or slight padding, but still clearly useful.
3 = mostly right but a noticeable gap (missed 1-2 obvious matches), or usable \
but leaves the planner with obvious follow-up work.
2 = major omission, wrong-item padding, or barely actionable.
1 = fails to support a go/where decision, or the set is substantially wrong.

Return strict JSON: {"score": <1-5 integer>, "justification": "<one line>"}\
"""


def judge_grounding(provider: LLMProvider, question: str, answer: str,
                     retrieved_context: list[dict]) -> dict:
    context_text = "\n\n".join(c["text"] for c in retrieved_context)
    user = (
        f"QUESTION: {question}\n\n"
        f"CONTEXT (what the assistant retrieved and saw):\n{context_text}\n\n"
        f"ANSWER (to judge):\n{answer}"
    )
    result = _call_judge(provider, GROUNDING_SYSTEM, user)
    return {
        "grounded": bool(result["grounded"]),
        "justification": result.get("justification", ""),
    }


def judge_quality(provider: LLMProvider, question: str, answer: str,
                   expected_answer: str) -> dict:
    user = (
        f"QUESTION: {question}\n\n"
        f"EXPECTED_ANSWER (grading reference -- named match-set + count, not "
        f"a literal string to match):\n{expected_answer}\n\n"
        f"ANSWER (to grade):\n{answer}"
    )
    result = _call_judge(provider, QUALITY_SYSTEM, user)
    return {
        "score": int(result["score"]),
        "justification": result.get("justification", ""),
    }
