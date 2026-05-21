> **Status:** active
> **TO-DO ref:** Human-readable Documentation
> **Last updated:** 2026-05-21

## Goal

Produce accessible, non-technical documentation for players — covering how to play the game, what the systems do, and how to interact with them. Players should come away with a solid mental model without needing to read code or Mechanics deep-dives.

## Approach

1. Write a getting-started guide / tutorial covering the core loop: queue actions → advance tick → read Luminary feedback → repeat.
2. Write plain-language overviews of each major system (Imagines, Influence Actions, Essence, Puissance, etc.) — enough to play intelligently, not enough to be a mechanic reference.
3. Publish as Markdown in `docs/Player/` (or similar) so it lives with the repo and can later feed an in-game encyclopedia.
4. Long-term: fold content into a redesigned **Divine Wisdom** tab with navigable UI and optional search.

## Files affected

- `docs/Player/` — new folder; one file per topic or a single `guide.md` to start
- Possibly `ui/` — future Divine Wisdom tab redesign (out of scope for initial pass)

## Notes

- Initial deliverable is Markdown docs, not a UI change. The in-game encyclopedia is a separate, later effort.
- Content should be written for someone who has never played before and is reading outside the game.
