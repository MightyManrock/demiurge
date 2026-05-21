> **Status:** active
> **TO-DO ref:** Rework action success/failure math
> **Last updated:** 2026-05-21

## Goal

Revise the roll that determines whether an action succeeds. The primary design question is whether `Framing` should gate success likelihood rather than (or in addition to) its current role.

## Approach

1. Audit the current success roll in `logic/tick_logic.py` — find `_resolve_intent_mutations()` and identify where success/failure is determined and what inputs feed it.
2. Read `docs/Mechanics/action-system.md` and `docs/Mechanics/influence-actions.md` for how Framing currently works.
3. Decide on the new formula: options include (a) Framing multiplies base success chance, (b) domain mismatch between Framing Imago and target directly reduces success, (c) a hybrid.
4. Implement the change, update the relevant Mechanics doc.
5. Run `--autoplay` with a few strategies to sanity-check balance hasn't blown up.

## Files affected

- `logic/tick_logic.py` — success roll logic in `_resolve_intent_mutations()`
- `core/action_core.py` — possibly `ActionDefinition` fields if new parameters are needed
- `docs/Mechanics/action-system.md` — update to reflect new math
- `docs/Mechanics/influence-actions.md` — Framing section

## Notes

- The Re-cost Manifest Omen item is explicitly blocked on this plan: if Framing gates success, a mismatched omen already self-penalizes, which may make a cost increase redundant.
- Don't change the formula without a clear design rationale — this touches every action in the game.
