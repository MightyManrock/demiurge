# PopAgent System — Design Document

## Context

Pops are sub-civilizational population groups that currently act as passive recipients of Demiurge and Proxius intervention. This design adds autonomous agency: Pops allocate their collective labor across a set of actions each tick, driven by internal need states and influenced by Faction Directives. This is item #4 on the Oros sandbox roadmap, downstream of the resource system (#3).

The player cannot directly control Pop behavior. Influence flows through: Demiurge → Proxii → mortal leaders → Faction Directives → Pop priority vector.

---

## Scope

**In scope:** forage, hunt, collect, commune, revel, enact_rituals, build, fortify, migrate (full resolution); raid, fight, rout (stubs — reserved in priority vector, no resolution until Pop-on-Pop and mortal-on-mortal combat are designed together).

**Out of scope:** combat resolution, tech/surplus bonuses (future), Pop "leak" migration (future).

---

## Data Model

### PopNeed (`core/agent_core.py`)

Parallel to `MortalNeed`. Added to the same file.

```python
class PopNeed(BaseModel):
    name: str
    satisfaction: float = Field(ge=0.0, le=1.0, default=1.0)
    decay_rate: float = 0.02
    pressing_threshold: float = 0.55
    urgent_threshold: float = 0.20
    satiation_hold: int = 0

    @property
    def is_pressing(self) -> bool:
        return self.satisfaction < self.pressing_threshold

    @property
    def is_urgent(self) -> bool:
        return self.satisfaction < self.urgent_threshold
```

### Canonical Pop Needs

| Need | Filled by | Notes |
|---|---|---|
| `sustenance` | forage, hunt, collect | Two-step: actions → stockpile → need |
| `safety` | fortify | Also: migrate away from high-danger locations |
| `cohesion` | commune, revel | |
| `purpose` | enact_rituals, Directive compliance | |
| `shelter` | build | Strong in sedentist Pops |
| `wanderlust` | migrate | Strong in nomadic Pops; near-zero in sedentists |

`shelter` and `wanderlust` are opposed drives modulated by `values:sedentism` in `Pop.culture_tags`:
- High `values:sedentism` → high shelter decay rate, near-zero wanderlust decay rate
- Strong anti-sedentism (low/negative) → inverse

### PopAgentState (`core/agent_core.py`)

```python
class PopAgentState(BaseModel):
    needs: list[PopNeed] = Field(default_factory=list)
    action_priorities: dict[str, float] = Field(default_factory=dict)
    # Recomputed each tick. Sums to 1.0 across all actions.
    fatigue: float = Field(ge=0.0, le=1.0, default=0.0)
    pending_migration_dest: Optional[UUID] = None
    migration_ticks_remaining: int = 0
```

### Pop (`core/universe_core.py`)

New field:
```python
pop_state: Optional[PopAgentState] = None
```

### PopLocation (`core/universe_core.py`)

New field:
```python
resource_stockpile: dict[str, float] = Field(default_factory=dict)
```

### Directive (`core/universe_core.py`)

Two new fields:
```python
action_weight_modifiers: dict[str, float] = Field(default_factory=dict)
# action_name → additive weight delta (positive = boost, negative = malus)
slot_modifier: int = 0
# 0 = no change; +1 = expand active slots by 1; -1 = contract by 1
```

---

## Action Set

### Active Actions

| Action | Primary Need | Output |
|---|---|---|
| `forage` | sustenance (via stockpile) | Flora resources → `resource_stockpile` |
| `hunt` | sustenance (via stockpile) | Fauna resources → `resource_stockpile` |
| `collect` | sustenance or other (via stockpile) | Draws from `PopLocation.collectible_resource` |
| `commune` | cohesion | Direct need satisfaction; boosts nearby mortal belonging quality |
| `revel` | cohesion | Direct need satisfaction (stronger per-tick, less sustained); boosts nearby mortal leisure/expression quality |
| `enact_rituals` | purpose | Direct need satisfaction |
| `build` | shelter | Direct need satisfaction + structural output (future: structures system) |
| `fortify` | safety | Direct need satisfaction + reduces `PopLocation.danger` |
| `migrate` | wanderlust (or safety) | Leg-by-leg movement along TravelNetwork |

### Stub Actions (reserved, no resolution)
`raid`, `fight`, `rout`

### Stratum/Occupation Competency

`competency_modifier` scales action output. Defaults to 1.0; specialists get ~1.5:

| Action | High-competency strata |
|---|---|
| forage, hunt, collect | COMMON, FERAL, WILD |
| build, fortify | ARTISAN |
| enact_rituals | SCHOLAR |
| fortify, (raid, fight, rout stubs) | WARRIOR |
| collect | TRADER |

---

## Priority Vector Computation

Runs each tick, producing `PopAgentState.action_priorities`.

**Pass 1 — Need urgency → raw weights**
Each action gets a raw weight from the urgency of the need(s) it fills. Urgency is continuous — scales from 0 at full satisfaction through pressing threshold to maximum at urgent threshold. Actions sharing a need (forage, hunt, collect all draw from sustenance) split that urgency.

**Pass 2 — Competency scaling**
Each raw weight multiplied by the Pop's `competency_modifier` for that action (from `social_class` and `occupation`).

**Pass 3 — Directive weight modifiers**
Active Directives from `Pop.active_directives` and member Factions' `active_directives` contribute additive deltas from `action_weight_modifiers`. A large enough positive delta can dominate the vector regardless of underlying needs. Negative deltas suppress actions.

**Pass 4 — Normalize**
Sum all weights; divide each by total → distribution summing to 1.0. Stub actions included in vector but always resolve to no output.

---

## Action Slot Cap & Fatigue

### Slot cap
`active_slots = max(2, floor(size_fractional))`

Only the top N actions by weight actually resolve each tick. All weights are computed and stored.

### Directive slot modifiers
Active Directives with `slot_modifier != 0` can expand (+1) or contract (-1) the active slot count. Applied after the size-derived cap, before selecting top-N actions.

**Pop fatigue** (`PopAgentState.fatigue`):
- Increments each tick the Pop acts under a Directive with `slot_modifier != 0`
- Decays when no slot-modifying Directive is active
- At `fatigue == 1.0`: Pop ignores all `slot_modifier` values until fully recovered — it will still respect `action_weight_modifiers` from Directives, just not be pushed beyond/below its natural slot count
- At minimum 2 base slots with `-1` modifier: effectively 1 active slot (full focus on the Directive action)

---

## Resolution & Resource Flows

**Per active action each tick:**
```
output = priority_weight × size_fractional × competency_modifier
```

`size_fractional` used directly as linear productivity scale (avoids million-unit outputs from actual population magnitude).

**Resource-producing actions** (forage, hunt, collect):
- Output deposited to `PopLocation.resource_stockpile[resource_type]`
- Bounded by available yield at location — overexploitation depletes the source before it regenerates

**Direct need-filling actions** (commune, revel, enact_rituals, build, fortify):
- Output scales `PopNeed.satisfaction` directly (capped at 1.0)

**Sustenance — two-step:**
1. forage/hunt/collect → `resource_stockpile`
2. Consumption pass: Pop draws from stockpile → fills `sustenance` need; empty stockpile → need goes unfilled

**Failure modes:**
- Poor priority planning → pressing needs go unfilled
- Overexploitation → local resource depleted, sustenance collapses
- Faction overreach → fatigue blocks slot modifications, Pop returns to natural priorities

---

## Tick Integration

**New Phase 2.6** in `logic/tick_logic.py` (after Phase 2.55 mortal agents). Runs once per Pop with `pop_state`:

1. Decay `PopNeeds` — `satisfaction -= decay_rate` (floor 0)
2. Fatigue update — increment if slot-modifying Directive active; decay otherwise
3. Recompute priority vector (four passes above)
4. Apply slot cap — compute `active_slots`; apply Directive `slot_modifier` if not fatigued; select top-N actions
5. Resolve action outputs — deposits to stockpile; direct need satisfaction
6. Consumption pass — stockpile → sustenance need
7. Narrative events — emit for notable states (pressing sustenance, full fatigue, stockpile depletion, fortification gain)

---

## Migration

When `migrate` is in the active slot set:
- Pop routes leg-by-leg along `TravelNetwork` (same infrastructure as mortal travel; higher tick cost)
- `PopAgentState.pending_migration_dest` holds destination UUID; `migration_ticks_remaining` counts down
- Wanderlust need fills gradually as migration progresses
- Safety-driven migration (fleeing danger) uses same mechanics but is triggered by safety need urgency rather than wanderlust
- Pop can interrupt migration if Directive changes or needs shift

**Future (not in scope):** Large Pops can "leak" toward destination — instantiating a linked child Pop carrying part of the population, enabling caravan/trade-route mechanics. Data model supports this naturally via the existing `linked_pop_ids` field.

---

## Persistence

All new fields follow the standard pattern (add to Pydantic model with defaults, add column to `core/scenario_schema.sql`, load in `utilities/scenario_loader.py` via `row.get()`, export in `utilities/scenario_exporter.py`).

`PopAgentState` serializes as JSON blob on the `pops` table (same pattern as `active_directives`).

`PopLocation.resource_stockpile` serializes as JSON blob on the `pop_locations` table.

---

## Verification

- Unit tests in `tests/test_pop_agent.py`: need decay, priority vector computation (all four passes), slot cap + fatigue interaction, Directive weight and slot modifiers, stockpile depletion → unmet sustenance
- `--autoplay` regression check: existing 50-tick scenarios should not break; Oros scenario (with Pops given `pop_state`) should show emergent priority allocation
- Inspect via Pop detail tab in TUI: `action_priorities`, need satisfaction bars, fatigue level

---

## Files Affected

| File | Change |
|---|---|
| `core/agent_core.py` | Add `PopNeed`, `PopAgentState` |
| `core/universe_core.py` | Add `Pop.pop_state`, `PopLocation.resource_stockpile`; extend `Directive` with `action_weight_modifiers`, `slot_modifier` |
| `core/scenario_schema.sql` | New columns: `pops.pop_state`, `pop_locations.resource_stockpile`, `directives.action_weight_modifiers`, `directives.slot_modifier` |
| `utilities/scenario_loader.py` | Load new fields |
| `utilities/scenario_exporter.py` | Export new fields |
| `logic/tick_logic.py` | Add Phase 2.6 Pop agent resolution |
| `logic/pop_agent_logic.py` | New file: `compute_pop_priorities()`, `resolve_pop_actions()` |
| `logic/needs_config.py` | Add `initialize_pop_state()` parallel to `initialize_mortal_state()` |
| `tests/test_pop_agent.py` | New test file |
