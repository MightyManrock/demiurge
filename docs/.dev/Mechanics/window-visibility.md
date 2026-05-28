> [← CLAUDE.md](../../CLAUDE.md)

# Window Visibility

Entities have `visibility: float` (0.0–1.0) and `pinned: bool`. `pinned=True` never decays (default for all scenario-start entities). `is_in_window(entity)` returns True if pinned or `visibility > ENTITY_VISIBILITY_FLOOR (0.05)`. Mortals additionally use `prominence ≥ ALWAYS_VISIBLE_THRESHOLD (0.65)` as a separate "always visible" criterion (see `is_mortal_visible`).

Non-pinned entities decay each tick at TickConfig-defined rates (locations, civs, species, mortals each have their own). Domain profiling is unaffected — Phase 3 reads all entities regardless of visibility. The TUI gates display on `is_in_window`; with `--dev`, out-of-Window entities are shown dimmed rather than hidden.
