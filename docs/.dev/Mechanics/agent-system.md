> [← CLAUDE.md](../../CLAUDE.md)

# Agent System

## Proxii (Implemented)

`core/agent_core.py` holds `ProxiusGoal` and `AgentActionChoice`. `NotableMortal.active_goal: Optional[ProxiusGoal]` carries goal state. `issue_directive` sets a goal; Phase 2.5 resolves one agent turn per active Proxius. Agent actions generate `StateMutation`s the same way action handlers do. `audit_proxius` exposes the full agent state.

`ProxiusDirectiveIntent` and `ProxiusGoal` both carry `culture_vectors` alongside `domain_vectors` — a preach directive applies its framing Imago's `culture:*` riders too. The Proxius bolstering step emits `POP_CULTURE_SHIFT` on the splinter Pop B (and a culture splash back to Pop A), and the splinter-creation step bakes the Imago's culture mechanics into Pop B's starting `culture_tags`.

When a `preach_imago` directive is issued and the chosen Pop A doesn't already have a splinter for the target imago, the UI prompts the player for a name (defaulting to `f"New {pop_a.social_class.value.title()}"`  — the `SocialStratum` value string, e.g. `"New Common"`). The string is carried on `ProxiusDirectiveIntent.goal_pop_name`, copied to `ProxiusGoal.goal_pop_name`, and applied as `Pop.name` on the splinter Pop B the moment it forms.

Demiurge-authored splinters set `Pop.demiurge_authored = True` at creation. The flag grants the player ongoing naming rights via a `[ Rename ]` button in the pop detail tab's header strip. Clicking it opens a `TextFormModal` pre-filled with the current name; clearing the field reverts to the stratum label. Scenario-authored pops always keep `demiurge_authored=False`.

## Mortal Agents (Implemented)

Any `NotableMortal` with a non-None `mortal_state: MortalAgentState` runs as a mortal agent in Phase 2.55 of the tick loop (`_tick_mortal_agents`). Currently only Durenn Vail has this.

### Decision loop (`evaluate_mortal_action`)

`logic/mortal_agent_logic.py` returns one action string per tick, evaluated in priority order:

| Priority | Action | Condition |
|----------|--------|-----------|
| 1 | `sell` | Inventory has a resource with `usable_for=["sell"]` above threshold and `converts_to` set |
| 2 | `spend` | Inventory has credits and a pressing need that spend fills (or any pressing need if `fills_need` is None) |
| 2.5 | *(override)* | `purpose` need pressing **and** KB has a `DirectiveFact` → skip priorities 3–4 entirely |
| 3 | `leisure` | `leisure` need pressing, local pop in `state.pops`, cooldown expired |
| 4 | `socialize` | `belonging` need pressing, local pop in `state.pops`, cooldown expired |
| 5 | `collect` | Known resource locations in KB, mortal at one, cooldown expired; else travel to best resource location |
| — | `idle` | No actionable need or resource |

Travel is triggered inside the collect branch when the mortal isn't already at a resource location. The sell/spend branches also trigger travel when the target location is known but not current.

The Priority 2.5 override ensures a mortal with unfulfilled community obligations (Purpose pressing) doesn't stop to relax — they skip leisure and socializing and proceed directly to the collect/travel/sell chain. Once Purpose is satisfied (post-sell, 8-tick hold), priorities 3–4 resume normally.

`MortalAgentState.last_action: Optional[str]` is set every tick to the action string returned by `evaluate_mortal_action`. Displayed on the mortal detail page for playtest observability.

### KnowledgeBase

`KnowledgeBase.facts: list[KnowledgeFact]` is a discriminated union keyed on `fact_type`:

| Type | Purpose |
|------|---------|
| `location` | Known PopLocation or SignificantLocation |
| `resource` | Known collectible resource at a location |
| `route` | Route tick cost to a destination |
| `location_quality` | Spend or sell quality at a location |
| `directive` | Mortal's encoded knowledge of a Pop Directive (see below) |
| `pop` | Known Pop — novelty tracking (visit count, last interaction tick) |

### Needs → see [needs-and-directives.md](needs-and-directives.md)

### Directives → see [needs-and-directives.md](needs-and-directives.md)

---

## Factions (Implemented)

`Faction` lives in `core/universe_core.py`. It is an institutional interest group that issues `Directive`s to qualifying member mortals.

```python
class Faction(BaseModel):
    id: UUID
    name: str
    description: str
    civilization_id: Optional[UUID]
    member_pop_ids: list[UUID]       # Pops affiliated with the faction
    member_mortal_ids: list[UUID]    # Direct mortal membership (explicit)
    mortal_leader_ids: list[UUID]    # Mortals holding leadership roles
    active_directives: list[Directive]
    visibility: float
    pinned: bool
```

`NotableMortal` carries `faction_ids: list[UUID]` and `led_faction_ids: list[UUID]` — the authoritative membership record. The faction sync pass in tick Phase 2.55 uses `mortal.faction_ids` directly to push `DirectiveFact`s into mortal knowledge bases. See [needs-and-directives.md](needs-and-directives.md) for directive mechanics.

`NetworkCondition.faction_ids` can gate a `TravelNetwork` to members of specific factions. See [travel-networks.md](travel-networks.md).

---

## Pop Agents (Implemented)

Any `Pop` with a non-None `pop_state: PopAgentState` runs as a Pop agent in Phase 2.57 of the tick loop (`_tick_pop_agents` in `logic/tick_logic.py`).

### Priority vector (`PopAgentState.action_priorities`)

Recomputed each tick via `compute_pop_priorities()` in `logic/pop_agent_logic.py`:

1. **Need urgency → raw weights** — urgency from each `PopNeed`'s satisfaction: 0.0 when held (`satiation_hold > 0`); a small background signal proportional to `decay_rate` when satisfied but below 1.0; scales linearly from 0 → 1 between pressing and urgent thresholds; >1 when urgent. Actions that map to the same need share its urgency evenly.
2. **Occupation baseline** — `OCCUPATION_BASELINE_WEIGHTS` table adds a small additive offset (0.1–0.3) to role-appropriate actions (e.g. `clergy → enact_rituals+0.3, commune+0.2`). Applied before competency so it gets amplified by stratum bonuses. Provides meaningful differentiation when all needs are healthy.
3. **Competency scaling** — multiplied by `_COMPETENCY` table keyed on `social_class.value` (WARRIOR → fortify 1.5×; ARTISAN → build 1.5×; SCHOLAR → enact_rituals 1.5×; COMMON/WILD/FERAL → forage/hunt 1.2–1.5×)
4. **Directive weight modifiers** — `Directive.action_weight_modifiers` adds/subtracts from action weights; sourced from `Pop.active_directives` and member Factions' `active_directives`
5. **Normalize** — divide by total to produce distribution summing to 1.0

Stub actions (`raid`, `fight`, `rout`) always have weight 0.0.

### Active slots

`compute_active_slots(pop, factions)` returns `max(2, floor(size_fractional))`, optionally ±1 from `Directive.slot_modifier`. Only the top-N actions by weight resolve each tick. Slot modifications are blocked when `PopAgentState.fatigue == 1.0`.

### Resource stockpile

`PopLocation.resource_stockpile: dict[str, float]` accumulates output from `forage`, `hunt`, and `collect` actions. A consumption pass draws `basis:*`-tagged entries each tick to fill the `nourishment` need and `solvent:*`-tagged entries to fill the `hydration` need.

### Canonical Pop needs

| Need | Filled by | Notes |
|---|---|---|
| `nourishment` | forage, hunt, collect (two-step: → stockpile → passive consume) | Filled from `basis:*`-tagged resources |
| `hydration`   | collect (two-step: → stockpile → passive consume)               | Filled from `solvent:*`-tagged resources; decays ~1.5× faster |
| `safety` | fortify | Also: migrate from high-danger |
| `cohesion` | commune, revel | |
| `purpose` | enact_rituals, Directive compliance | |
| `shelter` | build | High decay in sedentist Pops |
| `wanderlust` | migrate | High decay in nomadic Pops |

See [needs-and-directives.md](needs-and-directives.md) for full initialization details.

---

## Planned

Two-tier resolution split by visibility:
- **Luminaries and Heralds** go through the full `ActionDefinition`/`ActionInstance` machinery — interventions produce footprint, narrative, and attention.
- **Mortals, factions, and Proxii** generate `StateMutation`s more directly — internal politics are invisible state drift until they cross a threshold that surfaces as a narrative event.

**Luminary agency** is a natural extension of `EvaluationEngine` — when disposition sours past a threshold, evaluation flips to active intervention.
