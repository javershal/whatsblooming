#!/usr/bin/env python3
"""Phase 1 populate: build the fixed-set Trailside corpus.

Reads the 29 curated natives out of data/plants.json, fetches each plant's
Calflora species page for its `Habitat` and `Communities` fields, maps the
CNPS plant-community names onto Trailside's 7-habitat controlled vocabulary,
and writes data/trailside_plants.json.

Provenance: habitat is derived from Calflora (calflora_url kept on every
record); the raw community strings are preserved in `habitat_raw` so the
mapping is auditable. Per the rubric, the corpus is recorded *faithfully* to
the source — botanical completeness of Calflora is a data-quality matter, out
of scope for the eval. See trailside/schema_decision.md.
"""
import json, re, html, time, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLANTS = ROOT / "data" / "plants.json"
OUT = ROOT / "data" / "trailside_plants.json"

# The locked fixed set, by exact scientific_name as it appears in plants.json.
FIXED_SET = [
    "Diplacus aurantiacus", "Eriogonum latifolium", "Artemisia californica",
    "Erigeron glaucus", "Castilleja affinis ssp. affinis", "Dudleya farinosa",
    "Lupinus chamissonis", "Abronia umbellata", "Solidago spathulata",
    "Camissoniopsis cheiranthifolia", "Salvia mellifera", "Dendromecon rigida",
    "Ceanothus thyrsiflorus var. griseus", "Arctostaphylos glauca",
    "Adenostoma fasciculatum", "Salvia spathacea", "Iris douglasiana",
    "Frangula californica", "Quercus agrifolia", "Heteromeles arbutifolia",
    "Aquilegia formosa", "Erythranthe guttata",
    "Lonicera involucrata var. ledebourii", "Eschscholzia californica",
    "Lupinus succulentus", "Sidalcea malviflora", "Sisyrinchium bellum",
    "Salvia columbariae", "Garrya elliptica",
]

# Calflora CNPS community name -> Trailside habitat vocab.
# Communities not present in the Monterey planning area (montane conifer,
# desert) map to None and are dropped.
COMMUNITY_MAP = {
    "Northern Coastal Scrub": "coastal-bluff scrub",
    "Coastal Sage Scrub": "coastal-bluff scrub",
    "Coastal Strand": "coastal dune/strand",
    "Coastal Prairie": "grassland",
    "Valley Grassland": "grassland",
    "Chaparral": "chaparral",
    "Closed-cone Pine Forest": "Monterey pine forest",
    "Northern Oak Woodland": "oak woodland",
    "Southern Oak Woodland": "oak woodland",
    "Foothill Woodland": "oak woodland",
    "Mixed Evergreen Forest": "oak woodland",
    "wetland-riparian": "riparian",
    # Dropped (out of Monterey planning area): montane conifer + desert.
    "Yellow Pine Forest": None, "Red Fir Forest": None, "Lodgepole Forest": None,
    "Subalpine Forest": None, "Redwood Forest": None, "Joshua Tree Woodland": None,
    "Creosote Bush Scrub": None, "Sagebrush Scrub": None, "Bristlecone Pine Forest": None,
    "Pinyon-Juniper Woodland": None, "Alpine Fell-fields": None, "Shadscale Scrub": None,
}

# Curator overrides (Phase-1 review, 2026-06-29). Calflora's per-(sub)species
# community records have silent local gaps that make the corpus quietly
# *incomplete* (distinct from the statewide over-assignments, which we keep on
# purpose as grounded-but-not-locally-true eval material). Where a plant is
# missing an obvious Monterey habitat, the local-expert curator adds it — flagged
# via `habitat_source: "calflora+curator"`, never silently laundered into the
# Calflora-sourced set. See trailside/schema_decision.md §6.
CURATOR_OVERRIDES = {
    "Sisyrinchium bellum": {
        "add": ["grassland"],
        "reason": "Quintessential spring grassland wildflower locally; Calflora's record gave only Foothill Woodland + wetland-riparian, omitting grassland.",
    },
    "Castilleja affinis ssp. affinis": {
        "add": ["coastal-bluff scrub"],
        "reason": "Common in Monterey coastal scrub; Calflora's subspecies record lists only Valley Grassland.",
    },
    "Heteromeles arbutifolia": {
        "add": ["oak woodland"],
        "reason": "Classic coast-live-oak understory shrub; Calflora gave only Chaparral.",
    },
}

# Faithful one-line, hiker-facing descriptions (form + flower + field note).
DESCRIPTIONS = {
    "Diplacus aurantiacus": "Sprawling evergreen shrub with sticky leaves and showy apricot-orange tubular flowers; a coastal-scrub generalist.",
    "Eriogonum latifolium": "Low mounding subshrub topped with round pinkish-white flower clusters on bare stalks; classic coastal bluff and dune plant.",
    "Artemisia californica": "Aromatic gray-green shrub (California sagebrush) with feathery foliage; the defining smell of coastal sage scrub.",
    "Erigeron glaucus": "Low clumping perennial with lavender, yellow-centered daisies; hugs coastal bluffs and blooms much of the year.",
    "Castilleja affinis ssp. affinis": "Hemiparasitic perennial with bright red-orange paintbrush-like bracts; found in open grassland and scrub.",
    "Dudleya farinosa": "Rosette succulent (bluff lettuce) with chalky leaves and tall yellow flower stalks; clings to coastal rock.",
    "Lupinus chamissonis": "Silvery-leaved dune shrub (beach blue lupine) with blue-and-white pea flowers; a sand-stabilizing native.",
    "Abronia umbellata": "Trailing dune annual/perennial with fragrant pink ball-shaped flower clusters; a beach-strand specialist.",
    "Solidago spathulata": "Compact goldenrod with dense spikes of small yellow flowers; blooms late into fall on dunes and bluffs.",
    "Camissoniopsis cheiranthifolia": "Low silver-gray dune mat with small yellow four-petaled flowers (beach evening primrose); a strand pioneer.",
    "Salvia mellifera": "Aromatic chaparral shrub (black sage) with pale lavender flower whorls stacked along the stems.",
    "Dendromecon rigida": "Stiff evergreen chaparral shrub (bush poppy) with bright yellow poppy flowers; a fast post-fire bloomer.",
    "Ceanothus thyrsiflorus var. griseus": "Dense evergreen shrub (Carmel ceanothus) covered in pale-blue flower clusters in spring.",
    "Arctostaphylos glauca": "Large manzanita with smooth red bark and urn-shaped pink-white flowers; a winter-blooming chaparral shrub.",
    "Adenostoma fasciculatum": "Wiry needle-leaved chaparral shrub (chamise) with frothy cream flower sprays; the dominant chaparral plant.",
    "Salvia spathacea": "Spreading perennial (hummingbird sage) with tall magenta flower whorls; grows in shady oak woodland.",
    "Iris douglasiana": "Clumping perennial (Douglas iris) with pale-blue to purple flowers; favors grassy openings and forest edges.",
    "Frangula californica": "Evergreen shrub (California coffeeberry) with inconspicuous greenish flowers and berries ripening red to black.",
    "Quercus agrifolia": "Spreading evergreen coast live oak with holly-like leaves; the keystone canopy of local oak woodland.",
    "Heteromeles arbutifolia": "Evergreen shrub (toyon) with creamy summer flower clusters and bright red winter berries.",
    "Aquilegia formosa": "Nodding perennial (western columbine) with spurred red-and-yellow flowers; found along shaded streams.",
    "Erythranthe guttata": "Sprawling yellow-flowered seep monkeyflower of wet seeps and stream edges.",
    "Lonicera involucrata var. ledebourii": "Riparian shrub (coast twinberry) with paired yellow tubular flowers and dark berries in red bracts.",
    "Eschscholzia californica": "The California poppy: silky orange cup-shaped flowers over blue-green foliage; a grassland and roadside staple.",
    "Lupinus succulentus": "Robust annual (arroyo lupine) with deep blue-purple flower spikes; carpets grassland after wet winters.",
    "Sidalcea malviflora": "Perennial (checkerbloom) with pink hollyhock-like flowers on slender stalks in coastal grassland.",
    "Sisyrinchium bellum": "Grass-like perennial (blue-eyed grass) with small blue-purple yellow-centered flowers in spring meadows.",
    "Salvia columbariae": "Annual (chia) with spiny blue flower clusters stacked on square stems; a dry slope and disturbed-ground native.",
    "Garrya elliptica": "Evergreen shrub (coast silk tassel) with long dangling gray-green catkins; a notable winter bloomer.",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "trailside-eval-research"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def extract_communities(raw_text):
    txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw_text)))
    m = re.search(r"Communities\s*:?\s*(.*?)(?:Loading images|Elevation|Notes|Sources|External links|California Native Status|$)", txt)
    raw = m.group(1).strip(" ,") if m else ""
    items = [c.strip() for c in raw.split(",") if c.strip()]
    # Keep only recognized community names; drop free-text like "many plant communities".
    return [c for c in items if c in COMMUNITY_MAP]


def map_habitats(communities):
    habs = []
    for c in communities:
        h = COMMUNITY_MAP.get(c)
        if h and h not in habs:
            habs.append(h)
    return habs


def main():
    src = {p["scientific_name"]: p for p in json.loads(PLANTS.read_text())}
    out = []
    for sci in FIXED_SET:
        p = src[sci]
        comms = extract_communities(fetch(p["calflora_url"]))
        habs = map_habitats(comms)
        override = CURATOR_OVERRIDES.get(sci)
        habitat_source = "calflora"
        curator_note = None
        if override:
            for h in override["add"]:
                if h not in habs:
                    habs.append(h)
            habitat_source = "calflora+curator"
            curator_note = override["reason"]
        rec = {
            "common_name": p["common_name"],
            "scientific_name": sci,
            "growth_habit": p["growth_habit"],
            "native": True,
            "bloom_months": p["bloom_months"],
            "habitat": habs,
            "habitat_source": habitat_source,
            "habitat_raw": comms,
            "description": DESCRIPTIONS[sci],
            "calflora_url": p["calflora_url"],
            "calscape_url": p["calscape_url"],
            "photo_url": p["photo_url"],
            "photo_attribution": p["photo_attribution"],
        }
        if curator_note:
            rec["curator_note"] = curator_note
        out.append(rec)
        flag = " [curator]" if override else ""
        print(f"{p['common_name'][:28]:28} -> {habs}{flag}")
        time.sleep(0.4)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(out)} plants to {OUT.relative_to(ROOT)}")
    # Sanity: flag any plant that mapped to zero habitats.
    empty = [r["common_name"] for r in out if not r["habitat"]]
    if empty:
        print("WARNING: zero-habitat plants (review mapping):", empty)


if __name__ == "__main__":
    main()
