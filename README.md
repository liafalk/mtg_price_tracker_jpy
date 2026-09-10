# jpy-mtg-prices

A personal price tracker for Magic: The Gathering singles priced in JPY,
sourced from Hareruya's own product search endpoints. Think "ManaBox, but
for Japanese market prices."

## Status

Working: set discovery, rate-limited crawling, parsing, tiered
scheduling, storage, Scryfall identity matching, and the SvelteKit
frontend (in `web/`) for browsing the data — including a production
build served via Docker.

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

### Manual set-code overrides

Not every Hareruya set auto-resolves to a Scryfall set code (see the
`X sets need manual scryfall_set_code mapping` warning). Rather than
editing the DB by hand, add entries to `config/set_code_overrides.toml`:

```toml
"10ED" = "10e"
```

Keys are Hareruya's `product` code exactly as stored in
`sets.hareruya_product_code`; values are the Scryfall set code, which
you can look up at [scryfall.com/sets](https://scryfall.com/sets) or
`https://api.scryfall.com/sets`. Overrides always take precedence over
the automatic guess — including fixing a wrong automatic match, not
just filling gaps — and `resolve_scryfall_set_codes` (part of every
`sync_all`/`sync_scryfall` run) picks them up automatically; no code
changes needed. Get the value wrong and prices silently attach to the
wrong set, so verify before adding — leaving an entry unresolved (or
commented out, as the shipped file does for anything unverified) is
safer than guessing.

A few entries are pre-filled and verified (`10ED`, `CE`, `IE`); the
rest are commented-out placeholders for the sets that showed up
unresolved in testing — check them against Scryfall before
uncommenting. Some (`3EDBB`, `BRO-Retro`, `MH1-RT`) may not be simple
one-code mappings at all — border color / retro frame might be a
per-card attribute within the base set rather than its own Scryfall
set, similar to the Booster Fun situation below — worth confirming
card-by-card rather than assuming a single override code covers it.

A value can also be a list of Scryfall codes, for the rarer case where
one Hareruya product genuinely spans multiple *distinct* Scryfall sets
(not variants of one set — that's Booster Fun's job, see below):

```toml
"MB1+The list" = ["mb1", "plst"]
```

`MB1+The list` ("Mystery Booster & The List" on Hareruya) is exactly
this case — Mystery Booster packs also contain The List insert cards,
so Hareruya sells them as one browsable product, but Scryfall tracks
`mb1` and `plst` as two unrelated sets. Every code in the list routes
back to the same local `Set` row when matching prices to printings
(`sync_printings` → `_build_set_resolver`), while the DB's single
`scryfall_set_code` column just stores the first one for display.

Two open caveats on this specific set, worth knowing before trusting
its price data:

- **`The List` is also its own separate Hareruya listing**, queried
  via `category=248` rather than `cardset=` — a different query
  pattern this scraper doesn't support at all yet (see below). The
  override above only covers List cards priced as part of the combined
  MB1+List product, not the standalone listing.
- **`The List`'s Scryfall collector numbers are compound** (e.g.
  `ME4-102`, `TD0-A80`), not plain integers. Whether Hareruya formats
  these the same way in `product_name` — such that
  `scraper/parse.py`'s extraction regex (which currently only matches
  `(\d+)`, pure digits) can pull them out — is unverified. Check crawl
  logs for unmatched-doc warnings on this set before trusting it.

### `category=` products (not yet supported)

Hareruya has two different query patterns in its own navigation JSON:
most sets use `cardset=<id>` (what this scraper is built around), but
promos, Secret Lair drops, Duel Decks, standalone "The List", and a
long tail of other groupings use `category=<id>` instead — a
structurally different endpoint. `sync_sets.py` currently only
extracts `cardset=` nodes from `sideMenuList.json`; `category=`-only
nodes are silently dropped, and `hareruya_client.py`'s filter builder
has no way to construct a `category=` request at all. If you need
pricing for anything that only exists as a `category=` listing, that's
a real gap, not a config issue — it needs the client and set-sync
logic extended to handle a second query shape, which hasn't been
scoped or tested here yet.

### Scryfall bulk data format

Scryfall changed their bulk-data format in July 2026: files are now
gzip-compressed JSONL (one JSON object per line) served via a
`jsonl_download_uri` field, replacing the old single-JSON-array
`download_uri` (fully retired July 20, 2026). `sync_scryfall.py`
handles both shapes (`_parse_bulk_body`), preferring `jsonl_download_uri`
when present and falling back to `download_uri` otherwise, so a future
format change is less likely to break this outright -- but if
`sync_scryfall` ever throws a `KeyError`/`ValueError` around bulk data
again, this is the first place to look: check what
`https://api.scryfall.com/bulk-data` actually returns now and compare
against what this code expects.

### Booster Fun ("-BF") sets

Hareruya sells showcase/extended-art/borderless variants as a
separate product line with its own `cardset` id — e.g. `HOB` (base
set) and `HOB-BF` (Booster Fun) are two different Hareruya sets.
Scryfall doesn't work that way: it has no separate set code for these
treatments, they're catalogued inside the *base* set and distinguished
by `promo_types` containing `"boosterfun"` (confirmed by Scryfall's
own `is:boosterfun` search filter, e.g. `set:eld is:boosterfun`).

So `sync_scryfall.py` resolves a `-BF` Hareruya set to the *same*
`scryfall_set_code` as its base set (stripping the suffix before
matching), rather than looking for a `hob-bf` that doesn't exist. That
means two local `Set` rows legitimately share one Scryfall code —
`sync_printings` handles this by checking each card's `promo_types`:
boosterfun-tagged cards are assigned to the local `-BF` set, everything
else to the base set. If only one of the two local sets is actually
tracked (e.g. you never synced the `-BF` product from Hareruya), all
matching cards fall back to whichever one exists.

This same base-set-sharing behavior likely applies to other Hareruya
suffix conventions (e.g. `-Retro` for retro-frame sets) — not yet
handled, since retro frames use a different Scryfall mechanism
(frame/border metadata, not `promo_types`) that hasn't been verified
here. Sets like that will currently show up as unresolved in
`resolve_scryfall_set_codes` logs rather than being silently
mismatched.

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

## Production deployment notes

For a real server, run Postgres in Docker and back it up outside the container. The repo already uses a named volume in [docker-compose.yml](docker-compose.yml), but a Docker volume is not a backup strategy on its own.

### Recommended backup flow

- Keep the live DB in the `db_data` volume
- Run `scripts/backup_db.sh` on a schedule; it uses a dedicated PostgreSQL
  backup container and produces compressed custom-format archives
- Store backups on the host at `/var/backups/jpy-mtg` by setting `BACKUP_DIR`
- Keep the last 14 days of compressed dumps

Example:

```bash
chmod +x scripts/backup_db.sh scripts/restore_db.sh
sudo mkdir -p /var/backups/jpy-mtg
sudo chown $USER /var/backups/jpy-mtg
BACKUP_DIR=/var/backups/jpy-mtg ./scripts/backup_db.sh
```

Then add a cron entry:

```cron
0 */6 * * * BACKUP_DIR=/var/backups/jpy-mtg /path/to/jpy-mtg-prices/scripts/backup_db.sh >> /var/log/jpy-mtg-backup.log 2>&1
```

### Restore

```bash
BACKUP_DIR=/var/backups/jpy-mtg ./scripts/restore_db.sh /var/backups/jpy-mtg/jpy_mtg_prices-20260830T020000Z.dump
```

### Production environment

Use a real `.env` file instead of hard-coded secrets. Keep the DB and app separated by Docker networking, expose only the web port, and keep the database port closed to the public unless you specifically need direct access.

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
  full_run.py              # one-off full crawl of every tracked set
config/
  set_code_overrides.toml  # manual Hareruya -> Scryfall set code overrides
api/
  main.py                  # FastAPI app: /api/* JSON endpoints (sets, search, prices, ...)
web/                       # SvelteKit frontend (TypeScript, Svelte 5)
  src/routes/              # home, /search, /card/[set]/[number]
  src/lib/                 # api client, i18n, shared components, global styles
  Dockerfile               # multi-stage build, serves `node build`
scripts/
  backup_db.sh             # pg_dump via the `backup` compose service
  restore_db.sh            # restore a dump into the running DB
  migrate_legacy_schema.py # one-time migration (see Data model below)
scanner/                   # experimental card scanner (see scanner/README.md)
tests/                     # API endpoint tests
backups/                   # local backup dumps (default BACKUP_DIR)
requirements.txt
docker-compose.yml         # Postgres + app + web + frontend containers (see Setup below)
Dockerfile
```

## Setup

You need a Postgres server reachable at `DATABASE_URL` — nothing here
runs one for you automatically. Two ways to get one:

### Option A: Docker Compose (recommended)

Starts Postgres (with a persistent volume) and an `app` container
with dependencies pre-installed, on one network:

```bash
docker compose up -d db          # just the database
python db.py                     # or: docker compose run --rm app python db.py
```

Then run any script through the `app` service so it shares the
container network and `DATABASE_URL` automatically:

```bash
docker compose run --rm app python -m scraper.sync_all
docker compose run --rm app python -m scraper.crawl 426
docker compose run --rm app python -m scraper.daily_run
```

Postgres is also exposed on `localhost:5432` (user/pass/db all
`jpy_mtg` / `jpy_mtg` / `jpy_mtg_prices` — change these in
`docker-compose.yml` before running this for real) if you'd rather run
the Python scripts on the host against the containerized DB. There's
also an [Adminer](https://www.adminer.org/) UI at `localhost:8081` if
you want to browse the tables without a DB client installed.

To schedule the daily crawl, point cron/systemd at `docker compose run`
from the host, e.g. a crontab entry like:

```
0 3 * * * cd /path/to/jpy-mtg-prices && docker compose run --rm app python -m scraper.daily_run
```

### Option B: Local Postgres + venv

If you already have Postgres running somewhere:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=postgresql+psycopg://localhost/jpy_mtg_prices
python db.py                      # creates tables
```

### Frontend (SvelteKit)

The frontend lives in `web/` (SvelteKit + TypeScript + Svelte 5). It
calls the FastAPI `/api/*` endpoints and needs no database access of
its own.

**Development** — run the API and the frontend separately; the Vite dev
server proxies `/api/*` to `localhost:8000`:

```bash
uvicorn api.main:app --port 8000        # terminal 1
cd web && npm install && npm run dev    # terminal 2 -> http://localhost:5173
```

**Docker** — `docker compose up -d frontend` builds and serves the
production build on `http://localhost:5173`. The frontend is a
standalone Node server (via `@sveltejs/adapter-node`); it calls the
API from the browser, so the backend URL is baked in at build time via
the `PUBLIC_API_BASE` build arg (set to `http://localhost:8000` in
`docker-compose.yml`, since the browser reaches the API through the
host-mapped port). The API has CORS enabled to allow these cross-origin
calls.

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

### Migrate an existing database

After updating from the commit that stored Hareruya cardsets directly in
`sets`, run the one-time migration below. It is transactional and safe to
rerun; it preserves `printings` and `prices`.

```bash
python -m scripts.migrate_legacy_schema
```

With Docker Compose:

```bash
docker compose run --rm app python -m scripts.migrate_legacy_schema
```

Rows without a resolved `set_code` remain in `sets_hareruya` with a null
`scryfall_set_code`; run the normal Scryfall synchronization after adding any
needed entries to `config/set_code_overrides.toml`.

- **`sets`** — canonical Scryfall set metadata, keyed by Scryfall code.
- **`sets_hareruya`** — one row per Hareruya `cardset`. Carries the Japanese
  name, release date, assigned tier, and the matching Scryfall set code
  (resolved by `sync_scryfall.resolve_scryfall_set_codes`).
- **`printings`** — one row per `(set, collector_number)`, created
  *only* from Scryfall's bulk data. Carries `scryfall_id`, name,
  rarity — the identity fields Hareruya's crawler matches against but
  never writes.
- **`prices`** — append-only log of price observations, one row per
  crawl per `(printing, language)`. Includes `stock` and
  `weekly_sales`, which are useful signals for spotting movement beyond
  the release-date tiering alone if you want to refine scheduling
  later.

## Web UI

The frontend is the SvelteKit app in `web/`: enter a Scryfall set code
and collector number (both with autocomplete), get a table of the
latest JP/EN, foil/non-foil prices and a chart of price history for
each. It's read-only against the DB — looking something up never hits
Hareruya. If a card shows up but every price cell is empty, the crawler
hasn't run for that set yet (or hasn't run *with foil included* — see
below).

**Docker Compose** (recommended — starts alongside the DB):

```bash
docker compose up -d db web frontend
```

Then open `http://localhost:5173` (the API itself stays on
`http://localhost:8000`).

**Locally**, with `DATABASE_URL` pointing at a reachable Postgres:

```bash
uvicorn api.main:app --reload        # terminal 1 -> http://localhost:8000
cd web && npm install && npm run dev # terminal 2 -> http://localhost:5173
```

### Foil prices

The crawler defaults to **non-foil only** to keep request volume down
(foil roughly doubles the number of listings per set, so roughly
doubles page/request count for the same `min_interval_seconds`). To
also crawl foil:

```bash
# one-off / manual crawl of a single set:
python -m scraper.crawl 426 --foil

# scheduled daily crawl -- set this wherever daily_run.py runs
# (e.g. in the cron entry, or docker-compose.yml's `web`/`app` env):
CRAWL_INCLUDE_FOIL=true python -m scraper.daily_run
```

Until foil is crawled for a given set, the web UI's foil rows/chart
lines simply won't appear (not an error) — there's nothing to show
yet.

## Not yet built

- **`category=` products.** Hareruya's promos, Secret Lair drops, Duel
  Decks, standalone "The List", and a long tail of other groupings use
  a `category=<id>` query pattern instead of `cardset=<id>` — a
  different endpoint shape this scraper doesn't support at all yet
  (`sync_sets.py` silently drops these nodes, `hareruya_client.py` has
  no way to build a `category=` request). See the "`category=`
  products" note above.
