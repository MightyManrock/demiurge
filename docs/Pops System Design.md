# Pops System — Design Document

## Purpose and Overview

Pops replace civilizations as the primary granular unit of sapient (and near-sapient) life in the simulation. Civilizations exist as a higher-level abstraction, but the fine-grained modeling of belief, culture, demographics, and Essence generation happens at the Pop level.

The goal of the Pop system is to make divine influence feel *targeted* rather than abstract — preaching an Imāgō means something specific happens to a specific group of mortals, not just a number incrementing on a civilization panel.

---

## Pop Identity

A Pop is defined by two primary axes:

- **Species**: The biological/sapient species the Pop members belong to.
- **Social stratum or role**: For sapient species, this is social class or occupation (e.g., priestly caste, merchant class, laboring poor, military). For non-sapient species, this is their position in the local hierarchy (e.g., apex predator, herd prey, carrion species).

All members of a Pop share the same species and stratum. Variation in belief, culture, and behavior between members of the same species in the same civilization is what differentiates Pops from each other — two Pops of the same species can coexist in the same location if they have sufficiently different social roles or belief profiles (see Splinter Mechanic below).

---

## Pop Scale (Logarithmic)

Pop size is tracked on a **logarithmic scale** with a fractional component under the hood:

| Displayed Size | Approximate Member Count |
|---|---|
| 1 | A handful (single digits) |
| 2 | Dozens |
| 3 | Hundreds |
| 4 | Thousands |
| 5 | Tens of thousands |
| 6 | Hundreds of thousands |
| 7 | Millions |
| ... | (continues) |

**Implementation note**: The displayed size is an integer, but internally each Pop tracks a fractional size value (e.g., `5.73`). Size-related changes — growth, attrition, splinter poaching — operate on the fractional value. The displayed size steps down only when the fractional value crosses a whole-number threshold. This prevents visually jarring jumps (e.g., a size-6 Pop of millions should not immediately display as size-5 when a tiny splinter of a handful is cut off from it).

---

## Relationship to Civilizations

Civilizations are **broad, high-level abstractions** representing species/technological/cultural clusters. They do not model individual political units or factions — that is the role of Govs and Factions respectively.

A civilization's cultural profile and domain beliefs are **derived aggregates** of its constituent Pops, not independently settable properties. The civilization's expressed traits emerge bottom-up from Pop-level distributions.

Key principles:
- A civilization represents something like a "cultural sphere." All humans on Earth throughout recorded history would constitute approximately one civilization under this model.
- **Pops model the internal variation** within a civilization: different beliefs, practices, and values held by different groups.
- **Govs model political structure**: the governing bodies, institutions, and enforcement mechanisms.
- **Factions model advocacy and action**: entities that push for specific outcomes or behaviors at civilizational scale.

### `dominant_beliefs` vs. `established_beliefs`

A civilization carries two belief profiles:

- **`dominant_beliefs`**: A **derived aggregate** — the size-weighted average of all constituent Pop beliefs. Recomputed from scratch each tick after Phase 2.5 (after agent actions). This is what the simulation reads for domain profiling, Luminary evaluation, and Essence generation.
- **`established_beliefs`**: The **institutional baseline** — what the civilization officially represents, as transmitted through its education, legal frameworks, and cultural institutions. Set at scenario creation from the initial canonical beliefs and updated slowly over time (drifts toward `dominant_beliefs` at a rate proportional to cohesion). The Demiurge can observe this lag.

This distinction is what makes Pull/Push dynamics interesting: when Pops are pushed away from the established profile through divine influence, `dominant_beliefs` drifts, but `established_beliefs` lags behind.

### Stability and Cohesion (Interaction)
- **Stability** reflects how closely `dominant_beliefs` (Pop aggregate) aligns with `established_beliefs` (institutional profile), computed as cosine similarity between the two. When Pop beliefs drift away from the institutional profile — through divine influence, splinters, or organic change — stability decreases. Low stability generates events and slows `established_beliefs` drift. High internal alignment yields high stability regardless of absolute belief content.
- **Cohesion** measures how well the governing Govs align with each other. These are distinct failure modes: a civilization can have unified governance (high cohesion) while its population drifts away from what the government represents (low stability).

---

## Cultural Trait Inheritance

Pops inherit cultural traits from their parent civilization as a **baseline**, but individual Pops deviate from that baseline based on their social role, beliefs, and history.

- A priestly Pop skews toward whatever religious traits the civilization has
- A merchant Pop skews toward commerce and competition
- A Pop that has undergone significant Imāgō influence develops its own distinct profile

This creates a layered system: civilization-level traits represent the dominant or official character, while Pop-level traits represent the actual distribution, which may diverge significantly from the official profile.

---

## Domain Beliefs and Essence Generation

Pops are the **primary source of sapient Essence generation**. Each Pop contributes Essence based on:

1. **The Pop's domain beliefs** (what domains the Pop expresses through its beliefs and practices)
2. **The civilization's scope** — but only as a **multiplier** that applies when the Pop's domain beliefs **match** the civilization's established domain beliefs

This means:
- A large, scope-6 civilization does not grant its scope bonus to a small colony of a few thousand members. The colony's Essence contribution is proportional to its actual population.
- A Pop whose beliefs have drifted away from the civilization's profile does not receive the scope multiplier until the civilization shifts to match — or the Pop is part of a new, smaller civilization whose beliefs already match it.
- The scope multiplier represents institutional reinforcement: educational systems, legal frameworks, cultural transmission mechanisms. A small colony lacks this infrastructure.

Essence from Pop domain beliefs is fed into the **world pool** of the world where the Pop physically resides — not the world of the civilization's origin.

---

## The Splinter Mechanic

A **splinter Pop** is created when a Pop's belief profile diverges far enough from the civilization's `established_beliefs` that a faction breaks away.

### Trigger (Divergence-Based)

Splinters trigger automatically at the end of the passive phase each tick, when:
1. The Pop's cosine distance from `civ.established_beliefs` ≥ `SPLINTER_DIVERGENCE_THRESHOLD` (0.35)
2. The Pop's `size_fractional` ≥ `SPLINTER_MIN_SIZE` (4.0 — roughly "thousands")
3. The Pop has no existing child Pops that haven't themselves splintered (prevents cascade within one tick)

This is a **divergence-threshold model**, not a preaching-driven model. Preaching (Whisper, Omen, Development nudge) pushes Pop beliefs away from `established_beliefs` over time; the splinter fires when the accumulated drift crosses the threshold. The Proxius system is the primary vehicle for driving that drift, but the splinter itself is an emergent consequence of the simulation rather than a direct action outcome.

A future "Preach Imāgō" action may create splinters more directly (see below), but the threshold mechanic will remain the underlying trigger even in that case.

### Creation

When the threshold is crossed, the splinter Pop:
- Inherits the parent Pop's species, social stratum, beliefs, culture tags, and rider traits as a starting point
- Takes **35%** of the parent's `size_fractional` (parent is immediately reduced by this amount)
- Starts at half the parent's visibility, unpinned
- Records its lineage: `parent_pop_id` → parent; parent records the splinter in `child_pop_ids`
- Generates a narrative log entry naming the divergent domain

### Rider Traits and Future Preaching Mechanic

The `rider_traits` field on Pop is reserved for traits introduced specifically through Imāgō preaching. The intent is that a future "Preach Imāgō" action via Proxius will:
- Inject rider traits into the target Pop
- Drive the divergence that eventually triggers the threshold splinter
- Allow the splinter's belief trajectory to differ from the parent's in the specific direction the Imāgō was pointing

Trait attrition (inherited traits fading as rider traits intensify) and competitive size dynamics (splinter growing while parent atrophies) are planned but not yet implemented.

### Size Dynamics (Planned)

The current implementation does an **immediate** size transfer at splinter creation (35% cut). A future pass will replace this with:
- Splinter starts small (size-1 or size-2)
- Gradually **poaches** members from the parent over time based on belief affinity and exposure
- Parent atrophies proportionally rather than taking an instantaneous hit

### Splash Damage

When a divine action targets a mortal, civilization, or world, a fraction of its belief effect ripples to the Pops on that world. This is distinct from the splinter mechanic — splash is a direct belief-delta, not a new splinter:

- **Whisper**: 15% of the whisper's belief delta ripples to Pops on the target mortal's world, distributed proportionally by size among Pops of the same civilization.
- **Omen / Development Nudge**: 20% of the action's domain delta is distributed across all Pops on the target world, weighted **inversely** by size. Smaller Pops (cults, dissident factions, isolated communities) receive proportionally more impact than large ones — they lack the institutional mass to absorb or diffuse divine influence. A `religion:nontheism` culture tag is planned as a future resistance modifier.

This is not the same as the original design's description of splash as "Pops that are not directly targeted may themselves splinter at a reduced rate." That preaching-splash mechanic remains on the roadmap for when the Preach Imāgō action is implemented.

---

## Notable Mortal Generation

Pops and Govs generate notable mortals through different mechanisms, reflecting their different social characters:

### Pop-Generated Notables (Non-Civic)
Emerge from belief, practice, crisis, and cultural conditions within the Pop:
- Religious figures, prophets, mystics
- Folk heroes, rebels, dissidents
- Artists, philosophers, scholars
- Merchants, traders

**Trigger conditions**:
- The civilization's notable mortal count falls below a threshold proportional to its scale (larger civilizations require more notable mortals to feel "populated")
- A Pop experiences significant belief drift or stress
- Events affecting the Pop create narrative openings for notable figures to emerge

### Gov-Generated Notables (Civic)
Emerge from institutional roles and political conditions:
- Political leaders, administrators
- Military commanders, generals
- Judges, legal authorities
- Diplomats, spies

**Trigger conditions**: Similar to Pop-generated, but driven by institutional needs and political events rather than cultural or belief-level changes.

### Latent Notables
Rather than generating notable mortals purely on demand, the system maintains a small pool of **latent notables** within each significant Pop and Gov — figures who exist narratively but have not yet been "surfaced" to the player's awareness. They are revealed through scrying, events, or when circumstances create the narrative hook for them to appear. This avoids the feeling that people spring into existence when observed.

---

## Action Targeting

With Pops implemented, many actions that previously targeted civilizations or worlds will instead target specific Pops:

### Individual Pop Actions
- **Whisper / Shape Dream**: Targets a specific notable mortal within a Pop; other than directly affecting the notable mortal targeted, effects also ripple into the Pop's belief profile
- **Preach Imāgō** (via Proxius): Targets a specific Pop, potentially creating a splinter (note that Pops that are being "actively splintered" cannot be directly targeted in such a way as some sort of daisy-chain splintering)
- **Nudge Probability**: Can target events affecting a specific Pop (though this action will receive a lot more attention later once Events are more mature)

### Group / Institutional Actions
Actions that target multiple similar Pops simultaneously (e.g., "seize the media," "subvert a powerful figure") require different Proxius capabilities:
- **Less charisma-dependent**, more **cunning and political acumen**-dependent
- Reach multiple Pops through the institutional or media channel rather than direct persuasion
- These will be distinct action types rather than scaled versions of individual Pop preaching
- As for now, we will save implementing such actions for later

In addition, actions such as Manifest Omen will no longer target entire civilizations but instead all of the Pops living on a targeted world.

### Penetration vs. Impact
- **Small Pops** (low size): easier to penetrate, less civilizational impact
- **Large Pops** (high size): harder to penetrate, significant civilizational impact when moved
- A highly skilled Proxius (or expanded means) can preach to either larger Pops or multiple similar Pops simultaneously

---

## Govs

Govs are the **political counterpart** to Pops. Where Pops model the beliefs and cultural character of demographic groups, Govs model the governing structures, institutions, and policy-enforcement mechanisms of a civilization.

Govs interact with Pops in the following ways:
- Govs generate **civic notable mortals** (see above)
- **Cohesion** measures how well a civilization's Govs align with each other
- Govs can apply institutional pressure that accelerates or retards Pop belief drift
- Faction dynamics play out partly through Govs, as Factions seek to influence or control governing institutions

Govs are **not** detailed further in this document as they will be designed in conjunction with the Faction system.

---

## Implementation Notes

### State Structure (Implemented)
Pops are stored in a **flat dict** `state.pops: dict[str, Pop]` (str(UUID) → Pop), mirroring the pattern of `state.civilizations` and `state.mortals`. Pops are **not** nested under worlds or civilizations in the state object — they reference their civilization via `civilization_id` and their physical location via `current_location`.

**Spatial layer**: Each inhabited world has one or more `PopLocation` objects (subclass of `Location`, stored in `state.locations`) as children of the `SignificantLocation`. Pops reference these `PopLocation` UUIDs as `current_location`. The `pop_loc_to_world` index (built each tick in Phase 1 and the essence loop) maps PopLocation → parent world for spatial lookups.

Implemented Pop fields:
- `id`, `civilization_id`, `species_id`
- `social_class: Optional[SocialClass]` (sapient) / `wild_stratum: Optional[WildStratum]` (non-sapient); `@property stratum` returns whichever is set
- `size_fractional: float` (internal); `@property size_magnitude: int` (displayed)
- `dominant_beliefs: dict[str, float]`, `culture_tags: dict[str, float]`
- `rider_traits: dict[str, float]` (for future Imāgō preaching effects)
- `parent_pop_id: Optional[UUID]`, `child_pop_ids: list[UUID]` (splinter lineage)
- `notable_mortal_ids: list[UUID]` (reserved for future mortal generation)
- `visibility: float`, `pinned: bool`

### Civilization Aggregation (Implemented)
`civ.dominant_beliefs` is recomputed from scratch each tick by `_recompute_civ_dominant_beliefs()` after Phase 2.5, as the size-weighted average of all constituent Pop beliefs. Entries below `BELIEF_FLOOR` (0.02) are pruned.

Essence generation normalizes each Pop's contribution by `pop.size_fractional / total_civ_size` so that splitting one Pop into multiple Pops does not inflate total Essence output. The scope bonus (civ scale multiplier) scales with `_belief_match()` — the weighted overlap between the Pop's beliefs and `civ.established_beliefs`.

### Implementation Status
**Implemented (Phase 1 + 2):**
- Pop data model, DB schema, save/load round-trip
- Pop-driven Essence generation with size normalization and scope bonus
- `established_beliefs` as a separate institutional profile with drift mechanics
- Civ → Pop conformity pressure; Pop visibility system; Pop discovery in scry
- Pop display in TUI (indented under civilization, gated on visibility)
- Divergence-threshold splinter mechanic
- Splash damage from Whisper, Omen, and Development Nudge actions

**Planned (Phase 3+):**
- Preach Imāgō action (Proxius-mediated, creates splinters via rider traits)
- Gradual size-poaching between parent and splinter (replaces immediate cut)
- Rider trait intensification and inherited trait attrition
- `religion:nontheism` resistance to omen/splash effects
- Action retargeting (player selects a Pop directly as an action target)
- Group/institutional actions targeting multiple Pops simultaneously
- Notable mortal generation linked to Pops
- Gov system (political counterpart to Pops)
