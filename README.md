# jpy-mtg-prices

A personal price tracker for Magic: The Gathering singles priced in JPY,
sourced from Hareruya's own product search endpoints. Think "ManaBox, but
for Japanese market prices."

## Status

Early scaffold. Working: set discovery, rate-limited crawling, parsing,
tiered scheduling, storage. Not yet built: Scryfall identity matching and
an API/frontend to actually browse the data.

## Source of truth

**Scryfall is the source of truth for card identity.** `printings`
rows are created only from Scryfall's bulk data export
(`scraper/sync_scryfall.py`) — set, collector number, name, rarity,
Scryfall id/images. Hareruya is used *only* to update the `prices`
table against printings that already exist; the crawler never creates
a printing from Hareruya data. If a Hareruya listing doesn't match an
existing printing (wrong set mapping, a genuinely new set not yet
synced from Scryfall, a numbering mismatch), that price observation is
logged and dropped rather than guessed into a new row.

This means the setup order matters:

1. `sync_sets.py` — pulls Hareruya's set list, gives you `cardset` ids
   and `product` codes.
2. `sync_scryfall.py` — resolves each set's Scryfall set code from its
   Hareruya product code, then populates `printings` from Scryfall's
   bulk data for every matched set.
3. `crawl.py` / `daily_run.py` — crawls Hareruya prices and attaches
   them to the printings created in step 2.

Running the price crawler before syncing Scryfall for a given set
means every doc in that set fails to match and nothing gets written —
`crawl.py` logs this loudly rather than failing silently.

### Collector number normalization

Hareruya zero-pads collector numbers in its product names (`"(099)"`),
Scryfall does not (`"99"`). Since Scryfall printings are the join
target, `scraper/parse.py` strips leading zeros from whatever Hareruya
gives us (`normalize_collector_number`) before any lookup happens.
Numeric-with-suffix numbers (`"099a"` → `"99a"`) are handled the same
way. If a set's numbering doesn't follow this pattern, matches for
that set will silently fail rather than blow up — check the crawl logs
for unmatched-doc warnings.

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
  sync_scryfall.py         # Scryfall bulk data -> printings table (identity source of truth)
  sync_all.py              # convenience: runs sync_sets + sync_scryfall in one command
  tiering.py               # hot/warm/cold assignment + today's crawl list
  crawl.py                 # crawl Hareruya prices, attach to existing printings
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

**Quick start** — syncs sets and printings in one command (do this
first, and again whenever new sets are released; weekly is plenty):

```bash
python -m scraper.sync_all
```

That's `sync_sets` (Hareruya's set list) followed by `sync_scryfall`
(resolves Scryfall set codes, then populates `printings` from
Scryfall's bulk data). Check the logs for sets that couldn't be
auto-mapped (`no direct match`) — those need a manual
`scryfall_set_code` set by hand before their printings will populate.
The Scryfall download is sizeable (several hundred MB); expect the
first run to take a few minutes.

If you'd rather run the two steps separately (e.g. to re-sync sets
without re-downloading Scryfall's bulk data):

```bash
python -m scraper.sync_sets       # sets table only
python -m scraper.sync_scryfall   # printings table only
```

Once sets/printings are synced, **crawl prices** for one set manually,
by its Hareruya `cardset` id (find it via the `sets` table, or from a
`cardset=` query param on the site):

```bash
python -m scraper.crawl 426   # e.g. 426 = Hobbit (HOB)
```

**Run the full tiered daily crawl** (intended to be invoked by cron
/ systemd timer once a day):

```bash
python -m scraper.daily_run
```

## Data model

- **`sets`** — one row per Hareruya `cardset`. Carries the Japanese
  name, release date, assigned tier, and the matching Scryfall set
  code (resolved by `sync_scryfall.resolve_scryfall_set_codes`).
- **`printings`** — one row per `(set, collector_number)`, created
  *only* from Scryfall's bulk data. Carries `scryfall_id`, name,
  rarity — the identity fields Hareruya's crawler matches against but
  never writes.
- **`prices`** — append-only log of price observations, one row per
  crawl per `(printing, language)`. Includes `stock` and
  `weekly_sales`, which are useful signals for spotting movement beyond
  the release-date tiering alone if you want to refine scheduling
  later.

## Not yet built

- **API layer.** A thin FastAPI app serving the local DB (never hits
  Hareruya on a user request — only the scheduled crawl does).
- **Foil prices.** The crawler currently defaults to non-foil only
  (`foil_flg=[0]`) to keep initial scope small; foil is a straightforward
  second pass once the base pipeline is validated.
- **Manual set-code overrides.** Sets that don't auto-resolve against
  Scryfall (Booster Fun variants, retro frames, a handful of older
  products) currently need their `scryfall_set_code` set by hand;
  there's no override file/table yet, just direct DB edits.
