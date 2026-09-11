"""One-off: fill config/set_name_jp_overrides.toml from sets_hareruya.name_jp."""

import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

TOML_PATH = Path(__file__).resolve().parent / "config" / "set_name_jp_overrides.toml"
PREFIX = "マジック：ザ・ギャザリング｜"
PREFIX_DASH = "マジック：ザ・ギャザリング——"
VARIANT_SUFFIXES = ("ブースター・ファン", "統率者", "日本画ミスティカルアーカイブ", "ミスティカルアーカイブ", "エターナル使用可能カード")

engine = create_engine("postgresql+psycopg://jpy_mtg:jpy_mtg@db:5432/jpy_mtg_prices")

with engine.connect() as conn:
    rows = conn.execute(
        text(
            "SELECT set_code, name_jp FROM sets_hareruya "
            "WHERE set_code IS NOT NULL AND set_code <> '' "
            "AND name_jp IS NOT NULL AND name_jp <> ''"
        )
    ).fetchall()

# Build code -> name map. Prefer the shortest name for a code (base set,
# not the booster-fun / commander variants).
best: dict[str, str] = {}
for code, name_jp in rows:
    name = name_jp.strip()
    for prefix in (PREFIX, PREFIX_DASH):
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    code = code.strip().lower()
    if code not in best or len(name) < len(best[code]):
        best[code] = name

print(f"Hareruya rows: {len(rows)}, distinct codes: {len(best)}")

content = TOML_PATH.read_text(encoding="utf-8")
ends_with_newline = content.endswith("\n")
lines = content.splitlines()

filled = 0
skipped_existing = 0
out: list[str] = []
for line in lines:
    m = re.match(r'^(\w+) = ""(  # .*)?$', line)
    if m:
        code = m.group(1).lower()
        if code in best:
            out.append(f'{m.group(1)} = "{best[code]}"{m.group(2) or ""}')
            filled += 1
        else:
            out.append(line)
    elif re.match(r'^\w+ = "', line):
        skipped_existing += 1
        out.append(line)
    else:
        out.append(line)

TOML_PATH.write_text("\n".join(out) + ("\n" if ends_with_newline else ""), encoding="utf-8")
print(f"Filled: {filled}, already had values: {skipped_existing}")

# Verify it loads
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper.sync_scryfall import load_set_name_jp_overrides

loaded = load_set_name_jp_overrides(TOML_PATH)
print(f"Active overrides after fill: {len(loaded)}")
for k in sorted(loaded)[:10]:
    print(f"  {k} = {loaded[k]}")
