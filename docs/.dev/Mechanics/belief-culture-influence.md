# Belief & Culture Influence Mechanics

_Last updated: 2026-05-29. All rates reference `TickConfig` defaults in `logic/tick_logic.py`._

---

## Data model

### Pop
| Field | Type | Range | Notes |
|---|---|---|---|
| `dominant_beliefs` | `dict[str, float]` | `[BELIEF_FLOOR, BELIEF_CAP]` = `[0.02, 0.90]` | Domain beliefs. Pruned below floor each passive phase. |
| `culture_tags` | `dict[str, float]` | `religion:` → `[0, 1]`; `values:` and `practice:` → `[-1, 1]`; others → `[0, 1]` | Culture traits. Signed tags represent bipolar stances. Pruned below `CULTURE_FLOOR = 0.01` (abs). |
| `rider_traits` | `dict[str, float]` | `[0, 1]` | Temporary culture overlays from Imago nodes; decay each tick. |

### Civilization
| Field | Type | Notes |
|---|---|---|
| `dominant_beliefs` | `dict[str, float]` | Instantaneous size-weighted average of all pop `dominant_beliefs`. Fully recalculated every tick. |
| `established_beliefs` | `dict[str, float]` | Institutional anchor. Lags behind `dominant_beliefs` via a lerp. Pops are pushed toward this, not toward `dominant_beliefs` directly. |
| `culture_tags` | `dict[str, float]` | Instantaneous size-weighted average of all pop `culture_tags`. Fully recalculated every tick. |
| `established_culture_tags` | `dict[str, float]` | Institutional anchor for culture. Lags behind `culture_tags` via the same lerp. |

Peripheral pops (on `PopLocation`s whose parent world is not in `civ.core_locs`) are weighted at `peripheral_pop_belief_weight = 0.25` and `peripheral_pop_culture_weight = 0.25` of their `size_fractional` in these averages.

---

## Influence pathways

### 1. Pop → Civ aggregate (`recompute_civ_dominant_beliefs` / `recompute_civ_culture_tags`)
Called once per tick. **Fully overwrites** `civ.dominant_beliefs` and `civ.culture_tags` as weighted averages. There is no smoothing here — the aggregate is always the exact current mean of all pops.

Each pop's contribution is weighted by `size_fractional × stratum_influence_weight × peripheral_factor`. The **stratum influence weight** (`_STRATUM_INFLUENCE_WEIGHT`) gives politically prominent strata outsized representation:

| Stratum | Weight |
|---|---|
| `elite` | 2.0 |
| `scholar` | 1.8 |
| `warrior` | 1.5 |
| `trader` | 1.2 |
| `artisan` | 1.1 |
| `common` | 1.0 |
| `underclass` | 0.8 |
| `feral` | 0.4 |
| `wild` | 0.1 |

### 2. Civ aggregate → Civ established beliefs (institutional lag)
```
established_rate = established_drift_base (0.0005) × civ.health.cohesion
delta_per_tag = (dominant_val − established_val) × established_rate
```
`civ.established_beliefs` lerps toward `civ.dominant_beliefs` each tick. At cohesion = 1.0, the half-life of a gap is roughly 1,400 ticks (~3.8 years at 1 tick/day). The same rate governs `established_culture_tags` drifting toward `culture_tags`.

### 3. Civ established beliefs → Pops (conformity pressure, `civ_conformity_pressure`)
Fires every `civ_conformity_stride` ticks (default **10**).

```
conformity_rate = pop_conformity_base (0.0003)
                × _SCALE_CONFORMITY[civ.scale]   (0.2 nascent → 2.0 intergalactic)
                × civ.health.cohesion
                × stratum_susceptibility_modifier
                × 0.5  (if pop.preaching_imago_id is set)
delta_per_tag = (established_val − pop_val) × conformity_rate
```
Applies to both `dominant_beliefs` (using `established_beliefs`) and `culture_tags` (using `established_culture_tags`).

**Stratum susceptibility** (`_STRATUM_SUSCEPTIBILITY`): flat additive modifier to conformity rate.
| Stratum | Modifier | Effect |
|---|---|---|
| `trader` | −0.12 | 12% more open to institutional pull |
| `elite` | −0.06 | 6% more open |
| `scholar` | +0.10 | 10% more resistant |
| `warrior` | +0.15 | 15% more resistant |
| all others | 0.0 | no modifier |

### 4. Pop-to-Pop contact (`process_pop_contact`)
Passive belief drift between all co-located pops (same SignificantLocation / world). Fires every `pop_contact_stride` ticks (default **7**). Co-prime with `civ_conformity_stride` (10) so the two rarely fire on the same tick.

```
raw_delta = (a_strength − b_strength) × pop_contact_base_rate (0.00003)
delta = raw_delta × resistance × dist_factor
```

Only affects `dominant_beliefs`, not `culture_tags`.

**Distance factor** (`_pop_distance_factor`): `0.7 ^ |distance_from_core_A − distance_from_core_B|`. Same `PopLocation` → 1.0; one step apart (e.g. surface ↔ orbital) → 0.49; two steps → 0.34; etc.

**Pops on different SignificantLocations never contact each other.**

---

## Resistance system (`_pop_contact_resistance`)

Applies to Pop-to-Pop contact only (not civ conformity). Returns a multiplier in `[0.0, 1.0]`.

| Factor | Condition | Multiplier |
|---|---|---|
| Cross-civ | different `civilization_id` | × `cross_civ_contact_factor` (0.15) |
| Scale gap penalty | per rank of gap between civ scales | × `max(0.05, 1.0 − gap × 0.08)` per gap step |
| Cross-species | different `species_id` | × `cross_species_contact_factor` (0.50) |
| Cross-stratum | per stratum rank step apart | × `cross_stratum_contact_factor (0.70) ^ distance` |
| Size ratio | smaller source → less sway | × `min(1.0, src_size / tgt_size)` |
| Stratum susceptibility | flat modifier on total resistance | × `(1.0 + susceptibility)` |

Civ scale ranks (for gap penalty): `pre_sapient=0, nascent=1, tribal=2, city_state=3, regional=4, continental=5, planetary=6, interplanetary=7, interstellar=8, intergalactic=9`.

**Example — two Naran pops, same civ, same species, one stratum apart:**
`resistance = 1.0 × 1.0 × 0.70 × (size_ratio)`. A large pop (sz=9) receiving from a small pop (sz=3): `0.70 × 0.33 = 0.23`. Final delta ≈ `(gap) × 0.00003 × 0.23`.

**Example — cross-civ, same species, same stratum (e.g. Naran vs Surathi on Sethis):**
`resistance = 0.15 × scale_gap_penalty × 1.0 × size_ratio`. Planetary vs city-state (3 ranks): `0.15 × max(0.05, 1.0 − 3×0.08) = 0.15 × 0.76 = 0.114`.

---

## Belief inertia (`_belief_inertia`)

Applied to most belief/culture mutations to slow changes at extremes. Returns a `[0.0, 1.0]` multiplier.

| Zone | Condition | Multiplier |
|---|---|---|
| High, pushing up | current ≥ 0.7, delta > 0 | linear 1.0 → 0.40 as current → 0.9 |
| High, pushing down | current ≥ 0.7, delta < 0 | linear 1.0 → 0.65 at 0.9 (entrenched but movable) |
| Low, pushing up | current < 0.2, delta > 0 | linear 0.65 → 1.0 as current → 0.2 (unfamiliar idea friction) |
| Floor, pushing down | current ≤ 0.1, delta < 0 | linear 0.75 → 1.0 as current → 0.1 (tiny remnants cling) |
| Mid range | 0.2 – 0.7 | 1.0 |

For signed (`values:`, `practice:`) tags, `abs(current)` is passed as the `current` argument, so negative values receive the same inertia treatment as positive ones of equal magnitude.

---

## Culture tag specifics

### Signed tags
`values:` and `practice:` tags are clamped to `[-1.0, 1.0]`. Negative values represent the opposing cultural stance (e.g. negative `values:hierarchy` = active egalitarianism; negative `practice:music` = active suppression of music). `religion:` tags remain `[0, 1]`.

### `values:` stubbornness
All `POP_CULTURE_SHIFT`, `MORTAL_CULTURE_SHIFT`, and `CIV_ESTABLISHED_CULTURE_SHIFT` mutations targeting a `values:*` tag receive an additional dampening factor:
```
delta *= max(0.05, 1.0 − values_stubbornness_factor (0.1))
```
i.e., values tags shift at ~90% the rate of other culture tags.

### Alias expansion
When a mutation targets a legacy tag (e.g. `structure:hierarchy`, `practice:sedentism`), `expand_culture_tag()` fans it out to canonical targets with adjusted deltas before applying. See `utilities/culture_registry.py: CULTURE_TAG_ALIASES`.

### Rider traits
`rider_traits` are a temporary culture overlay from active Imago nodes. They decay each tick based on `RIDER_ATTRITION_BASE (0.00002)` modulated by culture synergy: positively synergistic culture tags slow decay; negatively synergistic ones accelerate it.

---

## Pop splinter (`_check_pop_splinter`)

Runs after conformity pressure each tick. A pop splinters when:
- `size_fractional ≥ SPLINTER_MIN_SIZE` and has no existing children
- Its `dominant_beliefs` diverge sufficiently from `civ.established_beliefs` (measured by the most-divergent tag)

The splinter inherits belief and culture tags from the parent and is assigned to the same location and civ. It thereafter evolves independently.

---

## Lineage bleed

When a pop's beliefs shift (from whispers, culture shifts, etc.), `LINEAGE_BLEED_FRACTION (0.20)` of each delta bleeds to its parent and children pops. Moderated by cosine similarity — pops whose beliefs have already diverged resist the bleed.

---

## All relevant `TickConfig` values

| Field | Default | Notes |
|---|---|---|
| `pop_conformity_base` | 0.0003 | Civ → Pop belief push rate per tick (before scale and cohesion) |
| `established_drift_base` | 0.0005 | Rate at which established_beliefs lerps toward dominant_beliefs |
| `pop_contact_base_rate` | 0.00003 | Pop-to-Pop direct contact rate per tick |
| `cross_civ_contact_factor` | 0.15 | Base resistance multiplier for cross-civ contact |
| `cross_civ_scale_penalty` | 0.08 | Per-rank-step penalty added to cross-civ resistance |
| `cross_species_contact_factor` | 0.50 | Resistance multiplier for cross-species contact |
| `cross_stratum_contact_factor` | 0.70 | Per-rank-step resistance multiplier for cross-stratum contact |
| `values_stubbornness_factor` | 0.1 | Extra dampening on `values:*` culture tag changes |
| `peripheral_pop_belief_weight` | 0.25 | Weight of non-core pops in civ aggregate recomputation |
| `peripheral_pop_culture_weight` | 0.25 | Same for culture_tags |
| `civ_conformity_stride` | 10 | Conformity pressure fires every N ticks |
| `pop_contact_stride` | 7 | Pop contact fires every N ticks |

---

## Deferred / TO-PLAN

- **Pop drift baseline ("anchor")**: a per-pop anchor value that each pop slowly fights toward independent of civ or contact influence. Requires additional model plumbing; tracked in TO-PLAN.md.
