# Actions Redesign — Master Plan

**Status:** `active`  
**Branch:** `action-redesign`  
**Last updated:** 2026-05-24

---

## Goal

A systematic pass over every action in the game. For each action we're capturing three things:

1. **Mechanic** — what the action actually does under the hood
2. **UI** — how the player interacts with it (pickers, confirmation steps, feedback)
3. **DB prep** — any schema columns needed now to support future features

All changes land on the `action-redesign` branch and merge together.

---

## How to use this document

As we work through actions in conversation, a sub-plan file gets created in `docs/plans/actions/` for each action (or logical group). This master plan stays as the index and tracks overall status. Sub-plans contain the actual spec.

When a sub-plan is fully implemented, mark it `complete` here and in its own file.

---

## Sub-plans index

| Action(s) | Sub-plan file | Status | Notes |
|---|---|---|---|
| `whisper` | [actions/whisper-to-mortal.md](actions/whisper-to-mortal.md) | `active` | UI only — unified config modal replaces 3-step wizard |

---

## Actions by category

Listed in category order, matching the in-game action browser. Stubs and parked actions noted.

### Direct Creation
- `seed_world`
- `uplift_species`
- `reshape_world`
- `extinguish_civilization`

### Overt Miracle
- `manifest_omen`
- `direct_miracle`
- `divine_manifestation`

### Subtle Influence
- `whisper`
- `shape_dream`
- `nudge_probability`
- `accelerate_development`

### Proxius Direction
- `appoint_proxius`
- `preach_imago`
- `empower_proxius`
- `dismiss_proxius`
- `go_quiet_proxius`
- `rescind_directive`
- `audit_proxius`

### Observation
- `scry`
- `explore_beliefs`
- `commission_inquiry`

### Self Refinement
- `reveal_imago`
- `change_affiliated_domains`
- `harvest_essence`

### Luminary Relations
- `report_to_luminary`
- `petition_constraint_relaxation`
- `dispute_demand`
- `ask_for_orders`

### Herald Interaction *(stub — awaiting Herald entity)*
- `negotiate_herald`
- `obstruct_herald`
- `petition_luminary_herald`

### Underreal
- `salvage_concept`
- `exile_to_underreal`
- `maintain_concealment`
- `investigate_underreal` *(stub)*
- `overthrow_luminary` *(stub)*
- `read_divine_traces` *(parked)*

---

## Branch note

When implementation begins, cut `action-redesign` from current `main`. All sub-plan changes go there. No partial merges — the branch lands as a unit unless a sub-plan is explicitly flagged as independent.

---

## Preservation rule

**Do not overwrite or remove any existing modal class during implementation.** New modals are added alongside old ones. The existing wizard-chain modals (`DomainPickerModal`, `ImagoTreeModal`, etc.) stay in place and fully functional throughout the redesign — other parts of the codebase that still use them must not break.

The only exception is shared helpers: if a helper is extracted from an existing modal (e.g. an imago tree rendering widget), the extraction may modify the original class to delegate to the helper, as long as its external behaviour is unchanged.

At the end of the full redesign pass, a dedicated cleanup step will identify and remove all modal code that is no longer referenced.
