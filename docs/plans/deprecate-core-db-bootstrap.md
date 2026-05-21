> **Status:** active
> **TO-DO ref:** Deprecate `core/core.db` auto-bootstrapping on launch
> **Last updated:** 2026-05-21

## Goal

Stop `core/core.db` from being unconditionally rewritten on every `main.py` launch. The DB should be treated as authoritative once it exists — only build it when genuinely absent. This eliminates the persistent git diff noise on `core/core.db` after every run.

## Background

Four registries write to `core/core.db` at startup:

| Registry | File | Current behavior |
|---|---|---|
| Domain | `utilities/domain_registry.py` | `CREATE TABLE IF NOT EXISTS` + `INSERT OR REPLACE` every launch |
| Culture | `utilities/culture_registry.py` | `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` every launch |
| Imago | `utilities/imago_registry.py` | `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` every launch |
| Action | `utilities/action_registry.py` | Only inserts missing actions — already idempotent |

Domain is the most aggressive: it uses `INSERT OR REPLACE`, so it overwrites any edited values, and also runs a DELETE to purge retired tags on every boot.

The call chain is: `main.py` → `DemiurgeApp.__init__()` → `TickLoop.__init__()` → each registry's `__init__()` → `_ensure_db()` / `_bootstrap()`.

The explicit rebuild tool (`tools/rebuild_databases.py`) already exists as the supported path for regenerating registry data. Auto-bootstrap is therefore redundant once the DB has been seeded.

## Approach

1. **Add a presence check** to each registry's `_ensure_db()` / `_bootstrap()` method:
   - If the relevant table already contains rows, skip the seed entirely.
   - If the table is absent or empty, seed as today (first-run / missing DB).
   - Domain: check `SELECT COUNT(*) FROM domain_registry` before the upsert block.
   - Culture: check `culture_registry` row count.
   - Imago: check `imago_node` row count.
   - Action: already guarded — no change needed.

2. **Remove the domain cleanup DELETE** (`DELETE FROM domain_registry WHERE tag IN (...)`) from the normal boot path. Move it into `tools/rebuild_databases.py` as an explicit migration step, or just let the rebuild handle it.

3. **Verify `tools/rebuild_databases.py`** forces a full reseed regardless of the presence check (i.e., it should pass a `force=True` flag or drop-and-recreate, not rely on the same guard).

4. **Test** by:
   - Running `python main.py --autoplay` twice in a row and confirming `git diff core/core.db` is empty after the second run.
   - Running `python main.py --rebuild` and confirming it still updates the DB correctly.

## Files affected

- `utilities/domain_registry.py` — add row-count guard before upsert block; remove boot-time DELETE
- `utilities/culture_registry.py` — add row-count guard before insert block
- `utilities/imago_registry.py` — add row-count guard before insert block
- `tools/rebuild_databases.py` — ensure rebuild path bypasses the guard (force reseed)

## Notes

- The action registry already has the right behavior (inserts only missing rows). Use it as the reference pattern.
- `core/core.db` is committed to the repo, so the file is always present in a fresh clone — the "absent" case is mainly for a truly clean environment or a deliberate `rm core/core.db`.
- Do not add a `force` parameter to the normal registry constructors; keep that complexity inside the rebuild tool only.
