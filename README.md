# jpy-mtg-prices

A personal price tracker for Magic: The Gathering singles priced in JPY,
sourced from Hareruya's own product search endpoints. Think "ManaBox, but
for Japanese market prices."

## Status

Early scaffold. Working: set discovery, rate-limited crawling, parsing,
tiered scheduling, storage. Not yet built: Scryfall identity matching and
an API/frontend to actually browse the data.

## How it works

Hareruya's storefront calls two endpoints when you filter its product
search:

1. `GET /ja/products/search/unisearch/query?<human filters>` — takes
   filters like `cardset`, `rarity[]`, `foilFlg[]`, `stock` and returns
   `{"message": "<fq=...&sort=...&rows=...&page=...>"}`.
2. `GET /ja/products/search/unisearch_api?<that message>` — runs the
   resolved query and returns the actual product/price JSON.

`scraper/hareruya_client.py` wraps both calls behind one rate-limited
client. A crawl of a set always does both steps for every page; nothing
is cached or replayed independently.

Set discovery comes from Hareruya's own navigation file,
`https://www.hareruyamtg.com/user_data/list/sideMenuList.json` — the
same JSON its own set-picker UI reads. `scraper/sync_sets.py` flattens
that tree into the `sets` table, extracting each set's `cardset` id,
`product=[XXX]` code (used later to join against Scryfall), Japanese
name, and release date where available.

## Why it's slow on purpose

This hits an undocumented, first-party endpoint — not a public API.
Everything here is built to be a slow, cache-friendly, low-volume
crawler rather than a fast one:

- **One request at a time.** `RateLimiter` enforces a minimum delay
  (default 45s) between every outbound request, globally across a
  crawl run — never issued concurrently.
- **Tiered, not exhaustive.** Sets are bucketed `hot` / `warm` / `cold`
  by release recency (`scraper/tiering.py`). Hot sets (released in the
  last 60 days) are crawled daily; warm sets (last year) rotate through
  roughly once a week; everything else rotates once a month. The
  rotation bucket is derived from each set's id so the same sets fall
  on the same day rather than reshuffling randomly.
- **Append-only price history.** `prices` is a log, not a
  single-row-per-printing table — storage is cheap, and it means price
  history charts are just a query away later with zero schema changes.

If you're adapting this yourself: raise `min_interval_seconds` rather
than lowering it, and don't parallelize the crawl. See the code
comments in `hareruya_client.py` and `tiering.py` for the reasoning
behind the specific numbers chosen.

## Project layout

```
models.py                  # SQLAlchemy models: Set, Printing, Price
db.py                      # engine/session setup (reads DATABASE_URL)
scraper/
  hareruya_client.py       # rate-limited /query -> /unisearch_api client
  parse.py                 # raw doc -> ParsedDoc (collector number, price, etc.)
  sync_sets.py             # sideMenuList.json -> sets table
  tiering.py               # hot/warm/cold assignment + today's crawl list
  crawl.py                 # crawl a set, upsert printings/prices
  daily_run.py             # daily entrypoint: retier -> pick sets -> crawl
requirements.txt
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=postgresql+psycopg://localhost/jpy_mtg_prices
python db.py                      # creates tables
```

## Usage

Sync the sets table (run occasionally — weekly is plenty, new sets
don't appear often):

```bash
python -c "
import asyncio
from db import SessionLocal
from scraper.sync_sets import run

with SessionLocal() as session:
    asyncio.run(run(session))
"
```

Crawl one set manually, by its Hareruya `cardset` id (find it via the
`sets` table after syncing, or from a `cardset=` query param on the
site):

```bash
python -m scraper.crawl 426   # e.g. 426 = Hobbit (HOB)
```

Run the full tiered daily crawl (intended to be invoked by cron /
systemd timer once a day):

```bash
python -m scraper.daily_run
```

## Data model

- **`sets`** — one row per Hareruya `cardset`. Carries the Japanese
  name, release date, assigned tier, and (once wired up) the matching
  Scryfall set code.
- **`printings`** — one row per `(set, collector_number)`. Collector
  number is parsed out of the leading `"(123)"` in Hareruya's
  `product_name` field, since it isn't a dedicated field in the API
  response.
- **`prices`** — append-only log of price observations, one row per
  crawl per `(printing, language)`. Includes `stock` and
  `weekly_sales`, which are useful signals for spotting movement beyond
  the release-date tiering alone if you want to refine scheduling
  later.

## Not yet built

- **Scryfall join.** Match `printings` to Scryfall's bulk data dump
  (free daily JSON export) on `(scryfall_set_code, collector_number)`
  to backfill `scryfall_id`, card images, and oracle text. The
  `product=[XXX]` code captured in `sets.hareruya_product_code` is
  intended as the join key against Scryfall's set codes, though a few
  sets (Booster Fun variants, retro-frame sets, etc.) may need manual
  mapping — spot-check before trusting it blindly.
- **API layer.** A thin FastAPI app serving the local DB (never hits
  Hareruya on a user request — only the scheduled crawl does).
- **Foil prices.** The crawler currently defaults to non-foil only
  (`foil_flg=[0]`) to keep initial scope small; foil is a straightforward
  second pass once the base pipeline is validated.
