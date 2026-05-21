> **Status:** blocked
> **TO-DO ref:** Re-cost Manifest Omen
> **Last updated:** 2026-05-21
> **Blocked by:** [action-success-rework.md](action-success-rework.md)

## Goal

Decide whether Manifest Omen's Essence cost needs to increase to account for its power level, particularly when paired with skilled Framing use.

## Approach

1. Wait for the action success/failure rework to land first.
2. After the rework, playtest Manifest Omen with well-matched and mismatched Framing to assess whether mismatched omens already self-penalize sufficiently.
3. If the self-penalty is enough: close this item as resolved by the rework.
4. If Manifest Omen is still overcost-effective: increase its base Essence cost in `utilities/action_registry.py` (or wherever costs are defined) and adjust the action definition.

## Files affected

- `utilities/action_registry.py` — Manifest Omen cost (if increase is warranted)
- `docs/Mechanics/influence-actions.md` — update cost documentation

## Notes

- Do not act on this until [[action-success-rework]] is complete.
- Resolution may be "no change needed" — that's a valid outcome.
