> **Status:** active
> **TO-DO ref:** CLAUDE.md Simplification
> **Last updated:** 2026-05-21

## Goal

Reduce CLAUDE.md to a lean, navigable reference. Move per-mechanic detail into dedicated files under `docs/Mechanics/` so Claude Code can load only what it needs for a given task.

## Approach

1. Keep the repo layout table and running-things section largely intact — these are high-value orientation content.
2. Reduce each mechanics section (tick loop, action system, domain system, Imago, etc.) to a short intro paragraph + a link to the corresponding `docs/Mechanics/<topic>.md`.
3. Create `docs/Mechanics/` and populate it with the extracted detail, preserving all existing content.
4. Add breadcrumb headers to each Mechanics file pointing back to CLAUDE.md.

## Files affected

- `CLAUDE.md` — trimmed
- `docs/Mechanics/` — new folder, one file per section:
  - `tick-loop.md`
  - `action-system.md`
  - `domain-system.md`
  - `imago-system.md`
  - `imago-revelation.md`
  - `influence-actions.md`
  - `essence-generation.md`
  - `belief-footprint.md`
  - `window-visibility.md`
  - `agent-system.md`
  - `scry-action.md`
  - `mortal-system.md`
  - `luminary-personality.md`

## Notes

- The architecture layers section and the "Extending the system" section should stay in CLAUDE.md — they're the most-reached-for reference during active development.
- Known/fixed issues section can stay too; it's short and useful at a glance.
