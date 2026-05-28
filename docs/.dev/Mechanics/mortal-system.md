> [← CLAUDE.md](../../CLAUDE.md)

# Mortal System

- `home_location` and `current_location` are required `UUID` fields on `NotableMortal`.
- Active Proxii do not age biologically (`bio_age` frozen); dormant Proxii age at 1/5 rate.
- `MortalProminence.APEX` designates a notable member of a non-sapient species (uplift candidate).
- Starting alignment is auto-computed by `scenario_loader` for mortals with stored `alignment == 0.0`, using `compute_mortal_alignment_base()` plus a "new Demiurge" penalty (alignment below 0.75 is dragged proportionally lower at session start; drifts back toward the natural base over ticks via `alignment_drift_rate`).
