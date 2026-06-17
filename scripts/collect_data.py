#!/usr/bin/env python3
"""
collect_data.py — Refresh whatsblooming plant data from Calflora.

Primary data source (Path W — automated, no API key needed):
  The Calflora "What Grows Here" (WGH) tool at
  https://www.calflora.org/entry/wgh.html drives a GWT-RPC endpoint at
  https://www.calflora.org/app/userdata. A single POST for a saved polygon
  (shape id, e.g. rs3899) returns every plant recorded in that area, with
  scientific + common name, family, growth habit, native status, bloom
  start/end months, up to 3 photos (with attributions), and the Calflora
  plant id. This script decodes that GWT-RPC response directly.

Fallback (Path A): a Calflora WGH tab-delimited text export via --tsv.

Photos come from Calflora's own photo set (attribution preserved). No
iNaturalist lookups are needed, so a full refresh is one HTTP request.

Usage:
  python scripts/collect_data.py [options]

  --shape-id ID    Calflora saved polygon shape id (default: rs3899)
  --tsv PATH       Use a Calflora WGH text export instead of the live endpoint
  --all            Include non-native plants too (default: CA natives only)
  --output PATH    Where to write plants.json (default: data/plants.json)
  --existing PATH  Existing plants.json to preserve photos from when missing
  --raw PATH       Save the raw GWT-RPC response to PATH (debugging)
  --dry-run        Print result to stdout, don't write file
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ── Calflora WGH (GWT-RPC) endpoint ──────────────────────────────────────────
# This is the request the WGH tool fires when you run a search for a saved
# polygon. The strong-name hash and module/permutation headers are tied to
# Calflora's currently deployed GWT build; if the endpoint starts returning an
# error instead of "//OK[...]", re-capture these from the browser Network tab
# (XHR -> /app/userdata) on https://www.calflora.org/entry/wgh.html.
WGH_ENDPOINT = "https://www.calflora.org/app/userdata"
WGH_STRONGNAME = "CCD946811B7108DD7F57B9B1BDC37CBB"
WGH_MODULE_BASE = "https://www.calflora.org/entry/com.gmap3.Wgh3J/"
WGH_PERMUTATION = "61E52EB5745FD49C921AA4BD9FC33FBE"

# GWT-RPC request payload. {shape_id} is the only thing we vary; every other
# token indexes the inline string table by position, so swapping the rid value
# string is safe. minc|10 = minimum 10 records; nstatus|2 filters at the query
# level too, but we also filter in code so the meaning is explicit.
WGH_PAYLOAD_TEMPLATE = (
    "7|0|18|https://www.calflora.org/entry/com.gmap3.Wgh3J/|"
    "CCD946811B7108DD7F57B9B1BDC37CBB|"
    "com.cfapp.client.wentry.UserDataService|oneList|"
    "java.lang.String/2004016611|java.util.HashMap/1797211028|"
    "wgh|129411|dateAfter|1920-01-01|rid|{shape_id}|nstatus|2|grez|8|minc|10|"
    "1|2|3|4|3|5|5|6|7|8|6|5|5|9|5|10|5|11|5|12|5|13|5|14|5|15|5|16|5|17|5|18|"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Content-Type": "text/x-gwt-rpc; charset=UTF-8",
    "Origin": "https://www.calflora.org",
    "Referer": "https://www.calflora.org/entry/wgh.html",
    "X-GWT-Module-Base": WGH_MODULE_BASE,
    "X-GWT-Permutation": WGH_PERMUTATION,
    "Cookie": "cflogin=login",
}

# Field positions inside each decoded String[] record returned by WGH.
F_SCI, F_COMMON, F_HABIT, F_NSTATUS, F_FAMILY = 0, 1, 2, 3, 4
F_BLOOM_START, F_BLOOM_END = 6, 7
F_PHOTO = (8, 10, 12)          # photo url positions
F_PHOTO_ATTR = (9, 11, 13)     # matching attribution positions
F_ID, F_RELATION = 17, 18      # calflora id; None/"parent"/"child" taxonomy rel
NATIVE_CODE = "2"


# ─────────────────────────── Calflora WGH (GWT-RPC) ──────────────────────────

def fetch_wgh_raw(shape_id: str) -> str:
    """POST the WGH GWT-RPC request for a saved polygon, return the raw body."""
    payload = WGH_PAYLOAD_TEMPLATE.format(shape_id=shape_id)
    req = urllib.request.Request(
        WGH_ENDPOINT, data=payload.encode("utf-8"), headers=HEADERS, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def decode_gwt_records(raw: str) -> list[list]:
    """
    Decode a GWT-RPC '//OK[...]' response into a list of String[] records.

    The body is JSON once the GWT \\xHH escapes are rewritten to \\u00HH. It is
    [<int tokens...>, [<string table>], flags, version]. GWT reads tokens from
    the tail, so we reverse them. The top object is an ArrayList of String[];
    a string token of 0 means null, otherwise it is a 1-based index into the
    string table.
    """
    raw = raw.strip()
    if not raw.startswith("//OK"):
        raise RuntimeError(f"Unexpected WGH response (not //OK): {raw[:200]!r}")
    arr = json.loads(re.sub(r"\\x([0-9a-fA-F]{2})", r"\\u00\1", raw[4:]))

    stab_i = next(i for i, el in enumerate(arr) if isinstance(el, list))
    strtab = arr[stab_i]
    stream = arr[:stab_i][::-1]
    pos = 0

    def read_int() -> int:
        nonlocal pos
        v = stream[pos]
        pos += 1
        return v

    def read_str():
        i = read_int()
        return None if i == 0 else strtab[i - 1]

    top = strtab[read_int() - 1]
    if not top.startswith("java.util.ArrayList"):
        raise RuntimeError(f"Expected ArrayList at top of response, got {top!r}")

    size = read_int()
    records = []
    for _ in range(size):
        read_int()                       # element type ref ([Ljava.lang.String;)
        n = read_int()                   # array length
        records.append([read_str() for _ in range(n)])
    return records


def expand_bloom_months(start, end) -> list[int]:
    """'3','5' -> [3,4,5]; handles wraparound like '11','2' -> [11,12,1,2]."""
    if not start or not end:
        return []
    a, b = int(start), int(end)
    if not (1 <= a <= 12 and 1 <= b <= 12):
        return []
    return list(range(a, b + 1)) if a <= b else list(range(a, 13)) + list(range(1, b + 1))


def records_to_plants(records: list[list], natives_only: bool) -> list[dict]:
    """Map decoded WGH String[] records to plant dicts (pre-enrichment)."""
    plants = []
    for r in records:
        if len(r) <= F_RELATION:
            continue
        if natives_only and r[F_NSTATUS] != NATIVE_CODE:
            continue
        sci = (r[F_SCI] or "").strip()
        if not sci:
            continue

        photo_url = photo_attr = None
        for u_pos, a_pos in zip(F_PHOTO, F_PHOTO_ATTR):
            if r[u_pos]:
                photo_url = r[u_pos]
                photo_attr = r[a_pos]
                break

        plants.append({
            "scientific_name": sci,
            "common_name": (r[F_COMMON] or "").strip(),
            "family": r[F_FAMILY],
            "growth_habit": r[F_HABIT],
            "native": r[F_NSTATUS] == NATIVE_CODE,
            "calflora_id": r[F_ID],
            "bloom_months": expand_bloom_months(r[F_BLOOM_START], r[F_BLOOM_END]),
            "photo_url": photo_url,
            "photo_attribution": photo_attr,
        })
    return plants


# ─────────────────────────── TSV fallback (Path A) ───────────────────────────

def load_from_tsv(tsv_path: str) -> list[dict]:
    """Parse a Calflora WGH tab-delimited text export (fallback path)."""
    import csv

    MONTH_ABBRS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    MONTH_NAMES = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }

    plants = []
    with open(tsv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        headers_lower = [h.lower().strip() for h in (reader.fieldnames or [])]
        month_cols = [h for h in headers_lower if h[:3] in MONTH_ABBRS]
        has_bloom_col = "bloom months" in headers_lower or "bloom_months" in headers_lower

        for row in reader:
            row_lower = {k.lower().strip(): v for k, v in row.items()}
            sci = (row_lower.get("taxon") or row_lower.get("scientific name")
                   or row_lower.get("scientific_name") or "").strip()
            common = (row_lower.get("common name") or row_lower.get("common_name") or "").strip()
            if not sci:
                continue

            bloom_months: list[int] = []
            if month_cols:
                for col in month_cols:
                    if row_lower.get(col, "").strip().lower() in ("x", "1", "yes", "true", "bloom"):
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

            plants.append({
                "scientific_name": sci,
                "common_name": common,
                "family": None,
                "growth_habit": None,
                "native": True,
                "calflora_id": None,
                "bloom_months": sorted(set(bloom_months)),
                "photo_url": None,
                "photo_attribution": None,
            })

    print(f"Loaded {len(plants)} plants from TSV: {tsv_path}", file=sys.stderr)
    return plants


# ─────────────────────────── URL builders ────────────────────────────────────

def make_calflora_url(plant: dict) -> str:
    if plant.get("calflora_id"):
        return f"https://www.calflora.org/cgi-bin/species_query.cgi?where-calrecnum={plant['calflora_id']}"
    return f"https://www.calflora.org/entry/visnome.html#srch=t&taxon={urllib.parse.quote(plant['scientific_name'])}"


def make_calscape_url(scientific_name: str, common_name: str) -> str:
    sci = scientific_name.replace(" ", "-")
    com = common_name.replace(" ", "-")
    return f"https://calscape.org/plant/{sci}-({com})/"


# ─────────────────────────── Main pipeline ───────────────────────────────────

def dedupe_by_common_name(plants: list[dict]) -> list[dict]:
    """Collapse records sharing a common name (case-insensitive).

    Calflora lists subspecies/varieties separately but they often share one
    common name. For this casual site we keep a single representative per common
    name, preferring one that has a photo and the cleaner (shortest) scientific
    name, and union the bloom months so no blooming coverage is lost.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for p in plants:
        key = (p["common_name"] or "").strip().lower()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)

    out = []
    for key in order:
        recs = groups[key]
        rep = dict(sorted(
            recs,
            key=lambda r: (not bool(r.get("photo_url")), len(r.get("scientific_name") or "")),
        )[0])
        months: set = set()
        for r in recs:
            months.update(r.get("bloom_months") or [])
        rep["bloom_months"] = sorted(months)
        out.append(rep)
    return out


def build_output(plants: list[dict], existing: dict[str, dict]) -> list[dict]:
    """Finalize records: add link URLs and preserve a prior photo if missing."""
    out = []
    for p in plants:
        sci = p["scientific_name"]
        common = p["common_name"] or sci  # fall back to scientific name
        photo_url = p["photo_url"]
        photo_attr = p["photo_attribution"]
        if not photo_url and sci in existing:
            photo_url = existing[sci].get("photo_url")
            photo_attr = existing[sci].get("photo_attribution")

        out.append({
            "common_name": common,
            "scientific_name": sci,
            "family": p.get("family"),
            "growth_habit": p.get("growth_habit"),
            "native": p.get("native", True),
            "bloom_months": p["bloom_months"],
            "calflora_url": make_calflora_url(p),
            "calscape_url": make_calscape_url(sci, common),
            "photo_url": photo_url,
            "photo_attribution": photo_attr,
        })
    out = dedupe_by_common_name(out)
    out.sort(key=lambda x: x["common_name"] or x["scientific_name"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh whatsblooming plant data from Calflora")
    parser.add_argument("--shape-id", default="rs3899", help="Calflora saved polygon shape id")
    parser.add_argument("--tsv", help="Use a Calflora WGH text export instead of the live endpoint")
    parser.add_argument("--all", action="store_true", help="Include non-native plants too")
    parser.add_argument("--output", default="data/plants.json", help="Output path")
    parser.add_argument("--existing", default="data/plants.json",
                        help="Existing plants.json for photo preservation")
    parser.add_argument("--raw", help="Save the raw GWT-RPC response to this path (debugging)")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON, don't write file")
    args = parser.parse_args()

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

    if args.tsv:
        plants = load_from_tsv(args.tsv)
    else:
        print(f"Fetching WGH polygon {args.shape_id} from Calflora...", file=sys.stderr)
        raw = fetch_wgh_raw(args.shape_id)
        if args.raw:
            Path(args.raw).write_text(raw, encoding="utf-8")
        records = decode_gwt_records(raw)
        print(f"Decoded {len(records)} records from WGH", file=sys.stderr)
        plants = records_to_plants(records, natives_only=not args.all)
        print(f"Kept {len(plants)} plants ({'all' if args.all else 'natives only'})", file=sys.stderr)

    output = build_output(plants, existing)
    with_photos = sum(1 for p in output if p["photo_url"])
    with_bloom = sum(1 for p in output if p["bloom_months"])
    print(f"Final: {len(output)} plants, {with_photos} with photos, "
          f"{with_bloom} with bloom months", file=sys.stderr)

    text = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    if args.dry_run:
        print(text)
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote {len(output)} plants to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
