# What's Blooming

A simple static site showing which California native plants are currently blooming
in the Monterey, CA area. Pick a month with the slider to see how the list changes
through the year.

## How it works

- **Frontend** — plain HTML/CSS/JS, no build step. [`index.html`](index.html) loads
  [`data/plants.json`](data/plants.json) and renders a card for each plant whose
  bloom months include the selected month.
- **Data** — `data/plants.json` is the committed source of truth. Each record has a
  common/scientific name, family, growth habit, 1-indexed `bloom_months`, links to
  Calflora and Calscape, and a Calflora photo with attribution.
- **Data pipeline** — [`scripts/collect_data.py`](scripts/collect_data.py) pulls the
  native plant list for a Calflora saved polygon (default shape id `rs3899`,
  covering the Monterey area) and writes `plants.json`. No API key required.

## Running locally

It's a static site, so serve the directory with any HTTP server (needed for the
`fetch` of the JSON to work):

```bash
python -m http.server 8000
# then open http://localhost:8000
```

## Refreshing plant data

```bash
python scripts/collect_data.py --existing data/plants.json --output data/plants.json
```

This also runs automatically via the
[Refresh Plant Data](.github/workflows/refresh-data.yml) GitHub Action — quarterly
(Jan/Apr/Jul/Oct) and on manual dispatch — committing any changes to `plants.json`.

## Credits

Plant data and photos from [Calflora](https://www.calflora.org), with links to
[Calscape](https://calscape.org). Photos courtesy of their respective contributors.
