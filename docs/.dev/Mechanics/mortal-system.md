> [← CLAUDE.md](../../CLAUDE.md)

# Mortal System

- `home_location` and `current_location` are required `UUID` fields on `NotableMortal`.
- Active Proxii do not age biologically (`bio_age` frozen); dormant Proxii age at 1/5 rate.
- `MortalProminence.APEX` designates a notable member of a non-sapient species (uplift candidate).
- Starting alignment is auto-computed by `scenario_loader` for mortals with stored `alignment == 0.0`, using `compute_mortal_alignment_base()` plus a "new Demiurge" penalty (alignment below 0.75 is dragged proportionally lower at session start; drifts back toward the natural base over ticks via `alignment_drift_rate`).

---

## Pop milieu (`pop_milieu`)

`NotableMortal.pop_milieu: Optional[UUID]` — the Pop the mortal is **currently embedded among**. Distinct from `pop_id` (the mortal's origin/home Pop). On scenario load, defaults to `pop_id` if not explicitly set.

`pop_milieu` affects which Pop the mortal is "speaking from" for whisper-splash influence calculations and similar social-context operations.

### Default arrival milieu (`_default_arrival_milieu`)

When a mortal arrives at a destination `PopLocation` with no explicit `TravelIntent.target_pop_id`, this static method picks `pop_milieu` using the following priority order:

1. **Own Pop at destination** — if the mortal's origin Pop (`pop_id`) is present at the destination, use it.
2. **Linked Pop at destination** — if any Pop in the origin Pop's `linked_pop_ids` is present, use the one with the highest computed link factor. The FERAL/WILD social-class filter is not applied here; an explicit link overrides normal social-class aversions.
3. **Same occupation** — among filtered, civ/species/size-sorted candidates, first Pop with `occupation == origin_pop.occupation`.
4. **Same stratum** — first Pop with matching `social_class`.
5. **Closest stratum within 2 steps** — WARRIOR special case: COMMON > TRADER > ARTISAN; general: walk down `_STRATUM_ORDER` up to 2 steps.
6. **None** — mortal has no Pop context at the destination.

COMMON-and-above mortals exclude FERAL and WILD Pops from steps 3–5 (step 2 is exempt).

See [linked-pops.md](linked-pops.md) for the linked-pop mechanic that feeds into step 2.
