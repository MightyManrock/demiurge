> Plans index: [`docs/plans/PLANS.md`](plans/PLANS.md)
> Items covered by a plan are tagged `→ plan: filename.md`

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

### Investigate canonicity of Luminary/Pantheon constraints
> → plan: [constraint-audit.md](plans/constraint-audit.md)

For future scenarios, possible constraints should have a canonical programming implementation. To this end:

1. Investigate and report on how the constraints in the scenario called "The Warden's Compact" are implemented in the logic.
2. Check that the constraints in the LLM-written, injected scenario "The Ash and the Ledger" are meaningfully integrated into game mechanics.
3. If either has mechanical gaps that reduce all of some of its effects to simply "flavor text," flag this as an important issue to fix.
4. In a future plan, we will incorporate some brainstorming material for how the constraints logic can be expanded to account for different situations in future scenarios.

---

### (pending previous) Canonical constraint types and tunables
> → plan: [constraint-audit.md](plans/constraint-audit.md)

I have attached [[constraint_types]] with many ideas on possible constraint categories and how each category might be canonically tuned.

Read this document and distinguish between:

* what is already fundamentally implemented;
* what can be implemented at the current stage;
* what can be built as a scaffold for new features whose mechanics could be accounted for in advance; and
* what really ought to be deferred until much later.