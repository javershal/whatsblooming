#!/usr/bin/env python3
"""
collect_data.py — Refresh whatsblooming plant data.

Data sources:
  - Calflora API (Path B, automated): requires --calflora-key and --shape-id
    Endpoints discovered by inspecting XHR traffic on calflora.org/entry/wgh.html
    while logged in — update CALFLORA_ENDPOINT below once confirmed.
  - Calflora WGH text export (Path A, fallback): pass --tsv path/to/export.tsv
    Download from calflora.org WGH tool → Results Format: Text → Export.

Photos are fetched from iNaturalist (no auth required).

Usage:
  python scripts/collect_data.py [options]

  --tsv PATH           Path to Calflora WGH tab-delimited export (Path A)
  --calflora-key KEY   Calflora API key (Path B); reads CALFLORA_API_KEY env var if omitted
  --shape-id ID        Calflora saved polygon shape ID (default: rs3899)
  --output PATH        Where to write plants.json (default: data/plants.json)
  --existing PATH      Existing plants.json to merge/preserve photos from
  --dry-run            Print result to stdout, don't write file
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ── Calflora API endpoint — update once discovered via DevTools inspection ──
# To discover: open https://www.calflora.org/entry/wgh.html in Chrome,
# open DevTools → Network → XHR/Fetch, run a WGH search for shape rs3899,
# find the JSON-returning request and copy its URL here.
CALFLORA_ENDPOINT = None  # e.g. "https://api.calflora.org/wgh"

INAT_BASE = "https://api.inaturalist.org/v1"
INAT_PLACE_CA = 28  # iNaturalist place_id for California
HEADERS = {"User-Agent": "whatsblooming/1.0 (github.com/jacob/whatsblooming)"}


# ─────────────────────────── Calflora helpers ───────────────────────────────

def load_from_tsv(tsv_path: str) -> list[dict]:
    """
    Parse a Calflora WGH tab-delimited text export.

    Expected column patterns (Calflora may use either):
      Pattern A: columns named Jan, Feb, Mar, ... Dec with 'x' for blooming months
      Pattern B: a single 'Bloom Months' column with comma-separated month names/numbers

    Returns list of dicts with keys: scientific_name, common_name, bloom_months (list[int])
    """
    import csv

    MONTH_ABBRS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    MONTH_NAMES = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }

    plants = []
    with open(tsv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        headers_lower = [h.lower().strip() for h in (reader.fieldnames or [])]

        # Detect which bloom column pattern is present
        month_cols = [h for h in headers_lower if h[:3] in MONTH_ABBRS]
        has_bloom_col = "bloom months" in headers_lower or "bloom_months" in headers_lower

        for row in reader:
            row_lower = {k.lower().strip(): v for k, v in row.items()}

            # Detect scientific name column (Calflora uses "Taxon" or "Scientific Name")
            sci = (
                row_lower.get("taxon")
                or row_lower.get("scientific name")
                or row_lower.get("scientific_name")
                or ""
            ).strip()
            common = (
                row_lower.get("common name")
                or row_lower.get("common_name")
                or ""
            ).strip()

            if not sci:
                continue

            bloom_months: list[int] = []

            if month_cols:
                for col in month_cols:
                    val = row_lower.get(col, "").strip().lower()
                    if val in ("x", "1", "yes", "true", "bloom"):
                        bloom_months.append(MONTH_ABBRS[col[:3]])
            elif has_bloom_col:
                raw = (row_lower.get("bloom months") or row_lower.get("bloom_months") or "").strip()
                for token in raw.replace(";", ",").split(","):
                    token = token.strip().lower()
                    if token in MONTH_NAMES:
                        bloom_months.append(MONTH_NAMES[token])
                    elif token in MONTH_ABBRS:
                        bloom_months.append(MONTH_ABBRS[token])
                    elif token.isdigit():
                        bloom_months.append(int(token))

            bloom_months = sorted(set(bloom_months))
            plants.append({
                "scientific_name": sci,
                "common_name": common,
                "bloom_months": bloom_months,
            })

    print(f"Loaded {len(plants)} plants from TSV: {tsv_path}", file=sys.stderr)
    return plants


def load_from_calflora_api(api_key: str, shape_id: str) -> list[dict]:
    """
    Fetch plant list from Calflora API for the given polygon shape.

    NOTE: CALFLORA_ENDPOINT must be set at the top of this file.
    Discover it by inspecting XHR requests from calflora.org/entry/wgh.html.
    """
    if not CALFLORA_ENDPOINT:
        raise RuntimeError(
            "CALFLORA_ENDPOINT is not configured. "
            "Discover the endpoint by inspecting network traffic on "
            "https://www.calflora.org/entry/wgh.html in Chrome DevTools "
            "(Network → XHR/Fetch), run a WGH search for your polygon, "
            "then set CALFLORA_ENDPOINT at the top of this script."
        )

    params = urllib.parse.urlencode({
        "shapeid": shape_id,
        "nstatus": "CA Native",
        "fmt": "json",
    })
    url = f"{CALFLORA_ENDPOINT}?{params}"
    headers = {**HEADERS, "Authorization": f"Bearer {api_key}"}
    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())

    # Parse response — field names depend on the actual API response structure.
    # Update the field mappings below to match what Calflora returns.
    plants = []
    for item in data if isinstance(data, list) else data.get("results", []):
        sci = item.get("taxon") or item.get("scientific_name") or item.get("name", "")
        common = item.get("common_name") or item.get("cname", "")

        # Bloom months may come as a list of ints, a bitmask, or month abbreviations.
        # Update this parsing to match the actual response format.
        raw_bloom = item.get("bloom_months") or item.get("bloom") or []
        if isinstance(raw_bloom, list):
            bloom_months = sorted(set(int(m) for m in raw_bloom if str(m).isdigit()))
        else:
            bloom_months = []

        if sci:
            plants.append({
                "scientific_name": sci.strip(),
                "common_name": common.strip(),
                "bloom_months": bloom_months,
            })

    print(f"Loaded {len(plants)} plants from Calflora API (shape: {shape_id})", file=sys.stderr)
    return plants


# ─────────────────────────── iNaturalist helpers ─────────────────────────────

def _inat_get(path: str) -> dict:
    url = f"{INAT_BASE}{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


UNUSABLE_LICENSES = {None, "all-rights-reserved"}


def _usable_photo(photo: dict) -> dict | None:
    if photo.get("license_code") in UNUSABLE_LICENSES:
        return None
    raw_url = photo.get("medium_url") or photo.get("url", "")
    photo_url = raw_url.replace("square", "medium") if raw_url else None
    if not photo_url:
        return None
    return {
        "photo_url": photo_url,
        "photo_attribution": photo.get("attribution", ""),
        "photo_license": photo.get("license_code", ""),
    }


def fetch_inat_photo(scientific_name: str) -> dict:
    """Return {photo_url, photo_attribution, photo_license} or all-None dict."""
    null_result = {"photo_url": None, "photo_attribution": None, "photo_license": None}

    # Try taxa default_photo (most representative)
    try:
        data = _inat_get(f"/taxa?q={urllib.parse.quote(scientific_name)}&rank=species&per_page=5")
        for result in data.get("results", []):
            if result.get("name", "").lower() == scientific_name.lower():
                photo = _usable_photo(result.get("default_photo") or {})
                if photo:
                    return photo
    except Exception as e:
        print(f"  iNat taxa lookup failed for {scientific_name}: {e}", file=sys.stderr)

    time.sleep(0.3)

    # Fallback: top-voted research-grade observations in California
    try:
        path = (
            f"/observations?taxon_name={urllib.parse.quote(scientific_name)}"
            f"&place_id={INAT_PLACE_CA}&quality_grade=research"
            f"&order_by=votes&per_page=10&photos=true"
        )
        obs_data = _inat_get(path)
        for obs in obs_data.get("results", []):
            for op in obs.get("observation_photos", []):
                photo = _usable_photo(op.get("photo") or {})
                if photo:
                    return photo
    except Exception as e:
        print(f"  iNat observations lookup failed for {scientific_name}: {e}", file=sys.stderr)

    return null_result


# ─────────────────────────── URL builders ────────────────────────────────────

def make_calflora_url(scientific_name: str) -> str:
    encoded = urllib.parse.quote(scientific_name)
    return f"https://www.calflora.org/entry/visnome.html#srch=t&taxon={encoded}"


def make_calscape_url(scientific_name: str, common_name: str) -> str:
    sci = scientific_name.replace(" ", "-")
    com = common_name.replace(" ", "-")
    return f"https://calscape.org/plant/{sci}-({com})/"


# ─────────────────────────── Main pipeline ───────────────────────────────────

def build_plants(
    plant_list: list[dict],
    existing: dict[str, dict],
) -> list[dict]:
    """
    For each plant, enrich with iNaturalist photo and build output record.
    Preserves existing photo if new iNat lookup returns nothing.
    """
    results = []
    total = len(plant_list)
    for i, plant in enumerate(plant_list, 1):
        sci = plant["scientific_name"]
        common = plant["common_name"]
        print(f"[{i}/{total}] {common} ({sci})", file=sys.stderr)

        photo = fetch_inat_photo(sci)

        # Fall back to existing photo if iNat returned nothing
        if not photo["photo_url"] and sci in existing:
            prev = existing[sci]
            photo = {
                "photo_url": prev.get("photo_url"),
                "photo_attribution": prev.get("photo_attribution"),
                "photo_license": prev.get("photo_license"),
            }
            if photo["photo_url"]:
                print(f"  Kept existing photo", file=sys.stderr)

        record = {
            "common_name": common,
            "scientific_name": sci,
            "bloom_months": plant["bloom_months"],
            "calflora_url": make_calflora_url(sci),
            "calscape_url": make_calscape_url(sci, common),
            **photo,
        }
        results.append(record)
        time.sleep(0.5)

    results.sort(key=lambda x: x["common_name"])
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh whatsblooming plant data")
    parser.add_argument("--tsv", help="Path to Calflora WGH tab-delimited export (Path A)")
    parser.add_argument("--calflora-key", default=os.environ.get("CALFLORA_API_KEY"),
                        help="Calflora API key (Path B); falls back to CALFLORA_API_KEY env var")
    parser.add_argument("--shape-id", default="rs3899", help="Calflora polygon shape ID")
    parser.add_argument("--output", default="data/plants.json", help="Output path")
    parser.add_argument("--existing", default="data/plants.json",
                        help="Existing plants.json for photo preservation")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON, don't write file")
    args = parser.parse_args()

    # Load existing data for photo preservation
    existing: dict[str, dict] = {}
    existing_path = Path(args.existing)
    if existing_path.exists():
        try:
            with open(existing_path) as f:
                for entry in json.load(f):
                    existing[entry["scientific_name"]] = entry
            print(f"Loaded {len(existing)} existing entries for photo preservation", file=sys.stderr)
        except Exception as e:
            print(f"Warning: could not load existing data: {e}", file=sys.stderr)

    # Phase 1: Load plant list
    plant_list: list[dict] | None = None

    if args.tsv:
        plant_list = load_from_tsv(args.tsv)
    elif args.calflora_key:
        try:
            plant_list = load_from_calflora_api(args.calflora_key, args.shape_id)
        except RuntimeError as e:
            print(f"Calflora API not configured: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Calflora API failed: {e}", file=sys.stderr)
            print("Falling back to existing plant list for photo refresh only.", file=sys.stderr)

    if plant_list is None:
        if existing:
            print("No new plant list available — refreshing photos for existing plants only.", file=sys.stderr)
            plant_list = [
                {"scientific_name": v["scientific_name"],
                 "common_name": v["common_name"],
                 "bloom_months": v["bloom_months"]}
                for v in existing.values()
            ]
        else:
            print("Error: no --tsv file, no working Calflora API, and no existing data.", file=sys.stderr)
            sys.exit(1)

    # Phase 2-4: Build enriched records
    plants = build_plants(plant_list, existing)

    output = json.dumps(plants, indent=2, ensure_ascii=False) + "\n"

    if args.dry_run:
        print(output)
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Wrote {len(plants)} plants to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
