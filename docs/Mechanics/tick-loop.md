> [← CLAUDE.md](../../CLAUDE.md)

# The Tick Loop

`TickLoop.advance(state)` runs six phases and returns `(new_state, TickResult)`:

1. **Passive world** — footprint decay, concealment decay, mortal age/alignment drift, civilization momentum, belief drift, cross-Pop contact, attention decay. Then `_process_active_events` emits continuation `BELIEF_SHIFT`/`CIVILIZATION_STAT` mutations for events at offset ≥ 1, populates `pending_attention_triggers`, and prunes expired events.
2. **Action processing** — ongoing actions appended first, `_validate_and_filter_queue` enforces one-per-category, `_resolve_intent_mutations` produces `StateMutation`s, `_apply_mutations` applies them all.
2.5. **Proxius agent resolution** — each active Proxius with `active_goal` takes one autonomous action (`PROMOTE_DOMAIN`, `BOLSTER_BELIEFS`, `TAKE_STOCK`, `REPORT_TO_DEMIURGE`, `PETITION_FOR_RELIEF`, `RESEARCH_DOMAIN`, `NOTHING`). Generates mutations the same way action handlers do.
3. **Domain profiling** — builds `UniverseDomainProfile` from civ `dominant_beliefs` (weighted by scale) and worlds' `domain_expression`.
4. **Luminary evaluation** — runs when `ticks_since_evaluation >= evaluation_interval` (scaled by personality.reactivity, min 5 ticks) or attention crosses a personality-scaled threshold. Reads `pending_attention_triggers` and clears it afterward.
5. **Disposition update** — applies deltas to each Luminary's `Disposition`.
6. **Terminal check** — victory/defeat conditions.

## The Mutation Pattern

**Action handlers never mutate state directly.** `_resolve_intent_mutations` returns a list of `StateMutation` objects; `_apply_mutations` applies them all at the end. Follow this pattern when adding new actions.

`_apply_mutations` routes by `mutation_type` and `target_id`:
- `BELIEF_SHIFT` / `DOMAIN_EXPRESSION` with a civ UUID → `Civilization.dominant_beliefs`
- `BELIEF_SHIFT` / `DOMAIN_EXPRESSION` with a `SignificantLocation` UUID → `location.domain_expression`
- `POP_BELIEF_SHIFT` / `POP_CULTURE_SHIFT` → `Pop.dominant_beliefs` / `Pop.culture_tags`
- `MORTAL_BELIEF_SHIFT` / `MORTAL_CULTURE_SHIFT` → `NotableMortal.belief_tags` / `culture_tags`
- `EVENT_EMITTED` → inserts the `Event` (carried in `m.new_value`) into `state.active_events`; idempotent on duplicate UUID
- All other types — see `_apply_mutations` directly.

**Belief-floor accumulation ("lever C").** `POP_BELIEF_SHIFT`, `POP_CULTURE_SHIFT`, `MORTAL_BELIEF_SHIFT`, and `MORTAL_CULTURE_SHIFT` apply handlers permit *sub-floor* entries to persist **within a tick** (the write gate is `> 1e-5`, not `> BELIEF_FLOOR`). This lets many small same-tick contributions accumulate and cross the floor together. `_prune_weak_beliefs` runs every passive phase and clears Pop/mortal belief & culture entries still below floor. `values:*` culture tags get a `values_stubbornness_factor` dampening (default 0.1).

## Queue Constraints

**One action per `ActionCategory` per tick** (enforced in `_validate_and_filter_queue`). The TUI annotates the action browser with `[used: <name>]` or `[ongoing: <name> (Nx)]` accordingly.

## Ongoing Actions

`SimulationState.ongoing_actions: dict[str, OngoingAction]` keyed by `ActionCategory.value`. Each tick, ongoing actions are appended to `action_queue` before Phase 2; a manually queued action in the same category takes priority for that tick (the ongoing one is blocked but stays registered). `OngoingAction` tracks `ticks_active` (age) and `executed_ticks` (actual runs). Persisted in its own table.

## Active Events

`SimulationState.active_events: dict[str, Event]` holds divine acts whose effects continue across ticks. Inserted via `EVENT_EMITTED`, applied each tick by `_process_active_events`, pruned when expired. Persisted in its own table. `pending_attention_triggers` is transient.

If an Event-emitting action fires while an active event with the same `event_type` and target already exists, no new event is emitted; the existing event's `base_strength` is bumped by +0.05 (capped at 1.0).
