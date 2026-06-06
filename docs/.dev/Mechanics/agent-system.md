> [← CLAUDE.md](../../CLAUDE.md)

# Agent System

## Proxii (Implemented)

`core/agent_core.py` holds `ProxiusGoal` and `AgentActionChoice`. `NotableMortal.active_goal: Optional[ProxiusGoal]` carries goal state. `issue_directive` sets a goal; Phase 2.5 resolves one agent turn per active Proxius. Agent actions generate `StateMutation`s the same way action handlers do. `audit_proxius` exposes the full agent state.

`ProxiusDirectiveIntent` and `ProxiusGoal` both carry `culture_vectors` alongside `domain_vectors` — a preach directive applies its framing Imago's `culture:*` riders too. The Proxius bolstering step emits `POP_CULTURE_SHIFT` on the splinter Pop B (and a culture splash back to Pop A), and the splinter-creation step bakes the Imago's culture mechanics into Pop B's starting `culture_tags`.

When a `preach_imago` directive is issued and the chosen Pop A doesn't already have a splinter for the target imago, the UI prompts the player for a name (defaulting to `f"New {pop_a.social_class.value.title()}"`). The string is carried on `ProxiusDirectiveIntent.goal_pop_name`, copied to `ProxiusGoal.goal_pop_name`, and applied as `Pop.name` on the splinter Pop B the moment it forms.

Demiurge-authored splinters set `Pop.demiurge_authored = True` at creation. The flag grants the player ongoing naming rights via a `[ Rename ]` button in the pop detail tab's header strip. Clicking it opens a `TextFormModal` pre-filled with the current name; clearing the field reverts to the stratum label. Scenario-authored pops always keep `demiurge_authored=False`.

## Mortal Agents (Implemented)

Any `NotableMortal` with a non-None `mortal_state: MortalAgentState` runs as a mortal agent in Phase 2.55 of the tick loop (`_tick_mortal_agents`). Currently only Durenn Vail has this.

### Decision loop (`evaluate_mortal_action`)

`logic/civilian_agent_logic.py` returns one action string per tick, evaluated in priority order:

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

## Planned

Two-tier resolution split by visibility:
- **Luminaries and Heralds** go through the full `ActionDefinition`/`ActionInstance` machinery — interventions produce footprint, narrative, and attention.
- **Mortals, factions, and Proxii** generate `StateMutation`s more directly — internal politics are invisible state drift until they cross a threshold that surfaces as a narrative event.

**Luminary agency** is a natural extension of `EvaluationEngine` — when disposition sours past a threshold, evaluation flips to active intervention.
