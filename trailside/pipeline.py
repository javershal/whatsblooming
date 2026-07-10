"""
Trailside RAG pipeline — Phase 3.

Public API:
    ask(question, month=None) -> {
        "call_type": str, "answer": str, "sources": [str],
        "retrieved_context": [{"id": str, "text": str}],
    }

call_type is the rubric's 4-way gradient: answer / hedge / redirect / refuse.
sources is a list of plant common names cited in the answer.
retrieved_context is the top-K chunks actually fed to the model (for eval
harness grounding checks — what the model SAW, not the whole corpus).

The model-call layer is provider-agnostic: swap GeminiProvider for any class
that implements LLMProvider (generate + embed).
"""
from __future__ import annotations

import json
import math
import os
import pathlib
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

ROOT = pathlib.Path(__file__).parent.parent
PLANTS_FILE = ROOT / "data" / "trailside_plants.json"
PLACES_FILE = ROOT / "data" / "places.json"
CACHE_FILE = ROOT / "trailside" / "embeddings_cache.json"
KEY_FILE = ROOT / "geminikey.txt"

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

RETRIEVAL_K = 6  # chunks returned to the model

SYSTEM_PROMPT = """\
You are Trailside, a trip-planning assistant for hikers in Monterey County, CA.
Your corpus is a fixed set of 29 Monterey native plants and 3 well-known spots
(Garland Ranch, Asilomar, Point Lobos). You answer at the habitat/plant-community
level — never make claims about specific trails, exact trail conditions, or
trail-microsite details.

You have two jobs:
  J1: place + time of year → what wildflowers will I see?
  J2: flower of interest → where and when can I find it?

Rules:
1. Answer ONLY from the CONTEXT block below. Do not use general botanical knowledge.
   If a plant you know about from training is not in CONTEXT, do not mention it.
2. Bloom months in CONTEXT are typical/expected ranges — you do not know current
   field conditions. If asked "is it blooming right now?", answer about expected
   timing but explicitly say you cannot confirm live conditions.
3. Stay at habitat level. Do not speculate about specific trail segments.
4. Out-of-scope: photo/visual plant ID, foraging, garden/landscaping advice,
   regions outside Monterey County, plants not in CONTEXT. Politely decline these
   and briefly say what you can help with instead.
5. Return your response as valid JSON (no markdown fences) with exactly these keys:
     "call_type": one of "answer" | "hedge" | "redirect" | "refuse"
     "answer": your response text (may be empty string for a pure refuse)
     "sources": list of plant common names from CONTEXT that you cited ([] if none)

call_type definitions:
  answer   — confident, grounded response; all claims supported by CONTEXT
  hedge    — grounded claim + honestly named uncertainty (temporal, coverage, etc.)
  redirect — question is partly out of scope; give what you can, redirect the rest
  refuse   — completely out of scope; decline and say briefly what you do cover

CONTEXT:
{context}
"""


# ---------------------------------------------------------------------------
# Provider-agnostic LLM interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Return the model's text response."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""


class GeminiProvider(LLMProvider):
    GEN_MODEL = "gemini-3.1-flash-lite"
    EMBED_MODEL = "models/gemini-embedding-001"

    def __init__(self, api_key: Optional[str] = None):
        from google import genai  # import here so the module loads without it
        key = api_key or os.environ.get("GEMINI_API_KEY") or KEY_FILE.read_text().strip()
        self._client = genai.Client(api_key=key)

    def generate(self, system: str, user: str) -> str:
        from google.genai import types
        response = self._client.models.generate_content(
            model=self.GEN_MODEL,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        return response.text

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self._client.models.embed_content(
            model=self.EMBED_MODEL,
            contents=texts,
        )
        return [e.values for e in result.embeddings]


# ---------------------------------------------------------------------------
# Corpus chunking
# ---------------------------------------------------------------------------

def _make_chunks(plants: list[dict], places: list[dict]) -> list[dict]:
    chunks = []
    for p in plants:
        bloom = ", ".join(MONTH_NAMES[m] for m in sorted(p["bloom_months"]))
        habitats = ", ".join(p["habitat"])
        text = (
            f"Plant: {p['common_name']} ({p['scientific_name']})\n"
            f"Bloom months: {bloom}\n"
            f"Habitats: {habitats}\n"
            f"Description: {p['description']}"
        )
        chunks.append({"type": "plant", "id": p["common_name"], "text": text})

    for pl in places:
        habitats = ", ".join(pl["habitat"])
        aliases = ", ".join(pl.get("aka", []))
        alias_str = f" (also known as: {aliases})" if aliases else ""
        text = (
            f"Place: {pl['name']}{alias_str}\n"
            f"Habitats found here: {habitats}"
        )
        chunks.append({"type": "place", "id": pl["name"], "text": text})

    return chunks


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------

def _load_or_build_cache(provider: LLMProvider, chunks: list[dict]) -> dict[str, list[float]]:
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text())
        cached_ids = {c["id"] for c in cache}
        current_ids = {c["id"] for c in chunks}
        if cached_ids == current_ids:
            return {c["id"]: c["embedding"] for c in cache}

    print(f"Building embeddings for {len(chunks)} chunks...")
    texts = [c["text"] for c in chunks]
    embeddings = provider.embed(texts)
    cache_data = [{"id": c["id"], "embedding": e} for c, e in zip(chunks, embeddings)]
    CACHE_FILE.write_text(json.dumps(cache_data, indent=2))
    print(f"Cached to {CACHE_FILE.relative_to(ROOT)}")
    return {c["id"]: e for c, e in zip(chunks, embeddings)}


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _cosine_sim(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


def _retrieve(query_vec: list[float], chunks: list[dict],
              cache: dict[str, list[float]], k: int = RETRIEVAL_K) -> list[dict]:
    scored = [(c, _cosine_sim(query_vec, cache[c["id"]])) for c in chunks]
    return [c for c, _ in sorted(scored, key=lambda x: -x[1])[:k]]


# ---------------------------------------------------------------------------
# Pipeline state (module-level lazy init)
# ---------------------------------------------------------------------------

_provider: Optional[LLMProvider] = None
_chunks: Optional[list[dict]] = None
_cache: Optional[dict[str, list[float]]] = None


def _init(provider: Optional[LLMProvider] = None):
    global _provider, _chunks, _cache
    if _chunks is not None and _provider is provider:
        return
    _provider = provider or GeminiProvider()
    plants = json.loads(PLANTS_FILE.read_text())
    places = json.loads(PLACES_FILE.read_text())
    _chunks = _make_chunks(plants, places)
    _cache = _load_or_build_cache(_provider, _chunks)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(question: str, month: Optional[int] = None,
        provider: Optional[LLMProvider] = None) -> dict:
    """
    Ask Trailside a question. Returns:
        {
            "call_type": "answer" | "hedge" | "redirect" | "refuse",
            "answer": str,
            "sources": [str],   # plant common names cited
        }

    month: integer 1–12; supply for temporal questions (maps to eval_month in
           the ground-truth set). Appended to the query for retrieval only.
    """
    _init(provider)

    # Embed the query (optionally with month context for better retrieval)
    month_str = f" in {MONTH_NAMES[month]}" if month else ""
    retrieval_query = question + month_str
    query_vec = _provider.embed([retrieval_query])[0]

    top_chunks = _retrieve(query_vec, _chunks, _cache)
    context = "\n\n".join(c["text"] for c in top_chunks)

    raw = _provider.generate(
        system=SYSTEM_PROMPT.format(context=context),
        user=question + (f"\n\n[Current month for this query: {MONTH_NAMES[month]}]" if month else ""),
    )

    retrieved_context = [{"id": c["id"], "text": c["text"]} for c in top_chunks]

    try:
        result = json.loads(raw)
        # Normalize: ensure all three keys exist
        result.setdefault("call_type", "answer")
        result.setdefault("answer", "")
        result.setdefault("sources", [])
        result["retrieved_context"] = retrieved_context
        return result
    except json.JSONDecodeError:
        # Fallback: treat raw text as the answer
        return {"call_type": "answer", "answer": raw, "sources": [], "retrieved_context": retrieved_context}
