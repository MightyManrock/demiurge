# Narrative Events — How-To and Reference

All player-visible log messages are `NarrativeEvent` objects or plain strings routed through a small set of display functions. This document is the canonical reference for generating new narratives correctly.

---

## The two layers

| Layer | Where | Responsibility |
|---|---|---|
| **Generation** | `logic/tick_logic.py`, `logic/civilian_agent_logic.py` | Build the text string; decide `in_window`; append to the right list |
| **Display** | `ui/display.py` — `_process_narrative()` | Resolve sentinels, linkify plain entity names, emit Rich markup |

These layers must stay separate. Generation code never imports from `ui/`. Display code never knows about simulation logic.

---

## Narrative categories and their lists

| Category | List on `TickResult` / `PassiveResult` | Display label | Chip filter |
|---|---|---|---|
| World events | `result.passive_result.narrative_events` | `WORLD EVENTS` | `system` |
| Action results | `result.action_result.entries[i].narrative` | `YOUR ACTIONS` | `actions` |
| Proxius reports | `result.agent_narratives` | `PROXIUS REPORTS` | `proxius` |
| Pinned mortal updates | `result.mortal_narratives` | `PINNED MORTALS` | `mortal` |

All four paths run through `_process_narrative()` in the display layer. **Never use `_linkify` directly** — it is called internally by `_process_narrative` and skips sentinel resolution.

---

## NarrativeEvent — always use the class

```python
# ✓ correct
result.passive_result.narrative_events.append(NarrativeEvent(
    text="...",
    in_window=is_in_window(pop),
))

# ✗ wrong — raw strings bypass in_window filtering
result.passive_result.narrative_events.append("...")
```

`in_window=True` → shown in normal and dev mode.
`in_window=False` → shown **only** in dev mode (dimmed). Use this when the event is real but involves entities outside the player's current Window.

Agent narratives and mortal narratives are plain strings (no `NarrativeEvent` wrapper) — they are always shown when present.

---

## Referencing entities in narrative text

### Named entities — use plain text

Entities that have unique, human-readable names are caught by `_linkify` automatically via the name index. Just write the name:

```python
f"{mortal.name} arrived at {civ.name}."
f"The {location.name} region shifted."
```

Entities covered: `NotableMortal` (`.name`), `Civilization` (`.name`), `SignificantLocation` / `System` / `Location` (`.name`).

### Anonymous entities — use sentinels

Entities without globally unique names need a UUID-bearing sentinel so the display layer can build a clickable link:

```
§type§identifier§display_label§
```

| Entity type | Sentinel format | Example |
|---|---|---|
| Pop | `§pop§{pop.id}§{pop_label(pop)}§` | `§pop§uuid§Artist§` |
| Species | `§species§{species.id}§{species.name}§` | `§species§uuid§Naran§` |
| Domain | `§domain§{full_tag}§{Label}§` | `§domain§domain:order§Order§` |
| Civilization | `§civ§{civ.id}§{civ.name}§` | `§civ§uuid§The Neran Confederacy§` |
| Imago node | `§imago§{node.id}§{node.name}§` | `§imago§uuid§Preach Imāgō§` |

**Pop labels** — always use `pop_label(pop)` from `core.universe_core` to get the right display name (authored name > occupation > stratum):

```python
from core.universe_core import pop_label
_sentinel = f"§pop§{pop.id}§{pop_label(pop)}§"
```

**Domain labels** — strip the `domain:` prefix and title-case it:

```python
label = tag.split(":", 1)[-1].title()   # "domain:order" → "Order"
_sentinel = f"§domain§{tag}§{label}§"
```

You can use both named-entity text and sentinels in the same string — `_process_narrative` resolves sentinels first, then linkifies the remaining plain text.

---

## Complete example

```python
from core.universe_core import pop_label
from core.action_core import NarrativeEvent

top_tag = "domain:order"
label = top_tag.split(":", 1)[-1].title()   # "Order"

note = (
    f"[Pop splinter] Part of §pop§{pop.id}§{pop_label(pop)}§ ({civ.name}) "
    f"broke away as §pop§{splinter.id}§{pop_label(splinter)}§ "
    f"over §domain§{top_tag}§{label}§ (divergence {divergence:.2f})."
)
events.append(NarrativeEvent(text=note, in_window=is_in_window(pop)))
```

---

## Sentinel resolution in display.py

`_ENTITY_SENTINEL_RE` matches: `pop`, `civ`, `imago`, `species`, `domain`.

Each type routes to a link action:

| Type | Action |
|---|---|
| `pop`, `civ`, `species`, `mortal`, location types | `screen.open_detail_by_id(kind, uuid)` |
| `imago` | `screen.open_imago_node(uuid)` |
| `domain` | `screen.open_divine_wisdom(tag)` |

To add a new sentinel type: (1) add the type string to `_ENTITY_SENTINEL_RE` in `display.py`; (2) add a color entry to `_LOG_LINK_COLORS`; (3) add a dispatch case in `_entity_link` if it needs a non-standard click action.

---

## Planned refactor

Narrative string-building is currently inline in `tick_logic.py` and `civilian_agent_logic.py`. The plan `docs/.dev/plans/narrative-formatters.md` tracks extraction of this into `logic/narrative_formatters.py`. Until that refactor lands, keep all new narrative strings consistent with the patterns above.
