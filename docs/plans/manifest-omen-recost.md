> **Status:** active
> **TO-DO ref:** Re-cost Manifest Omen
> **Last updated:** 2026-05-21

## Goal

Decide whether Manifest Omen's Essence cost needs to increase to account for its power level, particularly when paired with skilled Framing use.

## Approach

1. Playtest Manifest Omen with well-matched and mismatched Framing to assess current power level.
2. Manifest Omen always fires — it has no miss state. The Framing rework (which may gate success on regular actions) is orthogonal: Framing on Manifest Omen governs interpretation fidelity, not whether it activates. These are independent concerns.
3. Evaluate cost on its own merits. If it's overcost-effective even accounting for misinterpretation risk: increase its base Essence cost in `utilities/action_registry.py` and adjust the action definition.

## Files affected

- `utilities/action_registry.py` — Manifest Omen cost (if increase is warranted)
- `docs/Mechanics/influence-actions.md` — update cost documentation

## Notes

- Resolution may be "no change needed" — that's a valid outcome.
- The action success rework is now a separate, independent track.
