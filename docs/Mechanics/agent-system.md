> [← CLAUDE.md](../../CLAUDE.md)

# Agent System

## Proxii (Implemented)

`core/agent_core.py` holds `ProxiusGoal` and `AgentActionChoice`. `NotableMortal.active_goal: Optional[ProxiusGoal]` carries goal state. `issue_directive` sets a goal; Phase 2.5 resolves one agent turn per active Proxius. Agent actions generate `StateMutation`s the same way action handlers do. `audit_proxius` exposes the full agent state.

`ProxiusDirectiveIntent` and `ProxiusGoal` both carry `culture_vectors` alongside `domain_vectors` — a preach directive applies its framing Imago's `culture:*` riders too. The Proxius bolstering step emits `POP_CULTURE_SHIFT` on the splinter Pop B (and a culture splash back to Pop A), and the splinter-creation step bakes the Imago's culture mechanics into Pop B's starting `culture_tags`.

When a `preach_imago` directive is issued and the chosen Pop A doesn't already have a splinter for the target imago, the UI prompts the player for a name (defaulting to `f"New {pop_a.social_class.value.title()}"`). The string is carried on `ProxiusDirectiveIntent.goal_pop_name`, copied to `ProxiusGoal.goal_pop_name`, and applied as `Pop.name` on the splinter Pop B the moment it forms.

Demiurge-authored splinters set `Pop.demiurge_authored = True` at creation. The flag grants the player ongoing naming rights via a `[ Rename ]` button in the pop detail tab's header strip. Clicking it opens a `TextFormModal` pre-filled with the current name; clearing the field reverts to the stratum label. Scenario-authored pops always keep `demiurge_authored=False`.

## Planned

Two-tier resolution split by visibility:
- **Luminaries and Heralds** go through the full `ActionDefinition`/`ActionInstance` machinery — interventions produce footprint, narrative, and attention.
- **Mortals, factions, and Proxii** generate `StateMutation`s more directly — internal politics are invisible state drift until they cross a threshold that surfaces as a narrative event.

**Factions** need a new `Faction` model in `core/universe_core.py` (strength, goals, mortal/world links). This is the primary data-modelling prerequisite before expanding the agent phase. **Luminary agency** is a natural extension of `EvaluationEngine` — when disposition sours past a threshold, evaluation flips to active intervention.
