# Belief & Culture Influence Mechanics

_Last updated: 2026-06-01. All rates reference `TickConfig` defaults in `logic/tick_logic.py`._

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
Staggered per civilization: each civ fires on its own tick offset within `civ_conformity_stride` (default **10**), computed as `int(civ.id.int) % stride`. Different civs therefore exert pressure on different ticks.

```
conformity_rate = pop_conformity_base (0.0003)
                × _SCALE_CONFORMITY[civ.scale]   (0.2 nascent → 2.0 intergalactic)
                × civ.health.cohesion
                × stratum_susceptibility_modifier
                × 0.5  (if pop.preaching_imago_id is set)
delta_per_tag = (established_val − pop_val) × conformity_rate × resistance_multiplier
```
Applies to both `dominant_beliefs` (using `established_beliefs`) and `culture_tags` (using `established_culture_tags`).

**`practice:` tags are excluded entirely** from conformity pressure. Practices are things a society wants its different population groups to vary in; institutional enforcement of practice conformity belongs to future Gov/Faction edict mechanics.

#### Conformity resistance ("similar enough" gate)
Each tag's pressure is modulated by a per-tag resistance multiplier based on how close the pop already is to the established value:

```
d = abs(pop_val − established_val)
d_norm = clamp((d − floor) / (ceiling − floor), 0, 1)
resistance_multiplier = d_norm ^ 0.5
```

| Tag type | floor | ceiling | Effect |
|---|---|---|---|
| Domain beliefs | 0.05 | 0.40 | Immune below 0.05; full pressure above 0.40 |
| `religion:` | 0.08 | 0.42 | Slightly higher immunity zone |
| `values:` | 0.15 | 0.45 | Widest immunity zone; values resist institutional pull |
| `practice:` | excluded | — | No conformity pressure at all |

The `^0.5` (square root) exponent gives an asymptotic feel: resistance is still ~71% at the midpoint of the window, rapidly approaching 100% as divergence approaches the floor. The exponent is tunable.

**Stratum susceptibility** (`_STRATUM_SUSCEPTIBILITY`): flat additive modifier to conformity rate.
| Stratum | Modifier | Effect |
|---|---|---|
| `trader` | −0.12 | 12% more open to institutional pull |
| `elite` | −0.06 | 6% more open |
| `scholar` | +0.10 | 10% more resistant |
| `warrior` | +0.15 | 15% more resistant |
| all others | 0.0 | no modifier |

### 4. Periodic cultural noise (`process_pop_cultural_noise`)
Every **89 ticks** (staggered per pop: `int(pop.id.int) % 89`), tiny gaussian noise is applied to all of a pop's `dominant_beliefs` and `culture_tags` (including `practice:` — noise represents organic drift, not institutional pressure).

```
delta = gauss(0, pop_noise_sigma=0.03) clamped to [−pop_noise_cap, +pop_noise_cap=0.25]
```

Most samples are near zero; the cap prevents any single noise event from being significant. Belief inertia (`belief_inertia`) still applies to the resulting mutations. Mutation types are `POP_BELIEF_SHIFT` / `POP_CULTURE_SHIFT`.

### 5. Pop-to-Pop contact (`process_pop_contact`)
Passive belief drift between all co-located pops (same SignificantLocation / world). Staggered per world: each world fires on its own tick offset within `pop_contact_stride` (default **7**), computed from the world's UUID string. Co-prime with `civ_conformity_stride` (10) so the two rarely fire on the same tick for the same world.

```
raw_delta = (a_strength − b_strength) × pop_contact_base_rate (0.00003)
delta = raw_delta × resistance × dist_factor
```

Only affects `dominant_beliefs`, not `culture_tags`.

**Distance factor** (`_pop_distance_factor`): `0.7 ^ |distance_from_core_A − distance_from_core_B|`. Same `PopLocation` → 1.0; one step apart (e.g. surface ↔ orbital) → 0.49; two steps → 0.34; etc.

**Pops on different SignificantLocations never contact each other.**

Link drift (`_process_link_drift`) is also staggered per pop: each pop's links drift on their own offset within `LINK_DRIFT_STRIDE` (17 ticks), computed from `int(pop.id.int) % 17`.

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
| `pop_conformity_base` | 0.0003 | Civ → Pop belief push rate per stride (before scale, cohesion, and resistance) |
| `established_drift_base` | 0.0005 | Rate at which established_beliefs lerps toward dominant_beliefs |
| `pop_contact_base_rate` | 0.00003 | Pop-to-Pop direct contact rate per stride |
| `cross_civ_contact_factor` | 0.15 | Base resistance multiplier for cross-civ contact |
| `cross_civ_scale_penalty` | 0.08 | Per-rank-step penalty added to cross-civ resistance |
| `cross_species_contact_factor` | 0.50 | Resistance multiplier for cross-species contact |
| `cross_stratum_contact_factor` | 0.70 | Per-rank-step resistance multiplier for cross-stratum contact |
| `values_stubbornness_factor` | 0.1 | Extra dampening on `values:*` culture tag changes |
| `peripheral_pop_belief_weight` | 0.25 | Weight of non-core pops in civ aggregate recomputation |
| `peripheral_pop_culture_weight` | 0.25 | Same for culture_tags |
| `civ_conformity_stride` | 10 | Conformity pressure stride (staggered per civ) |
| `pop_contact_stride` | 7 | Pop contact stride (staggered per world) |
| `location_ambient_stride` | 61 | Location ambient influence stride (staggered per world) |
| `pop_noise_sigma` | 0.03 | Std dev for per-pop cultural noise gauss distribution |
| `pop_noise_cap` | 0.25 | Hard clamp on individual noise delta magnitude |

`POP_NOISE_STRIDE = 89` is a module constant (not in TickConfig).

---

## Deferred / TO-PLAN

- **Pop drift baseline ("anchor")**: a per-pop anchor value that each pop slowly fights toward independent of civ or contact influence. Requires additional model plumbing; tracked in TO-PLAN.md.
