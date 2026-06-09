> [← CLAUDE.md](../../CLAUDE.md)

# Needs & Directives

## Mortal Needs

Each mortal agent carries a `MortalAgentState.needs: list[MortalNeed]`. Six canonical need names are defined in `logic/needs_config.py`:

| Constant | Name | Decay | Pressing | Urgent |
|----------|------|-------|----------|--------|
| `NEED_NOURISHMENT` | `nourishment` | 0.02/tick | < 0.55 | < 0.20 |
| `NEED_HYDRATION`   | `hydration`   | 0.03/tick | < 0.55 | < 0.20 |
| `NEED_SAFETY` | `safety` | 0.01/tick | < 0.50 | < 0.20 |
| `NEED_BELONGING` | `belonging` | 0.04/tick | < 0.65 | < 0.30 |
| `NEED_STATUS` | `status` | 0.03/tick | < 0.60 | < 0.25 |
| `NEED_PURPOSE` | `purpose` | 0.03/tick | < 0.60 | < 0.25 |
| `NEED_LEISURE` | `leisure` | 0.04/tick | < 0.65 | < 0.30 |

### MortalNeed fields

```python
class MortalNeed(BaseModel):
    name: str
    satisfaction: float        # [0, 1]
    decay_rate: float          # subtracted per tick when satiation_hold == 0
    pressing_threshold: float  # satisfaction < this → is_pressing
    urgent_threshold: float    # satisfaction < this → is_urgent
    satiation_hold: int = 0    # ticks remaining where decay is suspended
```

### Trait-modulated profiles

`compute_need_profile(culture_tags: dict[str, float]) -> list[MortalNeed]` (in `needs_config.py`) builds a mortal's starting needs from their `culture_tags`. Each canonical need has a `NEED_TRAIT_MODIFIERS` entry mapping trait keys to `(Δdecay, Δpressing, Δurgent)` tuples. Trait values scale the deltas; results are clamped to sane ranges before construction.

`initialize_mortal_state(mortal)` calls `compute_need_profile` and wraps the result in a `MortalAgentState`.

### Passive restoration (tick_logic Phase 2.55)

Run each tick before decay, for every civilian mortal:

- **Sustenance** — if mortal's current location has `commerce_quality > 0`: +0.03/tick (food/trade access).
- **Safety** — unconditional: +0.02/tick (baseline stability of civilised space).

### Need decay

After passive restore, for each need: if `satiation_hold > 0` decrement it; else `satisfaction -= decay_rate` (floored at 0).

### Satiation hold

Actions that satisfy a need can set `satiation_hold` to suppress decay for several ticks. For example:
- `sell` → `fills_need` need: satisfaction = 1.0, hold = `round(8 * commerce_quality)`
- `spend` → affected needs: satisfaction += gain, hold = `round(8 * commerce_quality)` (if fully satisfied)
- `leisure` → Leisure need: satisfaction += `LEISURE_BASE_GAIN * quality`, hold = `round(6 * quality)`
- `socialize` → Belonging need: satisfaction += `SOCIALIZE_BASE_GAIN * quality`, hold = `round(5 * quality)`
- Directive fulfillment via `sell` → Purpose need: +0.35, hold = 8
- Status recognition via `sell` → Status need: see below
- Status recognition via `socialize` → Status need: see below

---

## Leisure & Socialize Actions

### Leisure

Fires at decision Priority 3 when `leisure` need is pressing and the mortal has a local pop (via `pop_milieu or pop_id`) present in `state.pops`. Cooldown: 3 ticks.

Quality is computed by `_pop_practice_quality(mortal_tags, pop_tags)`:
- Iterates practice tags on the pop (excluding `practice:ritual`, `practice:revelry`)
- Weights each by mortal's corresponding tag preference (defaulting to 0.2)
- Returns weighted average, clamped to [0, 1]

### Socialize

Fires at decision Priority 4 when `belonging` need is pressing, same pop condition. Cooldown: 3 ticks.

Quality is computed by `_pop_social_quality(pop_tags)`:
```
base = pop["values:solidarity"] * 0.5 + pop["practice:revelry"] * 0.5
```
Default values: 0.3 each.

---

## Status Recognition

Status is not self-reported — it is granted by a Pop community noticing a mortal's contribution. Two triggers fire `_status_recognition_from_pop(mortal, local_pop, state, *, strong)` in `logic/tick_logic.py`:

| Trigger | `strong` | Context |
|---------|----------|---------|
| Sell action (after wealth increase) | `True` | Pop whose `PopLocation.wealth` was raised |
| Socialize action (after Belonging) | `False` | Mortal's local pop (`pop_milieu or pop_id`) |

### Relationship tiers

Recognition magnitude scales by the mortal's relationship to the benefited pop:

| Relationship | Sell gain / hold | Socialize gain / hold |
|---|---|---|
| Own pop (`mortal.pop_id == local_pop.id`) | +0.30 / 6 ticks | +0.10 / 3 ticks |
| Linked pop (in `origin_pop.linked_pop_ids`) | `0.30 × link_factor` / 4 ticks | `0.10 × link_factor` / 2 ticks |
| Stranger | +0.05 / 2 ticks | +0.02 / 0 ticks |

The link factor for the linked-pop path is computed by `compute_link_factor(origin_pop, local_pop, base)` from `logic/sim_utils.py`, which incorporates stratum bonus, occupation bonus, and cosine similarity of belief+culture vectors.

### Hold gating

`satiation_hold` is only applied when the resulting `satisfaction >= pressing_threshold` (0.60). A mortal whose Status is very depleted gets the satisfaction gain but not the decay pause — they need another action to push above the threshold before hold kicks in.

---

## Directives

A `Directive` is a standing order issued by a `Pop` to its notable mortals.

```python
class Directive(BaseModel):
    id: UUID
    label: str = ""
    directive_type: str = "commerce"    # "commerce" is the only live type
    target_location_id: Optional[UUID]  # informational; not enforced in Phase 1
    issued_at_tick: int = 0
```

`Pop.active_directives: list[Directive]` — persisted as JSON in the `pops` table.

A mortal knows about a directive through a `DirectiveFact` in their `KnowledgeBase`:

```python
class DirectiveFact(BaseModel):
    fact_type: Literal["directive"] = "directive"
    directive_id: str           # UUID string matching Directive.id
    directive_type: str         # "commerce"
    satisfying_action: str      # "sell"
    target_pop_location_id: str # UUID of the PopLocation whose wealth this grows
    confidence: float = 1.0
    learned_at_tick: int = 0
```

`KnowledgeBase.directive_facts()` returns all facts with `fact_type == "directive"`.

### Directive fulfillment (sell → Purpose)

After a successful sell action in `_tick_civilian_agents`:

1. **Wealth gain** — find the mortal's local pop (`pop_milieu or pop_id`), get its `current_location` (a `PopLocation`), and add `min(0.05, credits_gained * 0.005)` to `pop_loc.wealth`.
2. **Purpose satisfaction** — if the mortal's KB has any `DirectiveFact` with `directive_type="commerce"` and `satisfying_action="sell"`, add 0.35 to the `purpose` need's satisfaction and set `satiation_hold = 8`.

These two effects are independent: wealth always updates on sell (if a pop is found); Purpose only updates if a matching DirectiveFact exists.

### Directive-awareness in the decision loop

When `purpose` is pressing **and** the mortal's KB contains at least one `DirectiveFact`, the civilian decision loop skips leisure and socialize (priorities 3–4) and falls through directly to the collect/travel/sell chain (Priority 2.5 override in `evaluate_civilian_action`). Community obligation takes precedence over personal time. Once Purpose is satisfied after a sell (+0.35, 8-tick hold), leisure and socialize resume normally.

See [agent-system.md](agent-system.md) for the full priority table.

---

## PopLocation Wealth

`PopLocation.wealth: float` (range [0, 1], default 0.5) — a prosperity indicator for that location's Pop community.

### Decay

Each tick in Phase 2.55, for each civilian mortal's home PopLocation:
```
pop_loc.wealth = max(0.0, pop_loc.wealth - 0.005)
```
This only runs for PopLocations tied to a mortal with `civilian_state`. General location-wide decay is a future concern.

### Growth

Sell action: `wealth_gain = min(0.05, credits_gained * 0.005)` added to `pop_loc.wealth`.

### SignificantLocation wealth (computed, not stored)

`compute_world_wealth(world_id, state)` in `logic/sim_utils.py` sums the `wealth` of all child `PopLocation`s for a given `SignificantLocation`. Not persisted.

---

## CollectibleResource

`PopLocation.collectible_resources: list[CollectibleResource]` declares what a location produces when agents collect/forage/hunt there. A location can have multiple resources (e.g., food flora AND potable water).

```python
class CollectibleResource(BaseModel):
    resource_type: str                  # freeform string; drives stockpile/inventory key
    max_yield: float = 1.0              # maximum quantity available per full renewal
    yield_renew_rate: float = 0.2       # fraction of max_yield restored each tick
    current_yield: float = 0.0          # tracks depletion; initializes to max_yield if 0
    cooldown_ticks: int = 3             # per-mortal cooldown (mortal collect only)
    action_types: list[str] = []        # ["forage"], ["hunt"], ["collect"], etc.; [] = any
    biochem_tags: list[str] = []        # species compatibility (see species-biology.md)
```

**Yield renewal (Phase 2.54):** Each tick, `current_yield += yield_renew_rate * max_yield`, capped at `max_yield`. Pops and mortals deduct from `current_yield` when they gather; output is bounded by what's available.

**Action types:** `action_types` controls which actions can use the resource. `["forage"]` means only Pop forage or mortal forage can draw from it. `[]` means any action. Use this to distinguish flora (forage-only), fauna (hunt-only), and labeled mineral/water sources (collect-only).

**Passive sustenance:** Resources are not consumed by explicit "eat" or "drink" actions. Instead:
- Pops: a consumption pass each tick draws `basis:*`-tagged resources from accessible `ResourceStockpile` entries at `pop.current_location` → fills `nourishment`; draws `solvent:*`-tagged resources → fills `hydration`. Access is gated by `can_access_stockpile(pop, stockpile)`.
- Mortals: `_tick_mortal_passive_sustenance` runs a three-source priority — (1) entitled Pop stockpile at current location (scaled by entitlement factor), (2) `MortalInventory`, (3) commerce-quality fallback.

---

## Migration tools

| Script | What it does |
|--------|-------------|
| `tools/migrate_durenn_needs.py` | Replaces Durenn Vail's vestigial needs with canonical 6-need profile; updates `credits.fills_need` |
| `tools/migrate_durenn_directive.py` | Adds a commerce `Directive` to Durenn's Pop; sets `PopLocation.wealth = 0.6`; adds `DirectiveFact` to Durenn's KB |
