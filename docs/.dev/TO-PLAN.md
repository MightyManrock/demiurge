> Plans index: [`docs/plans/PLANS.md`](plans/PLANS.md)
> Items covered by a plan are tagged `→ plan: filename.md`

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
`resource_stockpile` on `PopLocation` is currently a `dict[str, float]` with no ownership semantics. The intended design is a `ResourceStockpile` object with explicit ownership: which Pops or factions hold shares, how contributions and withdrawals are tracked, and how ownership is distributed when Pops migrate or diverge.

**Species-specific consumption enforcement**
`species_can_consume()` exists in `agent_core.py` but is not wired into either the Pop or mortal passive consumption passes. A mortal or Pop currently consumes any `basis:*`-tagged resource regardless of their species' `life_basis`. Consumption passes should check `species_can_consume()` before drawing — which requires `species` to be resolvable from the consuming entity at tick time.

**Stockpile draw rate limits**
The `entitlement_resolver` grants mortals access to Pop stockpiles but imposes no cap on per-tick draw volume. A drain-prevention mechanic is needed — likely a per-mortal ration rate proportional to Pop size or stockpile depth, scaled by entitlement factor.

**Mortal inventory capacity / encumbrance**
`MortalInventory` has no capacity limit; mortals who forage and hunt could accumulate resources indefinitely. A capacity model (weight- or slot-based) would gate this and connect naturally to `MortalAsset` vehicle cargo capacity once that is formalized.

**Resource-scarcity-driven Pop migration**
Persistent unmet `nourishment` or `hydration` needs should create migration pressure beyond the general `wanderlust` need. Pops unable to sustain themselves at their current location should seek resource-rich destinations. Requires routing logic to be aware of resource availability at destination PopLocations.

**Resource trade and market economy**
`Resource.base_value` and `Resource.converts_to` are already stubbed in the model, anticipating a sell/trade system. Full design: mortals sell resources at locations with market infrastructure; Pops trade stockpile surpluses with linked Pops; `base_value` drives pricing and `converts_to` enables commodity chains (raw ore → refined metal). Likely a large standalone plan.

---

### Canonize occupation; rename SocialClass → SocialStratum; occupation-based action bonuses

Three related changes best done together:

**1. Occupation enum**
`Pop.occupation` and `NotableMortal.occupation` are currently free strings. Canonize them into an `Occupation` enum (analogous to `SocialClass`) so that occupations are a closed, validated set. Existing string values in scenario DBs need a loader migration.

**2. SocialClass → SocialStratum**
Rename the `SocialClass` enum and all references (`Pop.social_class`, loader, exporter, display, tests) to `SocialStratum`. The values themselves (common, elite, etc.) may stay the same; this is a naming-only change but touches many files.

**3. Occupation-based action return bonuses**
Currently, action output modifiers (forage/hunt/collect yield, etc.) are keyed on social stratum. Shift the primary modifier to occupation: a farmer gets a larger forage bonus than a warrior, a scholar gets a knowledge-action bonus, etc. Stratum modifiers remain but are smaller and more generic — the two stack, with occupation providing the specific signal and stratum providing a mild background modifier. Requires auditing every place `social_class` is used to compute output or priority and replacing or supplementing with an occupation lookup table.

**Prerequisite:** Occupation enum must be defined and migration complete before the bonus redesign can land cleanly.

---

### Civilian agent bugs

10. **Durenn Vail doesn't return from Sethis.** After collecting a full hold and selling at Neran, he either doesn't score the return trip highly enough or gets stuck in a post-sell idle loop. The sell pop resolution, need satiation after selling, and travel scoring all interact here — needs a focused debug session.

---

### Random playtest notes

1. The weird margin error in the Log (when entries are sometimes formatted strangely when you're not currently looking at the Log) still resurfaces sometimes (see ![[random_additional_margin_error.png]]), but it does seem to clean itself up after a few ticks, so it's probably not a big deal.

2. ![[needs_links.png]] shows some Explore Beliefs entries in the Log that could use some sentinel/link treatment.

3. Essence income is fiddly. Starting out (mainly because Luminaries are taking the lion's share of your starting affiliated Domains), you're getting **very** little Essence. Once you have enough for Change Affiliated Domain, though, you end up with more Essence than you know what to do with **really** fast. I have a few ideas to address this:

- I am thinking of instituting a rule that the Demiurge can only ever capture 50% of the Essence generated by universal Domain expression, even if it is unclaimed by any Luminary. (In the future, when I get around to the Stronghold system, I may introduce an upgrade to raise this.)

- Of course, one way to solve the too-much-Essence problem is always going to be "give the player more to spend Essence on," and the last stages of the action redesign are meant to do just that, by finally fully implementing half-baked filler actions and stubs.

- Currently, harvesting Essence from the Underreal is **way** too risky for not a lot of benefit. Your concealment rate basically plummets immediately, even with the concealment priority set to 0.95. Part of this will be addressed in the action redesign (I want to give the player the option to stop harvesting when their concealment drops to a percentage the player chooses), but part of it is still the mechanics. It should be something you either do carefully and can leave running for hundreds of ticks without worrying about much or something you do quickly in a risky way to get a moderate amount of extra Essence when you need it. But having it at hand as an option would make the first few months less empty.

4. Luminaries are practically absent. It seems like you don't hear from them unless you go out if your way to talk to them. Granted, before the RTwP aspect as introduced, they pestered you **constantly**, but we may have to adjust the mechanics of it to find a happy medium. We could have them guaranteed to audit you within the first three months, after which they'll set intervals according to what they find in that audit and on their personalities. Perhaps they could also notice more by having their `attention` slowly rise–or even randomly for more mercurial Luminaries. Either way, there isn't that **dread** of a Luminary report that I want to be there.

5. Speaking of Luminary audits, I still think that your various footprint scores fall **way** too fast. They should be something that you pump up when you don't think Luminaries who care about particular categories are watching—and then worry about whether they'll go down in time before a Luminary audit comes in or a Luminary starts taking notice. It would be interesting if decay weren't linear—the higher it reaches, the longer it takes to fall. This could lead to several tactics: using Luminary interactions to try to trigger an audit so that you have breathing room afterwards, before the next audit comes; perhaps there could be a Proxius Directive to "clean up" a stubborn local footprint in specific locations, with the goal of reducing your universal footprint in that category.

6. Scry is **still** odd. Notable mortals (except on Neran, for some reason) are still almost impossible to detect, even when scrying at world scope. Details about worlds in entirely different systems (except their notable mortals, naturally) also show up too readily. We may want to rethink the Scrying mechanic, especially since the UI redesign I have in mind will feature an "auto-pause when all entities discovered in target location" check box; we may want to shift toward world-scrying being **intensely** focused on that world, and it becomes less getting lucky and more of a time investment. (It also couldn't hurt to introduce more Observation actions that tempt you to switch away from scrying.) That said, though, the splash discovery mechanic works well for discovering Pops "near" a targeted mortal.

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

