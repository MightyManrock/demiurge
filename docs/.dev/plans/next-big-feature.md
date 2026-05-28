> **Status:** active
> **TO-DO ref:** Pick the next big feature
> **Last updated:** 2026-05-21

## Goal

Choose the next major system to build: Agent expansion, Factions, Governments, or resources↔tech-progress. This plan tracks the decision and becomes the seed for the implementation plan once a direction is chosen.

## Options

| Option | Notes |
|---|---|
| **Agent expansion / Factions** | These are the same fork — `Faction` is the data-model prerequisite for expanding the agent phase. High narrative impact. |
| **Governments** | Would add political structure on top of civilizations. Dependent on Factions for full value. |
| **Resources ↔ tech-progress** | Economic/technological layer. More self-contained but lower narrative texture at current game scale. |

## Approach

1. Decide in conversation with the player (you). This plan is parked until that conversation happens.
2. Once direction is chosen, create a dedicated implementation plan and close this one.

## Notes

- Agent expansion and Factions are listed separately in TO-DO but are the same architectural fork — a `Faction` model in `core/universe_core.py` is the prerequisite for both.
- Governments likely want Factions first too, so Factions may be the natural first step regardless of which direction is chosen.
