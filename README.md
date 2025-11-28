# centris-ca-scrape
[Centris.ca](https://www.centris.ca/) is a Canadian real-estate listing website.
This project scrapes rental properties (default Montreal filters) and prepares a
mission folder for every crawl so that listings, photos, and AI analyses stay
linked forever.

#### Scraped data includes:
- Category
- Description
- Full address
- Features (rooms, beds, baths)
- Price (rent per month)
- Additional features
- URL of the property

The original upstream repo stored data in CSVs – that legacy file is still kept
in [`centris_scrape/listings.csv`](https://github.com/harshhes/centris-ca-scrape/blob/main/centris_scrape/listings.csv).

## Mission outputs

Running `scrapy crawl listings` now spins up a mission under
`missions/<mission-id>/` (the ID includes the timestamp plus an optional clue
slug). Each mission is self-contained:

```
missions/<mission-id>/
├── config/
│   └── mission.json           # clue + crawl parameters
├── data/
│   ├── listings.json          # filtered listings (default max_matches = 3)
│   └── listings_raw.jsonl     # raw newline-delimited feed of every emitted item
├── media/<listing_id>/...     # original photos grouped per listing
├── analysis/                  # AI/vision outputs land here
└── logs/crawl.log             # spider log for this mission
```

`listing_id`, `image_folder`, and `image_files` inside `data/listings.json` are
relative to the mission root, so you can move or archive the directory without
breaking links. If you still want an additional Scrapy feed, simply pass `-O`
when running the spider.

## Crawl configuration

Default knobs live in `config/crawl_defaults.json`. The spider reads this file
at startup, so you can change `max_matches` (currently 100) or add new keys
without touching code. Any argument you pass via Scrapy (for example
`-a max_matches=25`) still overrides the config file.

Common overrides you can pass on the command line:

- `rent_price_min`, `rent_price_max`
- `living_area_min`, `living_area_max`
- `land_area_min`, `land_area_max`
- `year_construction_min`, `year_construction_max`
- `city_id` (Centris geography ID; omit to search all cities)

Example:

```
python -m scrapy crawl listings ^
    -a mission_clue="duck near downtown" ^
    -a city_id=347 ^
    -a rent_price_max=5000
```

## Inspecting a single image with ChatGPT Vision or Ollama

1. Copy `.env.example` to `.env`.
   - For ChatGPT, set `OPENAI_API_KEY`.
   - For Ollama, keep (or change) `OLLAMA_HOST` and install a vision model such
     as `llava` via `ollama pull llava`.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run the helper:
   - ChatGPT (default): `python scripts/tools/analyze_image.py path/to/image.jpg`
   - Ollama: `python scripts/tools/analyze_image.py path/to/image.jpg --backend ollama --model llava`

The helper automatically resizes photos to ≤512×512 to keep vision costs low,
uploads them to the selected backend, and prints the response. Use `--prompt`
to ask a different question or `--model` to try another vision-capable model.

## Describing full missions

To describe the images for the first three listings of the most recent mission
and save the results under `analysis/`:

```
python scripts/tools/describe_run.py --backend ollama --model llava
```

This creates `missions/<mission-id>/analysis/listings_with_descriptions.json`
with an `image_descriptions` array per listing. Use `--mission <mission-id>`
(the legacy `--run` flag still works) to target a specific mission or pass
`--backend chatgpt` if you prefer the hosted API.

## Harvesting city IDs

Use `scripts/tools/city_lookup.py` to query the live Centris UI for geography
suggestions and capture their IDs:

```
python scripts/tools/city_lookup.py --terms mont,lav,quebec --output cities.json
```

The script starts an undetected Chrome session, calls the same suggestion API
the site uses (defaulting to `MatchType=CityDistrict`), and writes a JSON file
containing the unique IDs and labels so you can plug them back into
`-a city_id=<value>` or your clue logic.

If you just need the calculator dataset (which returns `{ "Id": "...", "Name": "..." }`
pairs), run:

```
python scripts/tools/get_city_ids.py --filters mont,lav,ste --output city_ids.json
```

This script opens a stealth Chrome window, posts to
`/api/calculator/GetCitiesForQc`, and captures the JSON payload so you can reuse
the IDs later without staying connected to the site.

## AI mission planner

Let an LLM translate mission clues into concrete crawl parameters and launch the
spider in one shot:

```
python scripts/tools/plan_mission.py "Find the inflatable duck near downtown"
```

What happens:
- The planner feeds the clue, `config/field_value_catalog.json`, and the top
  Québec cities (from `config/cities_qc.json`) into the selected LLM
  (defaults to Ollama `qwen3:8b`, override via `--model` or `--backend`). The
  planner warms the model with a short prompt unless you pass `--no-warmup`.
- The LLM responds with JSON containing `city_name`, field/filter keys, and
  numeric overrides. Manual flags such as `--city-name`, `--include-fields`, or
  `--rent-price-max` always win over the AI suggestion.
- The planner prints the resolved parameters, writes a copy to
  `missions/_planner_logs/<timestamp>.json`, and then shells out to
  `scrapy crawl listings` with all the inferred `-a` arguments. Pass `--dry-run`
  to skip the final crawl if you only want the plan.

Use `--preset`, `--mission-id`, or any of the numeric overrides (rent, living
area, land area, year, `max_matches`) to pin those values yourself. The spider
still records the clue, overrides, and city-resolution status inside the mission
folder exactly as it would for a manually-launched run.

If your local model needs longer to respond, bump `--llm-timeout` (seconds, default 600) so
the planner waits long enough for the Ollama request to finish.

Need a richer pre-prompt that references prior missions before sending anything
to the LLM? Use:

```
python scripts/tools/build_mission_question.py \
    "Fjord, whales, confluence" --history 5 --output mission_prompt.txt
```

This inspects the latest missions (up to `--history` entries), summarizes the
clues, cities, overrides, and listing counts, then writes a question block you
can paste into ChatGPT/Ollama to reason about the next move.

### Replaying an existing mission

To run the spider again with the **exact** parameters captured in an older
mission’s `config/mission.json`:

```
python scripts/tools/rerun_mission.py 20251112_203851_fjord-whales --dry-run
python scripts/tools/rerun_mission.py 20251112_203851_fjord-whales
```

The first command shows the reconstructed `scrapy` invocation; the second
actually launches it (creating a brand-new mission folder with the same clue,
fields, overrides, city settings, etc.). Pass `--clue` or `--mission-id` if you
want to tweak the rerun’s metadata.

### Running a stored planner log

If you only captured a planner proposal (no mission yet) you can run it later:

```
python scripts/tools/run_planner_log.py 20251112_203851_universitieslakesestrie --dry-run
python scripts/tools/run_planner_log.py 20251112_203851_universitieslakesestrie
```

The helper reads `missions/_planner_logs/<id>.json`, rebuilds the recorded
Scrapy command, and either prints it (`--dry-run`) or launches the crawler to
produce a brand-new mission directory. Use `--clue` or `--mission-id` to adjust
those fields before execution.

### Interactive mission menu

When you just want a simple menu to do everything (plan, run planner logs,
rerun existing missions, or delete old artifacts), run:

```
python scripts/mission_menu.py
```

The menu guides you through each action, and you can opt into dry-runs before
anything executes.

> **Tip:** `prompt_toolkit` powers the arrow-key menus. It installs automatically
> via `pip install -r requirements.txt`. If you skip that dependency, the menu
> falls back to simple number prompts.

## Manual / existing browser sessions

Cloudflare behaves better when you pass its challenges manually. You can now do
that without reworking any scripts:

1. **Attach to your own Chrome session**
   - Start Chrome yourself with a debugging port, e.g.
     `chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\temp\centris-profile`
   - Solve the Cloudflare challenge in that window.
   - Set `CHROME_DEBUGGER_ADDRESS=127.0.0.1:9222` (or `SELENIUM_DEBUGGER_ADDRESS`)
     in your environment before running `python scripts/mission_menu.py`.
   - The middleware will connect to that browser instead of launching a new one,
     so your solved session (and cookies) carry over.

2. **Launch via the crawler but pause for manual solving**
   - Set `SELENIUM_WAIT_FOR_USER=1` in your environment.
   - Every mission will open Chrome, print a prompt, and wait for you to finish
     any human challenges. Press Enter once you’re past Cloudflare and the
     crawler resumes automatically.

Leave both variables unset to keep the fully automated behavior.

## Harvesting city IDs automatically

You can attempt to capture Centris `CityDistrict` IDs (with all of the
anti-bot caveats) by launching a stealth Chrome session that hits the same
autocomplete endpoint the website uses:

```
python scripts/tools/harvest_city_ids.py --limit 3
```

- By default the script walks through `config/cities_qc.json` and fills in
  entries that are missing from `config/city_cache.json`.
- Use `--city "Montréal, Québec"` to target specific names, or `--headless`
  to run without opening a visible browser window.
- Every successful lookup is appended to `config/city_cache.json`, so the
  planner and crawler immediately benefit.

Cloudflare can still block these calls; the script automatically refreshes the
session and retries, but you may need to rerun it (or fall back to manual
DevTools capture) if the endpoint remains unavailable.

### Quick Chrome helper

Need a debug-enabled Chrome? Use the small helper:

```
python scripts/browser_helper.py
```

It can launch Chrome with `--remote-debugging-port` (default 9222), or show the
status of an existing debugging endpoint so you know which address to feed into
mission menu option 6.

## City cache & failure fallback

The spider now accepts either a numeric `city_id` **or** a `city_name`:

```
python -m scrapy crawl listings -a city_name="Montréal"
```

- When `city_id` is provided (via CLI or `config/crawl_defaults.json`), that ID
  is used directly. If you also pass `city_name`, the pair is saved into
  `config/city_cache.json` for future missions.
- When only `city_name` is supplied, the spider looks up the ID inside
  `config/city_cache.json`. The cache stores normalized keys, for example:

```json
{
  "montreal": { "name": "Montréal", "id": 5 },
  "quebec": { "name": "Québec (Ville)", "id": 641 }
}
```

- If the name is not present (for example because Cloudflare blocked the
  autocomplete endpoint), the spider logs a clear warning, writes
  `missions/<id>/analysis/city_resolution.json` with the missing city, and
  continues the crawl **without** a city filter (brute force). At that point
  you can manually capture the Centris ID (DevTools →
  `Property/GetSearchAutoCompleteData`) and add it to the cache before the next
  run.

The mission planner also consults this cache, so any clue that resolves to a
known city automatically reuses the stored ID instead of relying on LLM guesses.
If the planner picks a city that isn’t yet cached, it prompts you to enter the
Centris `CityDistrict` ID and immediately writes it to `config/city_cache.json`
for future runs.

## Field override catalog

AI clue solvers (or manual operators) often need to know which Centris enum
values are already wired into the spider. The file
`config/field_value_catalog.json` is generated straight from
`FIELD_REGISTRY` and lists every key you can pass through `include_fields`
along with the underlying `fieldId`, `value`, and condition metadata.

The catalog currently covers:
- `Category` and `SellingType` (Rent vs Sale)
- `PropertyType` (commercial/residential codes, including the new ones such as
  `property_type_multi_family`, `property_type_sale_industrial`, etc.)
- `AccommodationType`, `OperationType`, `Zoning`, and `ActivityArea`

Use it as the source of truth for AI hinting logic or to validate that a clue
maps to an existing override before launching a mission.

## Québec city catalog

If you only need a list of Québec populated places (for clue generation or
matching) without hitting Centris, drop the GeoNames `CA.txt` dump in the repo
root (already tracked in this workspace) and run:

```
python scripts/tools/build_city_catalog.py
```

This filters the GeoNames dataset to `featureClass = "P"` and `admin1 = "10"`
(Québec), then writes `config/cities_qc.json` sorted by population. Pass
`--min-population`, `--province`, or `--output` to customize the selection.
Each entry stores the GeoNames ID, the canonical French name, lat/lon,
population, admin codes, and timezone so the AI can reason about possible
matches even before Centris IDs are known.
