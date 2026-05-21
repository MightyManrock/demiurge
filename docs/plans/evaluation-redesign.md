> **Status:** complete
> **TO-DO ref:** (session work — no prior TO-DO entry)
> **Last updated:** 2026-05-21
> **Completed:** 2026-05-21

## Goal

Sharpen the Luminary disposition system so that **results** and **methods** axes have distinct, meaningful drivers — and so the `results_builder` autoplay strategy actually differentiates from an inert tanker baseline.

## Changes made

### Results axis → Essence satisfaction only
Removed `domain_alignment_to_results_delta` and `similarity_results_modifier` from the disposition delta assembly in `logic/tick_logic.py`. `EssenceSatisfaction.disposition_delta` is now the **exclusive** driver of the results axis. Motivation: Luminaries have no direct perception of domain expression in-world — they only feel it through Essence income.

### Passive essence expectation creep
Added `luminary_essence_passive_rise: float = 0.50` to `SimulationConfig`. Each evaluation period, before the threshold comparison:

```python
passive_rise = cfg.luminary_essence_passive_rise * ticks_since / max(state.tick_number, 1)
luminary.essence_expectation_raised += passive_rise
```

Large early (pressure mounts fast), shrinks with age (the bar raised early is harder to raise further). Creates long-run divergence between strategies that grow Essence and those that don't.

### Vrath FootprintConstraints (wardens_compact.db)
Added two loose-tolerance constraints to Vrath (enforcement_weight=0.45 each):
- **"No Cowardly Whispers"** — `subtle_influence ≤ 0.65`: Vrath finds subtlety dishonest/lazy.
- **"No Hiding Behind Proxii"** — `proxius_activity ≤ 0.65`: Same rationale — he wants the Demiurge in the open.

These activate the methods axis for Vrath; previously he had no FootprintConstraints and his methods score never moved.

### results_builder.py rewrite
Complete rewrite targeting Vrath's conflict/change domains:
- Appoints Veth Sarai tick 1, directs to preach Broken Banner → Neran Artisan pop
- Explores conflict → reveals Sharpened Edge at pool≥100; then change → New Dawn
- Domain swaps: order→conflict→mastery, change→growth (when essence≥1.5)
- Whispers to highest-alignment visible mortals, rotating by tick index
- Opportunistically appoints Urren (edge unlocked) and Deva (dawn unlocked)
- Fires one Omen per unlock (Sharpened Edge → Oros, New Dawn → Sethis) using `just_revealed_*` flags

## Files affected

- `logic/tick_logic.py` — disposition delta assembly; passive rise; `luminary_essence_passive_rise` config field
- `scenarios/wardens_compact.db` — two new FootprintConstraints for Vrath
- `autoplay/strategies/results_builder.py` — full rewrite
- `docs/Mechanics/belief-footprint.md` — (unchanged; already documents FootprintConstraint mechanics)

## Notes

- `luminary_essence_passive_rise = 0.50` is a provisional tuning; divergence between builder and tanker requires longer runs (50 ticks is borderline). May want to raise or run --autoplay for 100 ticks to see it clearly.
- The "Vrath dislikes subtlety" framing is intentional flavor: he's a conflict/change Luminary who sees whispers and proxy-work as cowardice.
