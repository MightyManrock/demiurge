> status: parked | last updated: 2026-05-31

# Narrative Formatters: Extract from tick_logic

## Goal

Extract all narrative string-building logic from `logic/tick_logic.py` (and `logic/civilian_agent_logic.py`) into a dedicated `logic/narrative_formatters.py` module. This is a pure refactor — no behavioral changes, no new features.

**Context:** During a narrative consistency audit (2026-05-31), we catalogued ~20 narrative generation sites across tick_logic. The display pipeline was also unified at that time (`_linkify` → `_process_narrative` everywhere). The remaining separation of concerns issue is that simulation logic and presentation string-building are co-mingled in tick_logic.

---

## What moves

One formatting function per event type. Each takes the raw simulation objects it needs and returns a string (or `NarrativeEvent` if the `in_window` determination is simple enough to include). tick_logic retains the orchestration decision — when to emit — but delegates string construction entirely.

**From `logic/tick_logic.py`:**

| Site (approx. line) | Formatter name |
|---|---|
| ~1070 — pending action cancelled | `fmt_pending_cancelled(action_key)` |
| ~1180–1217 — domain belief/culture drift events | `fmt_domain_drift(tag, delta, kind)` |
| ~1490–1506 — mortal arrival/departure | `fmt_mortal_arrival(mortal, civ)` / `fmt_mortal_departure(mortal, civ)` |
| ~1567–1571 — mortal prominence change | `fmt_mortal_prominence(mortal, old, new)` |
| ~1624–1627 — mortal death | `fmt_mortal_death(mortal)` |
| ~1648–1652 — mortal aging narrative | `fmt_mortal_aging(mortal)` |
| ~1737–1754 — pop splinter | `fmt_pop_splinter(pop, splinter, civ, top_div_tag, divergence)` |
| ~1777–1784 — link drift dissolution | `fmt_link_drift(pop_a, pop_b, state)` |

**From `logic/civilian_agent_logic.py`:**

| Site | Formatter name |
|---|---|
| sell action | `fmt_civilian_sell(mortal, resource, location)` |
| spend action | `fmt_civilian_spend(mortal, resource)` |
| leisure action | `fmt_civilian_leisure(mortal, pop)` |
| socialize action | `fmt_civilian_socialize(mortal, pop)` |
| collect action | `fmt_civilian_collect(mortal, resource)` |
| travel depart | `fmt_civilian_travel_depart(mortal, dest)` |
| travel arrive | `fmt_civilian_travel_arrive(mortal, dest)` |

## What stays

- All simulation logic, mutation lists, and phase orchestration in `tick_logic.py`
- `_process_narrative`, `_linkify`, `_entity_link`, sentinel regex — all in `ui/display.py` (display layer)
- `pop_label` — stays in `core/universe_core.py` (model layer utility, already there)

## New file structure

```python
# logic/narrative_formatters.py

from core.universe_core import Pop, Civilization, NotableMortal, pop_label
from core.action_core import NarrativeEvent

# Sentinel helpers — private to this module
def _pop_sentinel(pop: Pop) -> str:
    return f"§pop§{pop.id}§{pop_label(pop)}§"

def _domain_sentinel(tag: str) -> str:
    label = tag.split(":", 1)[-1].title() if ":" in tag else tag.title()
    return f"§domain§{tag}§{label}§"

# Public formatters — called from tick_logic and civilian_agent_logic
def fmt_pop_splinter(pop: Pop, splinter: Pop, civ: Civilization, top_div_tag: str, divergence: float) -> str: ...
def fmt_mortal_death(mortal: NotableMortal) -> str: ...
def fmt_pending_cancelled(action_key: str) -> str: ...
# ... etc.
```

## Import strategy

`narrative_formatters.py` imports from `core/` only — no imports from `tick_logic.py` or `civilian_agent_logic.py`, which avoids any circular dependency risk entirely.

`tick_logic.py` and `civilian_agent_logic.py` import from `narrative_formatters.py`:
```python
from logic.narrative_formatters import fmt_pop_splinter, fmt_mortal_death, ...
```

## Commit strategy

Single commit: "refactor: extract narrative string-building to logic/narrative_formatters.py". Tests and autoplay must pass before pushing. No numbers or behavior should change.

---

## Files affected

| File | Change |
|---|---|
| `logic/narrative_formatters.py` | New file |
| `logic/tick_logic.py` | Remove inline string-building, import and call formatters |
| `logic/civilian_agent_logic.py` | Remove inline string-building, import and call formatters |

---

## Notes

- This refactor has no player-visible effect. It is purely an internal cleanup.
- The sentinel helpers (`_pop_sentinel`, `_domain_sentinel`) currently duplicated across tick_logic can be consolidated here as private utilities.
- If a formatter needs `SimulationState` (e.g. link drift needs to look up both pops), import it from `tick_logic` under `TYPE_CHECKING` only to avoid runtime circularity, or accept the relevant objects directly as parameters (preferred — keeps formatters pure).
- Do this refactor when tick_logic is otherwise quiet. Touching 20+ sites in a noisy branch increases merge risk.
