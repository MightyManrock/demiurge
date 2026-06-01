# Pop UI Improvements — Design Spec

**Date:** 2026-06-01  
**Status:** Approved  
**Scope:** Three targeted UI improvements to pop display and detail tab lifecycle

---

## 1. Fractional Size in Dev Mode

### What
On a pop's detail page, when dev mode is active, show `size_fractional` alongside the existing `size_magnitude` display.

### Where
`ui/detail_renderers.py` — `render_pop_detail()` around line 1105.

### Format
```
size: 5  5.73          # dev mode — fractional appended, dimmed
size: 5 (100,000)      # normal mode — unchanged
```

The fractional value is rendered dimmed (e.g. `[#606060]`) so it reads as supplementary rather than primary. The word description (`100,000`) is omitted in dev mode to avoid an overly long line.

### Why
`size_fractional` is the engine's internal representation; `size_magnitude` is its floored integer. Pops grow and shrink continuously but the displayed integer only changes at thresholds. Dev mode users need the fractional value to evaluate whether a pop is close to growing or shrinking.

---

## 2. Splinter Pop Default Name

### What
When a splinter pop is created, seed its `name` field with the parent pop's label plus `" Splinter"`.

### Where
`logic/tick_logic.py` — `_check_pop_splinters()` around line 1850, in the `Pop(...)` constructor call.

### How
```python
name=f"{pop_label(pop)} Splinter",
```

Since `Pop.name` takes precedence over occupation and stratum in `pop_label()`, this name propagates automatically to all display contexts: narrative log events, the entities panel, tab labels, sentinels, and detail pages.

### Why
Splinter pops currently have no authored name, so they fall back to occupation or stratum — the same label as their parent. This makes them visually indistinguishable in lists and log events. Seeding `name` at creation is the minimal correct fix: it reuses the existing name-priority system without adding a new display-only concept.

### Notes
- If the parent pop itself is a splinter (grandchild case), its label will already say "Splinter", resulting in e.g. "Merchant Splinter Splinter". This is acceptable for now; such chains are rare and the label is still informative.
- The splinter narrative sentinel (`_splinter_sentinel`) is constructed after `Pop` creation using `label` (the parent's label). No change needed there — the new pop's own name will be used wherever the splinter pop is referenced by its own sentinel.

---

## 3. Auto-Close Detail Tab When Pop Disappears

### What
If a pop detail tab is open and the pop is removed from the simulation (absorbed, or otherwise deleted), the tab closes automatically on the next refresh.

### Where
`ui/detail_tabs.py` — `DetailTabManager.refresh_all()` around line 208.

### How
In `refresh_all`, after re-rendering each pane, check if the tab's current entity still exists. For `kind == "pop"`, look up `state.pops.get(entity_id)`. If the result is `None`, call `_close_pane(pane_id)`.

Panes are iterated over a snapshot (`list(self._panes.values())`) so closing mid-iteration is safe.

### Scope
Pop tabs only, per the stated requirement. Other entity kinds (mortals, civs, locations) are not affected by this change.

### Why
Currently, a tab for a deleted pop shows a "not found" renderer output rather than closing. This is dead UI — the user can't do anything useful with a tab for an entity that no longer exists. Auto-closing on the tick after deletion is the correct behavior.

### Edge case
If a tab has navigated away from the original pop (via the detail tab history stack), `dt.entity_id` reflects the *current* entity, not the original. A tab that has navigated from a pop to a mortal will not be closed if the original pop disappears — which is correct behavior.

---

## Files Affected

| File | Change |
|------|--------|
| `ui/detail_renderers.py` | Show `size_fractional` in dev mode on the pop detail size line |
| `logic/tick_logic.py` | Set `name` on splinter `Pop` at creation |
| `ui/detail_tabs.py` | Close pop tabs whose entity is no longer in `state.pops` |
