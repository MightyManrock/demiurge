# Whisper to Mortal — Action Redesign

**Status:** `active`  
**Parent:** [actions-redesign-master-plan.md](../actions-redesign-master-plan.md)  
**Branch:** `action-redesign`  
**Last updated:** 2026-05-24

---

## Summary

Replace the current 3-step wizard (mortal picker → domain picker → imago picker) with a single large unified configuration modal. Mechanic and DB schema are unchanged — this is purely a UI overhaul.

---

## 1. Mechanic

No changes. `WhisperIntent` fields, tick-logic handler, success formula, and footprint costs all stay as-is.

---

## 2. UI

### Current flow

`_build_intent("whisper")` in `ui/ui.py` chains three sequential `push_screen_wait` calls:
1. Mortal picker (`PickerModal`)
2. Domain picker (`DomainPickerModal`)
3. Imago tree picker (`ImagoTreeModal`) + imago detail/confirm (`ImagoDetailModal`)

### New flow

Replace steps 1–3 with a single `push_screen_wait(WhisperConfigModal(...))`. After the player clicks Continue, feed the result into the existing `ImagoDetailModal` for the confirmation step (unchanged).

### `WhisperConfigModal` layout

Full-screen (or near full-screen) two-column modal.

```
┌─────────────────────────────────────────────────────────────────┐
│  Whisper to Mortal                                              │
├────────────────────────┬────────────────────────────────────────┤
│  Mortal:  [Name]       │  Domain:  [Name]                       │
│ ┌──────────────────┐   │  ┌──┬──┬──┬──┬──┬──┬──┬──┐            │
│ │ Erevan  0.72 ...  │  │  │◈ │⬡ │◯ │✷ │✖ │🜂│≋ │∅ │            │
│ │ Ayana   0.45 ...  │  │  ├──┼──┼──┼──┼──┼──┼──┼──┤            │
│ │ ...               │  │  │✿ │☋ │◉ │⚱ │☼ │⚙ │⛉ │♾ │            │
│ │                   │  │  └──┴──┴──┴──┴──┴──┴──┴──┘            │
│ │                   │  │                                        │
│ │                   │  │  Imāgō:  [Name]                        │
│ │                   │  │  ┌─────────────────────────────────┐   │
│ └──────────────────┘   │  │  [imago tree for selected domain]│  │
│                        │  └─────────────────────────────────┘   │
│                        │                                        │
│                        │        [Back]  [Cancel]  [Continue]    │
└────────────────────────┴────────────────────────────────────────┘
```

#### Left panel — Mortal list

- `ListView` of all visible, non-deceased, non-Proxius/Herald mortals in the current window.
- Each row: `{name:<18}  align:{alignment:.2f}  {pop_name:<14}  {location_name}`
- Selecting a row updates the **"Mortal: [Name]"** label at the top of the left panel.

#### Right panel — Domain buttons

- 16 buttons arranged in a 2×8 `Grid`, each labelled with the domain's unicode icon (`dreg.icon(tag)`).
- Domains for which the player has **no unlocked imagoes** are `disabled=True` (greyed out, non-interactive). A domain is eligible if `demiurge.revelation_pools.get(tag, 0.0) > 0` (i.e. at least one imago has been unlocked at any tier — same logic as the existing `DomainPickerModal` capping).
- Selecting a domain:
  1. Updates the **"Domain: [Name]"** label.
  2. Clears any current imago selection and resets the **"Imago: —"** label.
  3. Re-renders the imago tree section below to show that domain's tree.

#### Right panel — Imago tree

- Displays the 7-node tree for the currently selected domain, using the same node layout as `ImagoTreeModal`.
- Nodes the player has not yet unlocked are greyed out (`disabled=True`).
- Clicking an eligible node updates the **"Imago: [Name]"** label.
- If the player selects a different domain after having already picked an imago, the imago selection clears before the tree re-renders.

#### Footer buttons

- **Back** — dismisses with `BACK` sentinel.
- **Cancel** — dismisses with `None`.
- **Continue** — disabled (greyed) until mortal, domain, AND imago are all selected. Once all three are chosen, enabled and styled green (add CSS class `continue-ready`). Dismisses with `(mortal_id, domain_tag, imago_node_id)`.

### After the modal

`_build_intent("whisper")` receives the tuple, constructs `WhisperIntent`, then calls `push_screen_wait(ImagoDetailModal(...))` for the existing confirmation step — no change to that part.

### Files affected

| File | Change |
|---|---|
| `ui/modals.py` | Add `WhisperConfigModal` class |
| `ui/styles.tcss` | Add `.continue-ready` button style (green) |
| `ui/ui.py` | Replace 3-step whisper chain in `_build_intent` with single `WhisperConfigModal` call |

---

## 3. DB prep

None required. All data needed by the modal is already in `SimulationState` or the registries.

---

## Notes

- `dreg.icon(tag)` is already available on the domain registry — this is the unicode glyph to use on domain buttons.
- The imago tree rendering logic in `ImagoTreeModal` (in `modals.py`) should be extracted into a private helper or widget that `WhisperConfigModal` can reuse, rather than duplicating.
- This modal is the prototype for the "anti-wizard" pattern. Other multi-step influence actions (Shape Dream, etc.) will follow the same template once this one is validated.
