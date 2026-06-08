> Plans index: [`docs/plans/PLANS.md`](plans/PLANS.md)
> Items covered by a plan are tagged `→ plan: filename.md`

---

### Pop migration, Faction Directives, and sacred-site mechanics
→ plan: [pop-migration-and-directives.md](plans/pop-migration-and-directives.md)

Full spec in the plan file. Summary of what's covered: real Pop routing using the existing TravelLocation infrastructure; band cascade migration via linked_pop_ids; mortal embedding (mortal travels with their Pop); six Faction Directive types for Pops (`hold_position`, `supply_run`, `pilgrimage`, `patrol`, `raid`, `support_garrison`); location action bonuses on `PopLocation` for sacred sites; mass ritual scaling for co-located Pops; `POP_NEED_PURPOSE` re-activation tied to directive execution. Contested mechanics (raid resistance, thrall capture, path interdiction, charity/appeal) are acknowledged but deferred to Phase 5 pending a conflict layer.

---

### Faction directive refinements

Improvements to Phase 2 directive types identified during Oros playtesting.

**supply_run: smart delivery interval**
Carriers currently run a continuous tight loop regardless of how full the destination stockpile is or how satisfied the destination Pops are. Two tiers of improvement:

- *At-deposit check (no KB required):* on a successful `deposit_cargo`, the carrier is co-located with the destination Pop and has direct access to its stockpile and need state. If both stockpile depth and Pop satisfaction are above a threshold, set a longer `interval_ticks` before the next run — carrier stays home longer, contributing to the local economy rather than making redundant trips. Resets to tight interval when destination dips back below threshold.
- *Pre-travel check (requires Pop KB):* before beginning the outbound leg, carrier checks its KB for the last-known stockpile and need state at the destination. If destination is already well-supplied, skips the trip entirely for this interval. Deferred until Pop KBs exist.

**hold_position: wanderlust relief valve**
`hold_position` currently suppresses migration with a hard −10 modifier, which saturates purpose but lets wanderlust decay unchecked. Two additions:
- Lower wanderlust decay rate significantly while the directive is active — pops that have a place and a role accumulate wanderlust pressure much more slowly.
- Relent when wanderlust reaches urgent: temporarily drop the migration suppression and let the pop wander. Once wanderlust is satisfied, issue a "return home" summons — `pending_migration_dest` is set back to `target_location_id` and migration priority boosted until the pop returns. Directive resumes suppression on arrival.

Note: directive priority ordering matters here. A supply_run carrier that also has hold_position should not have the relent logic fire mid-circuit; in-progress supply_run should take precedence.

**resupply directive** (new type)
Need-triggered reactive resupply, distinct from the continuous `supply_run`. Intended for bands in resource-scarce locations (e.g. Dunes of Tor) that need to periodically top up from a richer nearby source.

Trigger condition: any sustenance need (`nourishment`, `hydration`) at pressing threshold AND local `ResourceStockpile` below a low-water mark. Fields: `target_location_id` (the resupply source), `return_location_id` (home base), `cargo_manifest` (what to collect).

Four-phase loop:
1. Trigger fires → travel to `target_location_id`.
2. Dwell at source until all sustenance needs reach 1.0 AND `CargoStockpile` is full per `cargo_manifest`. Purpose held at a moderate value during dwell (pop is on a meaningful errand, not idle).
3. Load cargo from source stockpile.
4. Travel home → deposit cargo to home `ResourceStockpile`. Purpose tops off on successful deposit.

Directive sleeps (no-op) until trigger conditions are met again. Unlike `supply_run`, this is self-scheduling — it only activates when genuinely needed.

---

### Thrall capture

When a raid succeeds against a sufficiently weakened Pop, a fraction of that Pop's population is extracted — either absorbed into the raiding Pop, added to a new subjugated Pop in the raider's Faction, or held as a distinct enslaved-stratum Pop at the raider's home location. Requires: on-demand pop-splitting (not just divergence-driven), a `subjugated_by: Optional[UUID]` relationship field on Pop, and a `captive` or `thrall` SocialStratum value. Deferred until contested raid mechanics (Phase 5 of pop-migration-and-directives.md) exist.

---

### Nomadic ranging patterns

Beyond simple migration, nomadic bands should follow seasonal or resource-driven *circuits* — a repeating sequence of locations rather than a one-off move. Mechanically: a `patrol` directive already covers some of this, but true nomadism needs a `circuit: list[UUID]` field on Directive (ordered stops with optional dwell-ticks at each) and a `circuit_position: int` tracking current leg. The band advances to the next stop when dwell ticks expire or resources drop below a threshold. Deferred until basic Pop migration (Phase 1) and Directive infrastructure (Phase 2) are in place.

---

### Charity and appeal between Pops

A resource-poor Pop arriving at a wealthy Pop's location should be able to appeal for a resource transfer, with success gated by faction relationship and target surplus. Distinct from raid: appeal is voluntary on the target's part, costs no `danger`, and succeeds based on `linked_pop_ids` / shared Faction membership. Failed appeal with a hostile Pop could trigger a raid instead. Requires Pop migration and stockpile ownership semantics (see resource system deferred expansions).

---

### Rewrite Ledger and the Ash Luminary constraints

The current NarrativeConstraints in the scenario read as domain evaluation preferences
(e.g. "allow Decay to spread," "maintain hierarchy") rather than genuine constraints on
the Demiurge's behavior. Good constraints should impose tension — directives that require
active effort or restrict the player's freedom in ways that aren't just "score points in
my domain." They should also not reference specific mortal factions by name; Luminaries
operate at cosmological scale and are indifferent to mortal politics.

Rewrite all six NarrativeConstraints from scratch with this principle in mind.

---

### MortalAsset subtype canonization

`MortalAsset` is a generic flat model. As vehicle-specific properties accumulate, it needs typed subtypes — `VehicleAsset` is the first candidate:
- `cargo_capacity` is already a field sitting on the generic class that belongs specifically on vehicles
- `NetworkCondition.asset_type: str` will eventually need to specify required travel capability (sublight vs. warp, ship vs. ground vehicle) rather than a freeform string
- Other asset types may emerge as the system grows (permissions, structures, instruments)

Hold until vehicle properties multiply further.

---

### Resource system: deferred expansions

Future work building on the resource system plan (`2026-06-07-resource-system.md`). Each item below is a distinct plan candidate:

**Environment-dependent resource decay**
Resources in `ResourceStockpile` and `MortalInventory` should decay over time at rates that vary by environment. The model: `Resource.decay_rate` carries a base rate (already stubbed as `decay_rate: float = 0.0`); a `SignificantLocation` (world/planet) carries `resource_decay_modifiers: dict[str, float]` scaling base rates for its environment; `PopLocation` can override the parent world's modifier locally (e.g., a preserving cave vs. a hot open desert on the same planet). Decay runs as a tick phase over all stockpiles and inventories. What decays is environment-specific — organic food rots in carbon-water worlds; metals corrode in sulfuric-acid worlds like Kiddis; silicon-based foodstuffs may be stable indefinitely in the right conditions.

**ResourceStockpile shared-ownership system**
→ plan: [pop-migration-and-directives.md](plans/pop-migration-and-directives.md) (Phase 0)
`resource_stockpile` on `PopLocation` is currently a `dict[str, float]` with no ownership semantics. The intended design is a `ResourceStockpile` object with explicit ownership: which Pops or factions hold shares, how contributions and withdrawals are tracked, and how ownership is distributed when Pops migrate or diverge.

**Species-specific consumption enforcement**
`species_can_consume()` exists in `agent_core.py` but is not wired into either the Pop or mortal passive consumption passes. A mortal or Pop currently consumes any `basis:*`-tagged resource regardless of their species' `life_basis`. Consumption passes should check `species_can_consume()` before drawing — which requires `species` to be resolvable from the consuming entity at tick time.

**Stockpile draw rate limits**
The `entitlement_resolver` grants mortals access to Pop stockpiles but imposes no cap on per-tick draw volume. A drain-prevention mechanic is needed — likely a per-mortal ration rate proportional to Pop size or stockpile depth, scaled by entitlement factor.

**Mortal inventory capacity / encumbrance**
`MortalInventory` has no capacity limit; mortals who forage and hunt could accumulate resources indefinitely. A capacity model (weight- or slot-based) would gate this and connect naturally to `MortalAsset` vehicle cargo capacity once that is formalized.

**KnowledgeBase on PopAgentState**
`PopAgentState` has no `KnowledgeBase`; Pops currently have omniscient access to all `CollectibleResource` objects at their current `PopLocation` and no awareness model for other locations. Add `knowledge_base: KnowledgeBase = Field(default_factory=KnowledgeBase)` to `PopAgentState`, with loader/exporter/schema support. Once present, the KB can gate resource-aware travel decisions (a Pop should only migrate toward a resource-rich location it actually knows about) and support the same seeding/discovery mechanics that mortals already have.

**Unified directive targeting and Pop/mortal KB propagation**
Currently pops and mortals receive faction directives through different mechanisms: pops via an inline filter in `_collect_directive_modifiers` (checking `territory_pop_ids`), mortals via `_sync_faction_directives` which projects faction directives into their KB as `DirectiveFact` objects each tick. The intended unified design:

- Rename `territory_pop_ids` → `target_member_ids: list[UUID]` on `Directive`, covering both pop and mortal UUIDs. Empty = all faction members of either type.
- Add a `_sync_faction_directives_to_pops` pass (mirrors the mortal version) that pushes all faction directives into each member Pop's KB each tick.
- Pop agent reads from KB rather than walking raw directive lists. Checks `target_member_ids` to determine whether to follow; if not in the list, the directive is "known but not followed" — stored in KB for potential future use (resentment, drift, morale effects).
- Mortal side: same "known but not followed" distinction should apply. Currently all faction directives are injected unconditionally.
- Prerequisite: Pop KB (see above).

**Move mortal KnowledgeBase and MortalAssets onto MortalAgentState**
`NotableMortal.knowledge_base` currently lives on the mortal model itself rather than on `MortalAgentState`. Agent-runtime state (KB, needs, desires, cooldowns) should be colocated. Moving it to `MortalAgentState` requires updating every reference to `mortal.knowledge_base` across tick_logic, mortal_agent_logic, loader, and exporter. Similarly, `NotableMortal.assets: list[MortalAsset]` belongs on `MortalAgentState` — parallel to how `PopAgentState.cargo: CargoStockpile` holds the Pop's mobile inventory. Low urgency but the right home for both.

**Scale CargoStockpile capacity with Pop size**
`CargoStockpile` on `PopAgentState` currently uses fixed defaults (`max_slots: int = 4`, `slot_capacity: float = 20.0`). A larger Pop should be able to carry proportionally more. The model: `max_slots` and/or `slot_capacity` should be derived from `pop.population` at state initialization time (and recomputed when population changes significantly). Exact scaling law TBD — linear, stepped, or logarithmic are all viable.

**Seed Pop knowledge into Oros test sandbox**
Once Pop KBs exist, the Oros sandbox Pops start with empty KBs and have no awareness of locations outside their current one. Seed directional knowledge (routes, resource-rich destinations) into Pops that would plausibly know about nearby locations — nomadic bands know their circuits, Hiparunites know the Rift and Ulum Highlands, etc. Mirrors the mortal KB seeding already done for the sandbox.

**Resource-scarcity-driven Pop migration**
Persistent unmet `nourishment` or `hydration` needs should create migration pressure beyond the general `wanderlust` need. Pops unable to sustain themselves at their current location should seek resource-rich destinations. Requires routing logic to be aware of resource availability at destination PopLocations.

**Resource trade and market economy**
`Resource.base_value` and `Resource.converts_to` are already stubbed in the model, anticipating a sell/trade system. Full design: mortals sell resources at locations with market infrastructure; Pops trade stockpile surpluses with linked Pops; `base_value` drives pricing and `converts_to` enables commodity chains (raw ore → refined metal). Likely a large standalone plan.

---

### Occupation-based action return bonuses

`Occupation` enum and `SocialStratum` rename are complete. The remaining piece: action output modifiers (forage/hunt/collect yield, etc.) are currently keyed on social stratum. Shift the primary modifier to occupation — a farmer gets a larger forage bonus than a warrior, a scholar gets a knowledge-action bonus, etc. Stratum modifiers remain but are smaller and more generic; the two stack. Requires auditing every place `social_class` is used to compute output or priority and replacing or supplementing with an occupation lookup table.

The `OCCUPATION_BASELINE_WEIGHTS` table in `logic/pop_agent_logic.py` provides a natural starting reference for which occupations should receive which action bonuses.

---

### Random playtest notes

1. Luminaries are practically absent. It seems like you don't hear from them unless you go out of your way to talk to them. Granted, before the RTwP aspect was introduced, they pestered you **constantly**, but we may have to adjust the mechanics of it to find a happy medium. We could have them guaranteed to audit you within the first three months, after which they'll set intervals according to what they find in that audit and on their personalities. Perhaps they could also notice more by having their `attention` slowly rise — or even randomly for more mercurial Luminaries. Either way, there isn't that **dread** of a Luminary report that I want to be there.

2. Speaking of Luminary audits, footprint scores fall **way** too fast. They should be something that you pump up when you don't think Luminaries who care about particular categories are watching — and then worry about whether they'll go down in time before a Luminary audit comes in or a Luminary starts taking notice. It would be interesting if decay weren't linear — the higher it reaches, the longer it takes to fall. This could lead to several tactics: using Luminary interactions to try to trigger an audit so that you have breathing room afterwards, before the next audit comes; perhaps there could be a Proxius Directive to "clean up" a stubborn local footprint in specific locations, with the goal of reducing your universal footprint in that category.

---
### Human-readable Documentation
> → plan: [human-readable-docs.md](plans/human-readable-docs.md)

Especially since I have started sharing my game with friends, it is **very** clear that the only guide to how to play this game exists in my head. And now that my docs are moving with the repo, that is one area to address this.

I would like to start putting together a source about how the game works and how to go about playing it. This will include an introduction/tutorial as well as "non-codey" descriptions of the game's systems. Players who read this should come away with a good idea of what they can expect to see and how to interact with it.

In the future, we will fold a lot of this information into a redesign of the Divine Wisdom tab in-game. Ideally, that will become a definitive encyclopedia on Demiurge, with a navigable interface of its own—and possibly a search function, if possible.

---

### Mortal ritual + Imāgō system integration

Currently the Imāgō system is exclusively a Demiurge tool — mortal priests can perform the `ritual` action, but it has no mechanical connection to Imāginēs. The intended expansion: priests should be able to invoke specific Imāginēs as part of their ritual practice, allowing belief effects, domain expression, and possibly revelation to propagate through mortal religious activity without any direct Demiurge involvement.

This gives the Imāgō system a bottom-up path alongside the top-down Demiurge-authored one. Priests in high-belief locations could sustain and amplify Imāgō influence through their own rituals; the Demiurge could cultivate this as a passive force multiplier that keeps working between ticks.

Design questions to resolve before planning: how priests discover which Imāginēs are available to them (belief threshold? explicitly revealed by the Demiurge?); what ritual actions trigger which Imāgō effects; and how mortal-driven Imāgō expression differs mechanically from Demiurge-driven (lower magnitude? less directional control? different domain profile contribution?).

---

### Broader tick_logic.py decomposition

`logic/tick_logic.py` has grown very large and handles too many concerns in one file. Once the belief propagation extraction (→ plan: belief-propagation.md) is complete, do a systematic pass to identify other self-contained subsystems that can safely be extracted into their own modules under `logic/`. Candidates include: essence generation, splinter logic, civilian agent tick, visibility/decay, and the evaluation engine call-out. Each extraction should be a clean mechanical move (no behavioral changes) committed separately, with tick_logic.py's call sites updated to import from the new module.

**Status (2026-05-29):** First wave complete. Extracted: `belief_propagation`, `essence_generation`, `visibility_logic`, `proxius_logic`, `sim_utils`. Pop splinter check wrapped into `_check_pop_splinters()`. Remaining large blocks: `_resolve_intent_mutations` (~2000 lines) and `_apply_mutations` (~2500 lines).

---

### Intent resolution and mutation dispatch redesign

`_resolve_intent_mutations` and `_apply_mutations` together account for ~4500 lines in `tick_logic.py` and are the last major extraction blockers. A clean extraction requires rethinking their design rather than a mechanical move:

- **Intent resolution**: each intent branch is currently an `if/elif` arm in one giant function. A self-registering pattern (each intent type registers a handler function in a dict, dispatched by intent class) would let handlers live in per-intent modules or a dedicated `logic/intent_handlers/` package. Prerequisite: audit what helpers each branch calls and identify which need to move to shared locations first.

- **Mutation dispatch** (`_apply_mutations`): tightly coupled to every model type and `MutationType`. Worth exploring a visitor/protocol pattern where each model handles its own mutation types, reducing the central dispatch to a thin router.

- **Shared prerequisite**: `NarrativeEvent` currently lives in `tick_logic.py`. Any extraction that produces narrative events needs it moved to `core/` first.

Defer until there's a functional reason to touch these (e.g., adding a new intent type or mutation type that makes the current structure painful).

---

