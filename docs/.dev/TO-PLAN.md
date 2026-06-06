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

### TravelNetwork expansion: requirements, benefits, and agent route selection

TravelNetworks currently encode only connectivity (membership). The intended expansion has two parts:

**1. Network properties** — each TravelNetwork gains requirements and benefits:
- *Requirements*: citizenship/faction affiliation, possession of a specific Asset (e.g. a capable vessel docked at the route's origin node), payment of a cost, etc. Multiple networks may connect the same two nodes but with different access conditions. Whether a requirement is a hard gate or a soft benefit condition depends on the faction's enforcement capacity — a tribal faction can offer preferential access to trusted travelers but can't stop a determined outsider; a spacefaring civilization with orbital checkpoints can enforce hard restrictions. Both cases should be expressible in the model.
- *Benefits/costs*: expected travel time, cost in credits, average danger (once danger becomes a PopLocation property), and potentially others.

**2. Routing and agent selection** — the current `find_route` returns the shortest valid path regardless of traveler. The expanded system works in two layers:
- A router function (extending or wrapping `find_route`) filters out genuinely inaccessible routes given the traveler's current state, then labels each viable route with its objective properties.
- An agent-side selection function chooses between those routes based on the mortal's knowledge (`RouteFact`s in their KB), active directives, personality, and current goal. The same mortal may prefer different routes on different trips — Durenn takes his own ship when collecting cargo, commercial transit otherwise.

The router handles objective facts; the agent handles subjective preference. Neither layer bleeds into the other.

**Related:** `MortalAsset` likely needs a `VehicleAsset` subclass once vehicle-specific properties multiply — `cargo_capacity` is already a candidate field sitting on the generic class, and `NetworkCondition.asset_type: str` may eventually need to specify required travel capability (sublight vs. warp) rather than just an asset type string. Hold until vehicle properties actually multiply.

**Status:** `TravelNetwork` now has `edges: list[TravelEdge]` (per-pair privileged costs) and `conditions: list[NetworkCondition]` (faction, civilization, asset, stratum, occupation; hard gate or soft benefit). Model, schema, loader, and exporter are all updated. Not yet implemented: condition evaluation in routing, privileged cost lookup in `leg_cost`, or agent-side route selection logic.

**Prerequisite:** `RouteFact` already exists in `agent_core.py` and can be extended to carry network requirement/benefit data once the TravelNetwork model is expanded.

**Reference implementation — Oros sandbox:** The Oros scenario already implies four TravelNetworks and should serve as the first test case:

1. **General overland network** — Plains of Kir'an, Asvelim Savannah, Qaebdol Cave Village, Dunes of Tor, Ancestor Stones, Ulum Highlands. No requirements.
2. **Asha Dunewalker network** — Dunes of Tor, Taem's Oasis, Salt Flats. Open to all travelers at normal `max(1, a.dfc+b.dfc)` cost. Asha Dunewalker Clan membership or their permission unlocks reduced travel times: Dunes↔Oasis in 1 tick (vs. 3), Dunes/Oasis↔Salt Flats in 3/5 ticks (vs. 5/6).
3. **Stonecallers network** — Qaebdol Cave Village ↔ Ancestor Stones. Open to all travelers at normal cost. Stonecallers membership or their permission unlocks: 1 tick (vs. 2). Both nodes remain on the general network as fallback.
4. **Hiparunite network** — Ulum Highlands ↔ Hiparun's Rift. Open to all travelers at normal cost. Hiparunite membership or their permission unlocks: 2 ticks (vs. 5).

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

6. There are a few oddities in the UI for Explore Beliefs, Reveal Imāgō and Change Affiliated Domain (in particular, more than once I found I was Exploring Beliefs in the wrong Domain), but that is literally the very next thing we're doing in the action audit.

7. Manifest Omen and Preach Imāgō's  Imāgō selectors are broken, having most of the bottom of them cut off, ostensibly because we have been messing around with what it expects the Imāgō tree display code to be. But, along with Scry, those are the next three actions we'll focus on next after we finish with the Self-Refinement actions. So fixing that is very close in the pipeline.

8. Scry is **still** odd. Notable mortals (except on Neran, for some reason) are still almost impossible to detect, even when scrying at world scope. Details about worlds in entirely different systems (except their notable mortals, naturally) also show up too readily. We may want to rethink the Scrying mechanic, especially since the UI redesign I have in mind will feature an "auto-pause when all entities discovered in target location" check box; we may want to shift toward world-scrying being **intensely** focused on that world, and it becomes less getting lucky and more of a time investment. (It also couldn't hurt to introduce more Observation actions that tempt you to switch away from scrying.) That said, though, the splash discovery mechanic works well for discovering Pops "near" a targeted mortal.

9. Since we introduced RTwP, the Proxius preaching agent comes across as extremely impatient, sometimes abandoning their mission in just a few ticks. There are a few things in the pipeline to help with this, such as making Agent actions have cooldown much like your own actions do, and having mortals function as a kind of "super-Agent" that chooses between the goals of various Agent objects attached to it, meaning that there won't be as much of a need to have directed Proxiī get frustrated and quit entirely when they could just... do something else (like their day job).

---
### Human-readable Documentation
> → plan: [human-readable-docs.md](plans/human-readable-docs.md)

Especially since I have started sharing my game with friends, it is **very** clear that the only guide to how to play this game exists in my head. And now that my docs are moving with the repo, that is one area to address this.

I would like to start putting together a source about how the game works and how to go about playing it. This will include an introduction/tutorial as well as "non-codey" descriptions of the game's systems. Players who read this should come away with a good idea of what they can expect to see and how to interact with it.

In the future, we will fold a lot of this information into a redesign of the Divine Wisdom tab in-game. Ideally, that will become a definitive encyclopedia on Demiurge, with a navigable interface of its own—and possibly a search function, if possible.

---

### Pick the next big feature
> → plan: [next-big-feature.md](plans/next-big-feature.md)

Choose the next major system: Agent expansion, Factions, Governments, or resources↔tech-progress. Note that `Faction` is the data-model prerequisite for expanding the agent phase, so Agent-expansion and Factions are largely the same fork.

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

